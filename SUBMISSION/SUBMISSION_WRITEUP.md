# Reel2Play — submission write-up (draft)

> Replace bracketed fields and remove any sentence that the final demo/evidence does not support. This draft deliberately avoids invented usage, conversion, or evaluation numbers.

## One-line summary

Reel2Play turns a small business's own product Reel into a short, tested, playable mini-game ad and a set of shareable campaign assets.

## The problem

Small shops already create short product videos, but interactive advertising usually requires separate creative, development, and quality-assurance work. That makes playable experiences difficult for businesses without an in-house technical team.

## The solution

A shop uploads a product video or selects an eligible sample, confirms it has permission to use the media, and provides its product details and offer. Reel2Play analyses the brief, prepares product imagery, selects a fixed game template, builds a playable experience, runs quality checks, and prepares shareable outputs. The hosted game link is the primary distribution path for ordinary shops; a Meta playable export is an additional output for the applicable App Installs use case.

## How it works

1. **Intake and rights:** video/photo intake, owner-provided product details, rights confirmation, and removal of original audio.
2. **Director:** a model proposes product understanding, visual direction, language, offer interpretation, and a structured game configuration.
3. **Product preparation:** SAM 3.1 integration is available through the Modal worker; fallback behaviour is designed to avoid exposing unchecked video frames.
4. **Build:** application code validates the configuration and compiles it with fixed game templates and the shared game engine.
5. **Play-test:** the tester agent interacts with the game through the browser harness; code-defined gates determine pass/fail.
6. **Fix and report:** bounded repair attempts can be made; unresolved failures are reported for human review.
7. **Publish:** the pipeline can prepare a hosted game page and supporting assets such as a gameplay Reel, captions, poster, embed snippet, and Meta playable output.

## Model use and attribution

The project is designed around Meta open-weight models: Muse Spark Open for director-style reasoning, Muse Glimmer for play-testing, and SAM 3.1 for visual segmentation/face-related processing. The project includes provider adapters and deployment paths for these roles. **The exact models/providers that executed in the submitted recording must be stated here:**

- Director execution in demo: `[model/provider, or mock mode]`
- Play-test agent execution in demo: `[model/provider, or scripted/mock mode]`
- Segmentation execution in demo: `[SAM 3.1 deployment, fallback, or not used]`
- Evidence: `[redacted run identifier/log screenshot/config evidence]`

Do not claim that a model ran live solely because its adapter or configuration exists. Keep the attribution `Built with Muse Spark Open` visible in the product and submission materials.

## Safety and trust

The workflow is designed to require owner rights confirmation, remove source audio, block disallowed product categories and cash-prize claims, treat user/video text as untrusted data, isolate game play-testing from network access, and avoid collecting personal data in anonymous play analytics. Bystander-face processing depends on the configured SAM service; when it is unavailable, the fallback is designed not to display unchecked source frames. These controls should be demonstrated or verified before describing them as active in a live deployment.

## Evaluation

The repository includes an evaluation harness that records first-try success, success after fixes, time to a passed game, blind preference, completion, business-category understanding, and cost. CI uses synthetic sample videos and mock responses. The 30-video real-shop evaluation is **not yet complete** in the current project status: the example manifest still needs real, consented shop videos and a live run. No real-world performance or conversion result is claimed in this draft.

## Current implementation status

The feature register currently reports 34 features as `done`, 29 as `needs-key`, and 2 as `partial`. The main application architecture and demo flow are present, while several integrations require credentials/deployment and the 30-real-video evaluation/gallery remain partial. Refer to `FEATURES.md`, `PROGRESS.md`, and `HANDOFF.md` for the detailed status and setup requirements.

## What makes the approach different

- A short playable ad is generated from a shop's existing product media rather than asking the shop to commission a game from scratch.
- Models propose structured content while deterministic application code builds and validates the game.
- A browser-based play-test and explicit quality gates are part of the generation workflow.
- The output is designed for the channels small shops already use: shareable links, WhatsApp, social posts, QR posters, and website embeds.

## Demo links and team

- Live demo: `[insert verified public URL]`
- Three-minute video: `[insert final video URL]`
- Public source repository: `[insert verified repository URL, if required by the rules]`
- Team members: `[list every contributor who worked on the project, after confirming the hackathon rules]`
- Track: `[confirm exact track name in portal]`

## What remains

Configure and verify live providers and hosted services, run the evaluation on 30 real product videos with permission, populate the gallery from approved results, and complete final device/browser checks. Any feature not demonstrated or verified should remain described as implemented-but-unverified, needs-key, or partial according to the feature register.
