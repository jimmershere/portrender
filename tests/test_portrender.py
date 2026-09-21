"""No-network tests. The OpenAI client is exercised against a fake urlopen."""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("PORTRENDER_DATA", tempfile.mkdtemp(prefix="portrender-test-"))
os.environ["PORTRENDER_QUIET"] = "1"

from portrender import brands, config, craft, export, jobs, openai_images, prompts  # noqa: E402
from portrender import server  # noqa: E402

PNG = bytes.fromhex("89504e470d0a1a0a0000000d494844520000000100000001080200000090775" "3de0000000c4944415408d763f8cfc0000003010100c9fe92ef0000000049454e44ae426082")


class Craft(unittest.TestCase):
    def test_avoid_includes_universal_and_subject(self):
        c = craft.avoid_clause("animal")
        self.assertIn("wrong number of legs", c)
        self.assertIn("watermark", c)
        self.assertTrue(c.startswith("Avoid: "))

    def test_headline_block_quotes_exact_text(self):
        self.assertIn('reads exactly: "Do It Tired"', craft.headline_block("Do It Tired"))
        self.assertEqual(craft.headline_block(""), "")


class Prompts(unittest.TestCase):
    def test_sections_and_vars(self):
        t = prompts.substitute("A {{x}}{{#y}} with {{y}}{{/y}}{{^y}} alone{{/y}}", {"x": "hen", "y": ""})
        self.assertEqual(t, "A hen alone")
        t = prompts.substitute("A {{x}}{{#y}} with {{y}}{{/y}}", {"x": "hen", "y": "jam"})
        self.assertEqual(t, "A hen with jam")

    def test_template_render_merges_brand_and_appends_avoid(self):
        tpl = prompts.load("tee-graphic")
        b = brands.load("maddhatch")
        text, ctx, missing = prompts.render_prompt(tpl, {"subject_desc": "a hen", "headline": "Need Some Eggs?"}, b)
        self.assertEqual(missing, [])
        self.assertIn("sticker-style", text)               # brand.style default
        self.assertIn('reads exactly: "Need Some Eggs?"', text)
        self.assertIn("Avoid:", text)
        self.assertEqual(text.count("Avoid:"), 1)

    def test_missing_required_reported(self):
        tpl = prompts.load("tee-graphic")
        _, _, missing = prompts.render_prompt(tpl, {}, None)
        self.assertEqual(missing, ["subject_desc"])

    def test_free_prompt_without_subject_has_no_avoid(self):
        text, _, _ = prompts.render_prompt(None, {}, None, raw_prompt="a lighthouse")
        self.assertEqual(text, "a lighthouse")
        text, _, _ = prompts.render_prompt(None, {"subject": "animal"}, None, raw_prompt="a moose")
        self.assertIn("Avoid:", text)

    def test_all_shipped_templates_parse_and_render(self):
        b = brands.load("au2")
        for t in prompts.list_templates():
            self.assertTrue(t.prompt, t.name)
            fill = {k: f"<{k}>" for k, s in t.vars.items() if s.get("required")}
            text, _, missing = prompts.render_prompt(t, fill, b)
            self.assertEqual(missing, [], t.name)
            self.assertNotIn("{{", text, t.name)

    def test_save_template_roundtrip(self):
        with mock.patch.object(config, "TEMPLATES_DIR", Path(tempfile.mkdtemp())):
            p = prompts.save_template("My Test!", title="T", prompt="Hello {{who}}", subject="animal",
                                      defaults={"size": "1024x1024"}, vars={"who": {"default": "world", "help": "h"}})
            self.assertEqual(p.name, "my-test.toml")
            t = prompts.load("my-test")
            text, _, _ = prompts.render_prompt(t, {}, None)
            self.assertTrue(text.startswith("Hello world"))
            self.assertEqual(t.defaults["size"], "1024x1024")


class Brands(unittest.TestCase):
    def test_all_brands_load(self):
        slugs = {b.slug for b in brands.list_brands()}
        self.assertTrue({"maddhatch", "au2", "icenstone", "earl_biggers"} <= slugs)
        self.assertEqual(brands.load("maddhatch").get("handoff.tee_empire_brand"), "madd_hatchery")
        self.assertIn("brand.palette", {f"brand.{k}" for k in brands.load("au2").flat()})


class Client(unittest.TestCase):
    def _fake(self, captured):
        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def urlopen(req, timeout=0):
            captured.append(req)
            body = {"created": 1, "data": [{"b64_json": base64.b64encode(PNG).decode()}], "usage": {"output_tokens": 5}}
            return R(json.dumps(body).encode())
        return urlopen

    def test_generate_builds_json_body(self):
        cap = []
        with mock.patch("urllib.request.urlopen", self._fake(cap)):
            r = openai_images.generate("hi", api_key="k", model="gpt-image-2", n=1, size="1024x1024",
                                       quality="low", background="transparent")
        self.assertEqual(r.images[0], PNG)
        body = json.loads(cap[0].data)
        self.assertEqual(body["background"], "transparent")
        self.assertEqual(cap[0].full_url.split("/")[-1], "generations")
        self.assertEqual(cap[0].headers["Authorization"], "Bearer k")

    def test_edit_builds_multipart(self):
        cap = []
        with mock.patch("urllib.request.urlopen", self._fake(cap)):
            r = openai_images.edit("fix", [PNG, PNG], api_key="k", model="gpt-image-2", input_fidelity="high")
        self.assertEqual(len(r.images), 1)
        self.assertIn("multipart/form-data", cap[0].headers["Content-type"])
        self.assertEqual(cap[0].data.count(b'name="image[]"'), 2)
        self.assertIn(b'name="input_fidelity"\r\n\r\nhigh', cap[0].data)

    def test_non_retryable_http_error_raises(self):
        import urllib.error

        def boom(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b'{"error":{"message":"nope"}}'))
        with mock.patch("urllib.request.urlopen", boom):
            with self.assertRaises(openai_images.ImagesError) as cm:
                openai_images.generate("x", api_key="k", model="m", max_retries=0)
        self.assertIn("nope", str(cm.exception))


