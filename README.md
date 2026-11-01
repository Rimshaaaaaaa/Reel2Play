# Reel2Play

Reel2Play turns a small shop's Reel or product video into a tested, playable 20-second
mini-game ad that stars its own product and ends on its offer. It is built on Meta's
open-weight models: Muse Spark Open directs, Muse Glimmer play-tests, and SAM 3.1 cuts the
product out.

**Built with Muse Spark Open.**

## What a shop gets

| Who | What they get | Where it goes |
| --- | --- | --- |
| Small shops | A hosted game page with a unique win code per winner and a "challenge a friend" button, a 15-second gameplay Reel, captions, an A4 counter poster with a QR code, an embed snippet for their website, and opt-in sign-ups for their offers on WhatsApp | WhatsApp chats and Status, Instagram and Facebook links, Click-to-WhatsApp ads, the shop counter, the shop's own site |
| App developers | A Meta playable file (one HTML file up to 2 MB, or a ZIP up to 5 MB) and a lead-in video | Meta App Installs campaigns |
| Agencies | A workspace with several brands and roles, batches of games, and an MCP endpoint for their AI assistants | Both of the above |

Meta's playable-ad format only runs with the App Installs objective, so shops get the hosted
game page, which works anywhere a link works, and app developers get the true playable file.

## How it works

1. **Video in.** The shop uploads a Reel or photos on the web, or sends them in a WhatsApp
   chat, and confirms the video is theirs. The original sound is removed straight away.
2. **Director** (Muse Spark Open). Watches the video, finds the product, colours, offer and
   language, picks a template and writes the game's config as JSON.
3. **Cut-out** (SAM 3.1 on Modal). Cuts the product out of key frames as clean sprites.
4. **Builder** (plain code). Compiles the config with fixed templates into one HTML file.
5. **Tester** (Muse Glimmer on Modal). Plays the game in a headless browser from
   screenshots; 13 quality gates decide pass or fail.
6. **Fix loop.** A failed gate goes back to the director with its screenshot, up to three
   rounds. After that the shop gets the report and a "needs a person" flag, never a broken game.
7. **Publish.** A short game link, a gameplay Reel filmed from an exact replay of the
   tester's winning run, captions, and the Meta playable file with its lead-in video. Shops
   who came through WhatsApp get the link and the Reel back in the same chat.

The models read and propose; code builds the game and decides pass or fail. Every step is
written to a hash-chained audit log.

**Safety, by code.** Text from a video or a chat reaches a model only as marked data, and
anything in it that tries to give instructions is kept out of the game. No games for
alcohol, tobacco, weapons or adult products; prizes are coupons, never cash. Games run with
no network in a sandbox, and the hosted page may only send anonymous play counts.

## Setup in ten steps

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22, PostgreSQL 16 and ffmpeg.

1. Unzip the project and open a terminal in the `reel2play` folder.
2. `cp .env.example .env` (the defaults run everything on the mock model, no keys needed).
3. `make setup` installs the API, engine and web dependencies and Chromium for play-tests.
4. `createdb reel2play` creates the local database.
5. `make db` applies the migrations.
6. `make api` starts the API on http://localhost:8000.
7. In a second terminal, `make web` starts the web app on http://localhost:5173.
8. Open the web app and upload a video; the worker prepares it in a few seconds.
9. `make check` runs lint, types, all tests and the web build; `make e2e` runs Playwright;
   `make eval` runs the evaluation harness on three synthetic videos (see `eval/README.md`).
10. For real models, set `AI_MODE=live` and the keys in `.env` (see `HANDOFF.md`), then run
    `cd api && uv run reel2play model-check`.

## Project layout

```
api/                FastAPI app, PostgreSQL job queue, audit log
  src/reel2play/
    ai/             the only code that talks to a model: providers, roles, failover,
                    prompts, mock fixtures, cost meter, tool registry, agent loop
    pipeline/       the agent steps (director, cut-out, builder, tester, fix, report)
    gates/          the 13 quality gates, one small module each, decided by code
    playtest/       the play-test harness (Playwright) and where it runs (Modal Sandbox)
    cutout/         SAM 3.1 client, mask choice and cleanup, fallback cut-out
    builder/        template registry, game config schema, palette, CTA, HTML compiler
    intake/         upload and video preparation
    publish/        game page and short link, gameplay Reel, captions, Meta playable
    whatsapp/       WhatsApp Cloud API: webhook, the chat, sending the result back
    media/          storage (local or Supabase) and ffmpeg tools
    jobs/           queue, worker, handlers
    routes/         HTTP endpoints
  migrations/       Alembic
  tests/
web/                React + Vite: upload, try-it page, dashboard, gallery, game pages
engine/             TypeScript canvas engine shared by every game template, and its build
templates/          one folder per game template: template.json (description, difficulty
                    ranges) and game.ts (the game itself)
workers/modal/      SAM 3.1 and Muse Glimmer on Modal
eval/               the 30-video evaluation harness
fixtures/synthetic/ small synthetic test media (labelled synthetic)
samples/            try-it samples and their manifest (synthetic ones are labelled)
```

## Pages

| Address | What it is |
| --- | --- |
| `/` | Upload a Reel or photos, with the owner's price and offer, and an optional voice note |
| `/import` | Pick a video already posted on the shop's Instagram account or Facebook Page |
| `/batch` | Several products at once, one file each, each with its own name and price |
| `/batches/<id>` | The set of games from a batch, as each is made and tested |
| `/agency` | An agency's workspace: brands, the team and their roles, invites |
| `/templates` | Every game template with a live demo and its designer; designers send new ones |
| `/ads/<id>` | One game: live progress, the share card (link, Reels, poster, embed code), an easier version when players find it hard, the test report, the why panel |
| `/try` | For judges: pick a sample and watch each agent work |
| `/studio` | The shop's games, plays (and how many came from the poster or the website), order taps, win codes to mark as used, cost and brand kit |
| `/gallery` | The evaluated games, each playable |
| `/compare` | Blind test: the game or a still ad of the same product |
| `<API>/g/<code>` | The hosted game page a shop shares (`?layout=square` or `?layout=landscape` for other shapes; the poster adds `?from=qr`, website embeds `?from=embed`) |
| `<API>/v/<code>` | An A/B test: each visit gets one of the three versions |
| `<API>/mcp` | For AI assistants: the Model Context Protocol endpoint (see below) |

