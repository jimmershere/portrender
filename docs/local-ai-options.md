# Local / open-source options for voice, avatar and video — 2026-09-23

Research for blockers B-3…B-6 in [`SETUP-STATUS.md`](SETUP-STATUS.md): can the fleet
generate moving avatars with voice, and replace kie.ai, without paying per clip?

Per fleet rule 6, every claim below is sourced and uncertainty is flagged.
**Host facts are verified on the machines.** Everything else is web-sourced on
2026-09-23 and marked *(web)*; figures from SEO-style content sites are marked
*(web, low confidence)* — treat them as order-of-magnitude, not spec.

## The decisive fact: neither host has a GPU

Verified on both machines, 2026-09-23:

| | pop-os | quasimodo |
|---|---|---|
| CPU | AMD Ryzen 7 6800H, 8c/16t | Intel i5-1135G7, **4c/8t** |
| GPU | Radeon 680M **iGPU** (RDNA2, 12 CU, shared RAM) | Iris Xe **iGPU** |
| Discrete VRAM | **none** | **none** |
| RAM | 30 GiB | 30 GiB |
| Free disk on `/app` | 611 GB | 854 GB |
| CUDA / ROCm | not installed | not installed |
| ollama | not installed | not installed |

**This corrects `/app/CLAUDE.md`, which lists quasimodo's hardware as
*unverified*.** quasimodo is not the beefy host — it is roughly **half** the
machine pop-os is (4 cores vs 8, an older mobile i5 vs a Ryzen 7). Any "run the
heavy job on quasimodo" instinct is backwards: **pop-os is the stronger box.**

Both are mobile-class platforms with soldered integrated graphics. Neither can
take a desktop GPU without an external enclosure.

## Correction: ollama cannot do this

Ollama runs **text** LLMs (and vision-*input* models). It does not generate
images, video, or speech, and there is no "strong open model" in ollama that
produces a talking avatar. Image/video diffusion is a different stack entirely
(ComfyUI / diffusers). So the answer to "can quasimodo or pop-os render this
using ollama" is **no — not because the hardware is too small, but because that
is not what ollama does.**

Ollama *is* the right answer for one of the four missing keys — see B-3 below.

## What genuinely runs on this hardware, free

### Ad scripts (replaces `OPENROUTER_API_KEY`, B-3) — ✅ solved locally

Ollama on pop-os. Expect **~10–15 tok/s on a 7B model at Q4**, with the Radeon
680M able to take some layers off the CPU for a 20–40% gain *(web, low
confidence)*. Ad copy is short, so that is comfortably fast enough. Recommended
starting model: **Qwen3.5-class 4B–9B at Q4**, described as the sensible CPU-only
default for 32 GB machines *(web)*. `gpt-oss-20B` is reported faster than
Qwen3-14B with weaker world knowledge *(web)*.

**But consider not needing it at all.** Fleet rule 1 says the thinking belongs in
Claude Code skills, not app code. Ad scripts written by a Claude Code skill use a
subscription you already pay for, cost nothing extra, and are better than any 7B
model. Ollama is the right fallback for unattended/cron runs where no agent is
driving. Both beat paying OpenRouter.

### Voice (replaces the voice half of `HEYGEN_API_KEY`, B-5) — ✅ solved locally

**Chatterbox** (Resemble AI, **MIT**) is the standout: zero-shot voice cloning
from ~5 s of reference audio. The **Chatterbox-Nano** variant (110M params) is
reported to run ~3× faster than realtime on 8 CPU cores *(web)*.

⚠️ **Measured on pop-os 2026-09-23, the DEFAULT model is 8–15× *slower* than
realtime** (30 chars → 1.64 s audio in 25 s; 124 chars → 5.56 s audio in 44 s).
The "3× faster" figure is Nano specifically, not Chatterbox generally. A 30 s
voice-over is therefore ~4–8 minutes of CPU: batch, not interactive. Nano is the
upgrade path if that becomes the bottleneck.

Resemble's own blind study claims 65.3% listener preference over ElevenLabs
*(vendor claim — treat as marketing)*. A self-host server with an
OpenAI-compatible API and CPU support exists *(web)*.

Alternatives: **Piper** (MIT, fastest on CPU, audibly synthetic, no cloning),
**Kokoro-82M** (Apache-2.0, 54 fixed voices, **cannot clone**).

⚠️ **Licence traps for a commercial merch business:** **XTTS v2 is CPML**
(non-commercial without contacting Coqui) and **F5-TTS is CC-BY-NC 4.0** *(web)*.
Both are widely recommended online and both are wrong for Earl Biggers. Use
Chatterbox, Piper or Kokoro.