class Jobs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.p = mock.patch.multiple(config, DATA_DIR=self.tmp, RENDERS_DIR=self.tmp / "renders",
                                     JOBS_DIR=self.tmp / "jobs", REFS_DIR=self.tmp / "refs")
        self.p.start()

    def tearDown(self):
        self.p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _job(self, n=2):
        man = jobs.create(kind="generate", prompt="p", label="Test Label", brand="au2", template=None, vars={},
                          model="gpt-image-2", n=n, size="1024x1024", quality="low", background="auto")
        return jobs.run(man["id"], dry_run=True)

    def test_dry_run_writes_images_and_manifest(self):
        man = self._job(3)
        self.assertEqual(man["status"], "done")
        self.assertEqual(len(man["images"]), 3)
        self.assertTrue((jobs.job_dir(man["id"]) / "01.png").is_file())
        self.assertTrue((jobs.job_dir(man["id"]) / "prompt.txt").is_file())
        self.assertIsNotNone(man["cost_estimate"])

    def test_review_verbs_and_statuses(self):
        man = self._job()
        jobs.review(man["id"], 1, "approve", note="nice")
        jobs.review(man["id"], "02.png", "rejected")
        jobs.review(man["id"], 1, "star")
        m = jobs.read(man["id"])
        self.assertEqual(m["images"][0]["status"], "approved")
        self.assertEqual(m["images"][0]["note"], "nice")
        self.assertTrue(m["images"][0]["starred"])
        self.assertEqual(m["images"][1]["status"], "rejected")
        self.assertEqual(len(jobs.list_jobs(image_status="approved")), 1)
        self.assertEqual(len(jobs.approved_images()), 1)
        with self.assertRaises(ValueError):
            jobs.review(man["id"], 1, "bogus")

    def test_missing_key_errors_cleanly(self):
        man = jobs.create(kind="generate", prompt="p", label="x", brand=None, template=None, vars={},
                          model="m", n=1, size="auto", quality="low", background="auto")
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": ""}), mock.patch.object(config, "ENV_FILES", []):
            man = jobs.run(man["id"])
        self.assertEqual(man["status"], "error")
        self.assertIn("OPENAI_API_KEY", man["error"])

    def test_exports(self):
        man = self._job(1)
        te, ct, au = self.tmp / "te", self.tmp / "ct", self.tmp / "au2"
        (te / "inbox").mkdir(parents=True); (ct / "assets" / "mascots").mkdir(parents=True); au.mkdir()
        with mock.patch.multiple(config, TEE_EMPIRE_DIR=te, TEE_EMPIRE_INBOX=te / "inbox", CLEMTOCK_DIR=ct,
                                 CLEMTOCK_URL="http://127.0.0.1:1", AU2_DIR=au):
            r = export.to_tee_empire(man["id"], 1, text="EST. 2024", placement="underneath")
            side = json.loads(Path(r["sidecar"]).read_text())
            self.assertEqual(side["placement"], "underneath")
            self.assertEqual(side["brand"], "au2")
            self.assertEqual(export.to_clemtock(man["id"], 1, category="logos")["rescanned"], False)
            self.assertTrue(Path(export.to_au2(man["id"], 1)["image"]).is_file())
            self.assertTrue((ct / "assets" / "logos" / "test-label-01.png").is_file())
            # second export of the same image does not overwrite
            r2 = export.to_tee_empire(man["id"], 1)
            self.assertNotEqual(r["image"], r2["image"])
        exps = jobs.read(man["id"])["images"][0]["exports"]
        self.assertEqual([e["target"] for e in exps], ["tee-empire", "clemtock", "au2", "tee-empire"])

    def test_server_render_and_review_via_api_functions(self):
        with mock.patch.object(server, "spawn", lambda jid: jobs.run(jid, dry_run=True)):
            out = server.api_render({"template": "sticker", "brand": "maddhatch", "vars": {"subject_desc": "a hen"}, "n": 1})
            jid = out["job"]["id"]
            self.assertEqual(jobs.read(jid)["status"], "done")
            out = server.api_review({"job": jid, "image": "01.png", "action": "approve"})
            self.assertEqual(out["job"]["approved"], 1)
            out = server.api_edit({"source": f"{jid}:1", "prompt": "wink", "n": 1})
            self.assertEqual(jobs.read(out["job"]["id"])["kind"], "edit")
            self.assertEqual(jobs.read(out["job"]["id"])["parent"], {"job": jid, "image": "1"})
            with self.assertRaises(server.ApiError):
                server.api_render({"template": "sticker"})
        st = server.api_state()
        self.assertIn("maddhatch", [b["slug"] for b in st["brands"]])


if __name__ == "__main__":
    unittest.main()