## Built during the hackathon

The building period is 27 October to 4 November 2026. Dates are Pakistan time.

| Day | Built |
| --- | --- |
| 28 October | Foundation: API skeleton, settings, PostgreSQL schema and migrations, job queue with worker and cron endpoint, hash-chained audit log, media storage (local and Supabase), the model provider layer (roles, failover between Baseten and Fireworks, reasoning per role, JSON validation with a repair round, cost meter, tool registry, agent loop, mock provider), upload with rights confirmation and sound removal, the web upload page, CI |
| 28 October | Director and cut-out: video understanding with key frames from scene detection, offer and price rules (the owner's words win), brand kit, SAM 3.1 worker on Modal with a fallback cut-out |
| 28 October | Builder: the canvas engine, three original templates (catch, runner, puzzle) with difficulty only in template.json, palette and contrast, WhatsApp end card with a coupon, Urdu right to left, one-file HTML under 2 MB |
| 28 October | Tester: the play-test harness (headless Chromium, paused game clock, network blocked), Muse Glimmer playing from screenshots, 13 code-decided gates, the critic's product check, phone and tablet runs, the fix loop with three rounds, the shop's report, and Modal Sandboxes with no network |
| 28 October | Evaluation harness: any manifest of videos through the whole pipeline, with the spec's measures overall and per kind of business, run on synthetic videos in CI; the 30-video manifest to fill in |
| 28 October | Studio, safety and demo: the shop's studio (no accounts: a key kept in the browser), anonymous plays and order taps, cost per game, the why panel with its tamper check, live progress over server-sent events, the try-it page with labelled samples, the gallery, the blind preference page, the prompt-injection guard, and blocked categories with no cash prizes |
| 28 October | Publish and WhatsApp: the hosted game page behind a short link with a link preview, the gameplay Reel filmed from an exact replay of the winning run, captions checked against the owner's facts, the Meta playable (HTML and ZIP) with its lead-in video, and the WhatsApp chat: send a video, confirm it is yours, get the link and the Reel back |
| 28 October | Stretch, first batch: import from Instagram or Facebook (official Graph API), the product followed across frames for a moving sprite, voice-note briefs on the web and WhatsApp, several products from one video or a catalog, and six more templates (memory match, scratch card, tap to reveal, stack, quiz, colour picker) |
| 28 October | Stretch, second batch: square and landscape pages and Reels, three versions per ad with an A/B link, seasonal themes (Ramzan, Eid, 14 August, wedding season, winter sale), accessibility (tap-only play, sound captions, less motion) and the claim check |
| 28 October | Stretch, third batch: the A4 counter poster with a QR code that is scanned back before it is saved, embed code for the shop's website, unique win codes with redemption in the studio, and the self-improving loop (an easier version of a hard game, tested and offered to the owner) |
| 28 October | Stretch, fourth batch: batch mode (a catalog of products becomes a varied set of games), the MCP endpoint for AI assistants with a safe video fetch, memory per brand (the director sees what worked for the shop before), and blur for bystanders' faces with SAM 3.1 (no video frame is shown when faces cannot be checked) |
| 28 October | Later features: custom mechanics (the director writes a checked script, played by the tester in the sandbox), score sharing without personal data, opt-in sign-ups for offers over WhatsApp with consent and STOP, the agency workspace with roles, and the template marketplace with live demos and checked submissions |

## Ordering from an AI assistant (MCP)

Any assistant that speaks the Model Context Protocol can order a game: add a remote MCP
server with the address `https://<your API>/mcp` (streamable HTTP, no sign-in). It offers
three tools: `list_game_templates`, `make_playable_ad` (a public https link to a video the
shop owns, `rights_confirmed: true`, and a WhatsApp number or shop link) and
`get_playable_ad` (ask every minute or so until the status is `published`). The same
agents, tests and safety rules run as for the web page; the first order returns a studio
key (`shop_key`) to add more ads to the same shop.

## Sound

Every sound effect is synthesized in the browser at play time (`engine/src/audio.ts`), so
there are no audio files and nothing licensed from anyone else. The shop's own music is
removed on upload and never reused.

## Model API upgrade path

Meta's Model API (dev.meta.ai) is not available from Pakistan, so Reel2Play runs on
open-weight models served through Baseten, Fireworks and Modal. When the Model API is
reachable, these slot in through the same role configuration (`api/src/reel2play/ai/roles.toml`):

- **Muse Spark 1.3** as the director endpoint, ahead of Spark Open.
- **Muse Image** for generated game backgrounds and themed end cards.
- **Muse Wonder** for animated end cards.
- **Voice Transcribe** for voice-note briefs (feature 10).
- **SAM 3.1 through the API** instead of self-hosting it on Modal.

## Roadmap

The feature register tracks all 65 items and their current status (`FEATURES.md`). The current
register is 34 `done`, 29 `needs-key`, and 2 `partial`; code presence and mock tests do not
prove that live providers or third-party services are running. What remains includes the
credentials and deployments listed in `HANDOFF.md`, the 30 real consented product videos,
a live evaluation run, and the open questions in `PROGRESS.md`.

---

Built with Muse Spark Open.