### Stills (relieves B-1, the OpenAI credit blocker) — ✅ viable, slower

Distilled/turbo diffusion on CPU is usable. Reported on a Core i7-12700
(comparable class to the 6800H): **SDXL-Lightning 768×768, 2 steps → 10–18 s per
image**; a 4B Flux-class model at 1024×1024 → **~108 s** *(web, low confidence)*.

That is fine for overnight merch batches, poor for interactive iteration. It does
**not** match gpt-image-2 quality, but it means portrender is not dead while the
OpenAI balance is zero — and it costs nothing per image forever.

## What is marginal: the moving avatar

Lip-sync is far lighter than full video diffusion, but still wants a GPU.

| Model | Licence | Commercial? | Notes |
|---|---|---|---|
| **MuseTalk 1.5** | MIT | ✅ yes | realtime 30fps+ **on a V100**; light footprint *(web)* |
| **LatentSync** | Apache-2.0 | ✅ yes | 8 GB VRAM (v1.5) / 18 GB (v1.6) *(web)* |
| **SadTalker** | Apache-2.0 | ✅ yes | **CPU-only: 10–30 min per video** *(web)* |
| **Wav2Lip** (public model) | LRS2-derived | ❌ **NO** | *"strictly non-commercial"* — trained on LRS2; needs a Sync Labs contract *(web)* |
| **LivePortrait** | — | check | CPU inference "possible but slow"; authors recommend NVIDIA *(web)* |
| **Duix-Avatar** (ex-HeyGem) | custom | ⚠️ conditional | commercial OK below 100k users / $10M revenue; **RTX 4070 floor** *(web)* |
| **daVinci-MagiHuman** | Apache-2.0 | ✅ yes | 15B, ~2 s per clip **on an H100** *(web)* |

**Wav2Lip is the single biggest trap here** — it is the most-recommended open
lip-sync model on the internet and it is the one Earl Biggers may not use.

Verdict: **SadTalker on pop-os is the only commercially-clean option that runs
with no GPU at all**, at 10–30 min per clip. That is batch-overnight territory,
not iteration. MuseTalk is the better model but its "realtime" numbers are GPU
numbers; a reported Apple-Silicon MLX CPU port needs **~50 GB peak RAM** *(web)*,
which exceeds the 30 GiB in both boxes.

## What is not happening locally: text-to-video

This is the honest no.

| Model | Floor to run *(web)* |
|---|---|
| Wan 2.2 **5B**, FP8 | 8 GB VRAM — "several to many minutes" per 5 s 720p clip |
| Wan 2.2 14B GGUF Q4/Q5 | 6 GB VRAM + RAM offload → 480p, 10–15+ min per clip |
| Wan 2.2 14B full | 40 GB+ (24 GB quantised) |
| LTX-2.5 (22B) | 12 GB minimum, 32 GB FP8 recommended |
| HunyuanVideo | 60 GB+ full, 24 GB quantised |

The floor of the entire category is **8 GB of discrete VRAM**, and the fleet has
zero. CPU-only text-to-video is described as *"impractically slow — many minutes
to hours per short clip… the least viable option"* *(web)*. Note also the
guidance that low-VRAM offloading needs **24–32 GB system RAM** — the fleet has
30 GiB, so RAM is not the constraint. **The GPU is.**

So: **there is no free local replacement for kie.ai on this hardware.** Anything
that claims otherwise is quoting GPU benchmarks.

## The three real options for video

1. **Keep a per-clip API.** fal.ai Wan 2.5 ≈ **$0.05/s**; kie Wan 2.7 ≈ $0.08/s;
   fal Wan 2.7 ≈ $0.10/s; Replicate $0.07–0.25/s *(web, low confidence)*. A 5 s
   clip ≈ **$0.25–0.50**. Zero ops. This is what clemtock already does.
2. **Rent a GPU by the hour and self-host the open model.** vast.ai RTX 4090
   ≈ **$0.34/hr**; A100 SXM ≈ $1.49/hr; H100 ≈ $2–3/hr *(web)*. At ~4 min per
   clip on a 4090 that is roughly **$0.02–0.03 per clip** — about **10–15×
   cheaper than the APIs**, and it pays for itself after ~2 clips per rented
   hour. Cost: you own the ComfyUI/Wan setup and the idle-time discipline.
3. **Buy a GPU.** Neither host can take one internally. This means a new desktop
   or an eGPU enclosure — a purchase decision, not a config change. Worth it only
   if video becomes steady-state volume rather than occasional.

## Where a local provider would plug in

`backend/clemtock/providers/base.py` already defines exactly the right seams —
`ScriptProvider`, `ImageProvider`, `VideoProvider`, `AvatarProvider`, all ABCs,
with the docstring noting the abstraction exists "to let video-gen swap between
kie.ai and HeyGen… without touching the pipeline". A local stack is new sibling
classes, not a rewrite:

| New provider | Implements | Replaces | Runs where |
|---|---|---|---|
| `ollama_script.py` | `ScriptProvider` | OpenRouter (B-3) | pop-os CPU ✅ |
| `chatterbox_voice.py` | (voice half of avatar) | HeyGen voice (B-5) | pop-os CPU ✅ |
| `sadtalker_avatar.py` | `AvatarProvider` | HeyGen (B-5) | pop-os CPU, 10–30 min/clip ⚠️ |
| `comfy_image.py` | `ImageProvider` | OpenAI stills (B-1) | pop-os CPU, ~10–120 s/img ✅ |
| `comfy_video.py` | `VideoProvider` | kie.ai (B-4) | **rented GPU only** ❌ |

Note `AvatarProvider.generate(text, out, avatar_id, voice_id)` takes *text*, so a
local implementation has to do TTS **and** lip-sync — Chatterbox feeding
SadTalker. HeyGen bundles those two steps; locally they are separate.

## Open questions — ask, don't guess

- **PR-6. Is a rented GPU acceptable?** It puts brand art and voice on a
  third-party host for the duration of the render, which is a different privacy
  posture from "everything on the fleet". Fleet rule 5 (nothing leaves the
  machine without a human) arguably already covers it, but this is a new class of
  egress and should be decided deliberately.
- **PR-7. Does the avatar need to be photoreal?** These ventures are cartoon
  mascots (Earl Biggers, Madd Hatchery). A rigged 2D mascot or Ken-Burns-plus-
  lip-flap may beat a photoreal talking head *and* run instantly on CPU. Nobody
  has confirmed the product needs a realistic human face at all — that assumption
  came from HeyGen being in the stack, not from a brief.
- **PR-8. Whose voice is being cloned?** Chatterbox clones from ~5 s of audio.
  Cloning a real person's voice for ads needs that person's consent on record.

## Sources

Talking-head / lip-sync: [pixazo](https://www.pixazo.ai/blog/best-open-source-ai-lip-sync-models) ·
[lip-sync model selection & licences](https://tomodahinata.com/en/blog/ai-lip-sync-talking-head-model-selection-guide-2026) ·
[Spheron self-host avatar](https://www.spheron.network/blog/self-host-ai-avatar-generator-heygen-alternative-2026/) ·
[awesome-talking-head-generation](https://github.com/harlanhong/awesome-talking-head-generation) ·
[LiveTalk ONNX port](https://github.com/arghyasur1991/LiveTalk-Unity)
Video models / VRAM: [Hyperstack](https://www.hyperstack.cloud/blog/case-study/best-open-source-video-generation-models) ·
[LTX guide](https://ltx.io/blog/open-source-video-generation-models-guide) ·
[low-VRAM & CPU reality](https://localaimaster.com/blog/local-text-to-video-low-vram) ·
[AI Magicx comparison](https://www.aimagicx.com/blog/open-source-ai-video-models-comparison-2026)
TTS: [Chatterbox (Resemble)](https://www.resemble.ai/learn/models/chatterbox) ·
[chatterbox repo](https://github.com/resemble-ai/chatterbox) ·
[self-host server](https://github.com/devnen/Chatterbox-TTS-Server) ·
[CodeSOTA open-source TTS](https://www.codesota.com/speech/best-open-source) ·
[Kokoro vs XTTS vs Chatterbox](https://localaimaster.com/blog/kokoro-vs-xtts-vs-chatterbox)
LLM on CPU: [CPU-only local LLMs](https://www.popularai.org/p/best-cpu-only-local-llm) ·
[32GB local LLMs](https://atomic.chat/blog/guides/best-local-llm-32gb) ·
[unsupported AMD GPU + ollama](https://www.conroyp.com/articles/running-ollama-ubuntu-unsupported-amd-gpu-performance-guide)
GPU rental / API pricing: [vast.ai pricing](https://vast.ai/pricing) ·
[RunPod vs Vast](https://www.spheron.network/blog/runpod-vs-vastai-2026/) ·
[video API per-second rates](https://nodetool.ai/blog/ai-video-generation-cost)
CPU image gen: [local image generation guide](https://www.local-llm.net/guides/local-image-generation/) ·
[SDXL-Turbo CPU experiments](https://dev.to/govindsb/sdxl-turbo-optimization-experiments-fgg)
