# Progress

Updated after every build group so a new session can carry on from here.

## Done

### Group 1: Foundation (28 October)

- API skeleton: settings from the environment, SQLAlchemy models, Alembic migration
  `0001_foundation` (shops, brand kits, videos, jobs, audit log, model calls).
- Job queue on PostgreSQL (`SKIP LOCKED`), retries with backoff, stale-job recovery, an
  in-process worker thread, and `POST /internal/cron` behind `X-Cron-Secret`.
- Hash-chained audit log with verification and `GET /api/audit/...`.
- Media storage: local (signed links served by the API) and Supabase Storage (REST).
- Provider layer in `ai/`: OpenAI-compatible client for Baseten, Fireworks and the Modal
  Glimmer server; roles in `roles.toml` with failover order and reasoning per role;
  JSON answers validated with Pydantic plus one repair round (Spark Open on Baseten has no
  JSON mode); cost meter per call; tool registry and agent loop; mock provider with
  recorded fixtures; `reel2play model-check` CLI and `/internal/model-check`.
- Upload (feature 1): video or photos, owner's brief (price kept exactly as typed), rights
  confirmation required, sound removed, speech kept privately for the director.
- Web: upload page with phone preview and live status.
- CI: API lint, format, mypy strict, migrations check, tests with 85% coverage floor; web
  lint, tests, build; Playwright end-to-end on phone and desktop sizes. Manual live
  model-check workflow.
- Results: 94 API tests, 99% line coverage; 8 web unit tests; 4 Playwright tests.

### Group 2: Director and cut-out (28 October)

- Frames: ffmpeg scene detection plus even samples, up to six candidates, sharpness scores,
  measured dominant colours (`media/frames.py`).
- Director step (`pipeline/analyze.py`, prompt `director_analyze.md`, schema in
  `analysis.py`): sends the muted video, the speech as a separate audio part, and the
  candidate frames; validates the answer; picks key frames (sharpest frame if the picks are
  unusable); builds the `CreativeBrief` where the owner's price and offer always win; crops
  the logo; saves the brand kit (palette, tone, logo) and feeds it to the next analysis.
- Cut-out step (`pipeline/cutout.py`, `cutout/`): SAM 3.1 client for our Modal endpoint,
  mask choice weighted by the director's box, cleanup (largest region, holes, feathered
  edge), RGBA sprite up to 512 px; GrabCut fallback marked lower quality.
- Pipeline runner (`pipeline/runner.py`): one queue job per step, shared state in the
  database, audit-log progress lines, permanent failures and a give-up hook that marks the
  ad failed with the reason.
- Modal apps (`workers/modal/`): SAM 3.1 behind a proxy-authenticated FastAPI endpoint,
  Muse Glimmer behind vLLM with `@app.server`. Decorators checked against Modal 1.6.3.
- `GET /api/ads/{id}`; the upload page now follows the agents live and shows the brief,
  palette and cut-out. Web restyled: neutral oklch palette, tactile 3D cards and buttons,
  dark mode, container queries.
- Results: 121 API tests, 98% coverage; 9 web tests; 4 worker tests; 4 Playwright tests.

### Group 3: Engine, builder and three templates (28 October)

- Engine (`engine/src`): 9:16 stage that scales to any screen, pointer input in play-field
  units, a hard 30 s stop, intro and end cards as DOM (text nodes only), tactile 3D
  buttons, Urdu/English with right-to-left, system fonts only, synthesized sound effects,
  hosted and Meta platforms, analytics hook, and `window.__r2p` with a manual clock so
  testers and scripted players can play turn by turn.
- Templates (`templates/`): catch (tote bag, "dud" pebbles), runner (Pip the courier,
  crates, coupons, product on a podium), puzzle (3 × 3 raised tiles, hint, self-solve at
  the limit). Difficulty values live only in each template.json.
- Builder (`api/src/reel2play/builder`): template registry, game config schema (camelCase,
  matching the engine), contrast-safe palette from the brand colours (every text pair at
  least 4.5:1), WhatsApp link with product and coupon, WebP sprites and a square product
  photo, the single-HTML compiler with escaping and the 2 MB check.
- Build step: the director proposes template, difficulty, colours and words; code corrects
  unknown templates, invented offers and off-palette colours; the build is stored and
  shown live in the upload page's phone frame (sandboxed iframe, strict CSP).
- Results: API tests pass at 98% coverage; engine 13 unit tests and 30 browser tests
  (360 × 640 and tablet); web 10 tests; Playwright end-to-end on phone and desktop.

### Group 4: Tester, gates, fix loop, report and sandbox (28 October)

- Play-test harness (`playtest/harness.py`): a standalone Playwright script that speaks
  JSON lines; it opens the game at a screen size (360 × 640 touch phone with the CPU
  slowed 4×, or a 768 × 1024 tablet), blocks every request, drives the game's paused clock,
  taps and drags, takes screenshots, measures each end-card part (box, clipping, styles)
  and clicks the call to action with popups and `FbPlayableAd` recorded.
- Where it runs (`playtest/session.py`): a Modal Sandbox with `block_network=True` from
  the official Playwright image when `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET` are set; a local
  subprocess in development and CI; production without Modal refuses (a permanent error, not
  retried).
- Players (`playtest/drivers.py`): the tester agent (Glimmer, Spark Open as failover)
  plays from screenshots with tap, drag and wait as JSON actions in plain text, one turn
  at a time on the paused clock; on the mock, scripted players per template, labelled
  "scripted".
- 13 gates (`gates/`), one small module each, all decided by code from the evidence; the
  critic (Spark Open) checks the product, offer, price, readability and language from the
  real key frame, a gameplay shot and the end card.
- Test step, fix step and report (`pipeline/playtest.py`, `fix.py`, `report.py`): a
  failure goes back to the director with the failed gates, measurements, screenshot and
  the templates' allowed ranges; the rebuilt game is tested again, up to three rounds, then
  "needs a person". The shop's report names each check in its own language with the
  tester's screenshot; the web page shows it as a checklist (right to left for Urdu).
- Coverage now includes the harness subprocess (coverage's subprocess patch, greenlets).
- Results (checked from a clean unzip): 172 API tests at 98% coverage; engine 13 unit and
  30 browser tests; web 12 tests; 4 worker tests; Playwright end-to-end on phone and
  desktop now waits for the play-test report (about a minute per upload on the mock).

### Group 5: Publish and WhatsApp (28 October)

- Exact replays: the harness pauses the game clock before the first tap, so a run is just
  its list of commands. Each test now stores every run's commands (`test_runs.replays`), and
  a replay in a fresh page gives the same result to the hundredth of a second (tested on
  all three templates).
- Publish step (`pipeline/publish.py`), only for the build that passed: a 7-character
  random short link, `/g/<code>` serving the tested game plus link-preview tags (a square of
  the end card) under the same sandbox CSP; the gameplay Reel filmed from a replay of the
  winning run at 20 frames per game second and 2× pixels, encoded 720 × 1280 H.264 for 10 to
  15 seconds with no sound; the Meta playable rebuilt from the identical config (checked),
  scanned for redirect code, played once to see `FbPlayableAd.onCTAClick()`, saved as HTML
  and as a ZIP with `index.html`, plus a 5-second lead-in; captions for WhatsApp Status,
  Instagram and Facebook with every number checked against the owner's facts.
- WhatsApp (`whatsapp/`): `GET` handshake and signed `POST` webhook, messages recorded by id
  so retries run once, a two-button rights question, price and offer read from the caption,
  the media downloaded through the Graph API and sent through the normal upload path, and a
  finished-ad notice that sends the link and the Reel back (or says why not). The owner's
  number never reaches jobs, logs or the audit trail (tested).
- The CTA gate now records only facts (host, opened, right number, order written), not the
  shop's number.
- Timing fixes found by the full suite: a flawless catch run could end in 14.1 s, so the
  first drop now waits 1.7 s (normal and hard time limits 23 s); the puzzle gets a tester
  pace of 1.5 s per tap in template.json (used by the scripted and the model tester) and
  one more misplaced tile per tier. A sweep of 100 seeds across the templates passes.
- Results (checked from a clean unzip): 216 API tests at 98% coverage; engine 13 unit and
  30 browser tests (all three templates now finish in 15 to 30 s); web 13 tests; 4 worker
  tests; Playwright end-to-end on phone and desktop from upload to the published game page.
- Web: "Your game is live" card with the link (copy and open), the Reel, caption tabs with
  copy, and the Meta files for app developers.

### Group 6: Studio, safety and demo (28 October)

- Safety (`safety.py`): untrusted text goes to models as «data» and every prompt says so;
  instruction-like text from a video is kept out of the product, offer and descriptions
  (audit line `guard.flagged`); blocked categories by the director's answer or by words in
  English, Roman Urdu and Urdu stop the ad as `blocked` before any game is made; offers that
  promise cash prizes are left out ("cash on delivery" is fine).
- Studio (`shops.py`, `routes/studio.py`): the first web upload hands the browser a key
  (only its SHA-256 is stored); uploads to an existing shop need it. `/api/shop` lists the
  games with plays, completion, order taps and cost, and the brand kit.
- Analytics (`routes/events.py`, `insights.py`): plain-text beacons, validated and kept
  without IP, cookie or device; the endpoint is a meta tag added only to the hosted page,
  whose CSP allows only that address.
- Why panel (`routes/why.py`): builds with the director's reason, fix rounds, decisions,
  cost by agent, and a hash check of every entry and its link.
- Demo: `samples/` with two synthetic videos and a manifest (sneaker, Urdu sneaker, cake,
  and mock-only fix-loop and blocked demos); `/api/try` with at most three runs at once;
  live progress over server-sent events; gallery (`reel2play gallery add`); blind
  preference page and its results.
- Web: pages for the ad (`/ads/:id`, live), try-it, studio, gallery and compare, with a
  header menu; the upload page now hands over to the ad page.
- Results (checked from a clean unzip): 263 API tests at 98% coverage; engine 14 unit and
  30 browser tests; web 23 tests; 4 worker tests; Playwright end-to-end on phone and
  desktop: upload to published game, why panel, studio, and the try-it safety stop.

### Group 7: Evaluation harness (28 October)

- `reel2play eval run <manifest>`: each video goes through the ordinary upload path (marked
  synthetic when it is) and the job queue runs until its ad is finished; nothing is skipped.
  `results.json` and `report.md` give first-try success, success after fixes, median minutes
  from upload to a passed game, blind preference and completion (from visitors; refreshed
  later with `reel2play eval report`), whether the director read the kind of business
  right, and cost, overall and for each of the six kinds. `--gallery` shows the published
  games in the gallery.
- `eval/videos.example.json` has the 30 slots (five per kind); blanks must be filled in
  before a run, and every video needs a `consent` line. `eval/videos/` is never committed.
- The full suite caught one more flaky case: a catch seed with many duds could make even a
  flawless player lose at 23 s. Catch now drops at most one dud in any three, with one more
  second (24 s normal and hard, 25 s easy); random-seed sweeps of 100 ads won all 300 runs.
- CI runs the harness on `eval/ci.json` (three synthetic videos on the mock: a pass, a pass
  for another business, and the fix loop ending with a person); the manual live workflow
  runs the two synthetic samples through the real models.
- Results (checked from a clean unzip): 272 API tests at 98% coverage; engine 14 unit and
  30 browser tests; web 23 tests; 4 worker tests; Playwright end-to-end on phone and desktop.

### Stretch, batch 1: features 3, 7, 10, 11 and 13 (28 October)

- 3, import: Facebook Login (optional login configuration), the latest videos on the Pages
  the owner manages and their linked Instagram account, then the normal brief, rights check
  and upload path. Files only from Meta's servers, every redirect checked before it is
  followed, streamed with the size limit; the sign-in stays in server memory for 30 minutes
  and travels in a header. Reels with Instagram library music have no file and say so.
- 7, product tracking: a clip around the best key frame, the product followed by SAM 3.1's
  video model or by code, kept frames centred at one scale; code compares pixels and only
  animates a product that really changes. The SAM worker gained a `track` endpoint.
- 10, voice brief: recorded in the browser or sent on WhatsApp before "yes"; a minute of
  speech for the director; typed fields win, then the voice note, then the video, and code
  drops an offer whose numbers were not heard.
- 11, several products: up to three more products from the video, or one per photo in a
  catalog; each cut out; catch drops them in turn and memory match pairs them.
- 13, six templates: memory match, scratch card, tap to reveal, stack, quiz and colour
  picker, all drawn in code; seed sweeps of the scripted players finish every difficulty in
  15 to 30 seconds. The director writes facts and quiz questions; code checks them.
- The upload form is now shared by the upload and import pages (`BriefFields`).

### Stretch, batch 2: features 18, 19, 22, 23 and 31 (28 October)

- 18, shapes: `?layout=square|landscape` puts the 9:16 play field beside a panel with the
  product, offer and price; the fits-screen gate now checks both shapes; the publisher makes
  square (1080 × 1080) and wide (1920 × 1080) Reels from the tested Reel and a screenshot of
  each page. Meta playables stay portrait.
- 19, A/B: versions B and C start at the build step from A's reading and cut-outs; code
  forces another template and colours; one `/v/<code>` link shares visitors; the studio
  names a leader after 20 plays each when one is clearly ahead on order taps or finishes.
- 22, themes: occasion from the owner's pick, then the voice note, then the video; drawn
  decorations at the edges and a code-worded greeting in Urdu or English.
- 23, accessibility: tap-only play everywhere (scratch taps clear a spot), sound captions
  in game time with a CC switch, less motion when the phone asks, contrast already gated.
- 31, claims: code finds unprovable claims in three languages; the critic's are kept only if
  really present; game words with claims fail the gate; owner's own claims and a missing
  price go in the report's "Worth checking".

### Stretch, batch 3: features 36, 37, 40 and 44 (28 October)

- 36, counter poster: an A4 PDF printed in the sandboxed browser with the product, the
  owner's offer and price and a QR code (segno); the QR code is read back from a picture of
  the page with OpenCV before it is saved, and the page must be exactly one.
- 37, website embed: tall and wide `<iframe>` snippets in the share card; `?from=embed` and
  the poster's `?from=qr` mark where plays started (a new `events.source` column).
- 40, unique win codes: `POST /api/coupons` from the hosted page on a win (open to the
  sandboxed page's "null" origin, rate-limited in memory, capped per day); the code goes on
  the end card and into the WhatsApp message; the studio marks codes as used.
- 44, easier versions: after 30 plays, low completion or few wins start one easier version
  of the same game (director proposes, code keeps only easier values in range); tested,
  held as `ready`, and published under the same link when the owner chooses it.
- Shared code: `copy_ad` (A/B versions and easier versions start from the same reading
  and cut-outs).

### Stretch, batch 4: features 46, 52, 53 and 55 (28 October)

- 46, batch mode: `POST /api/batches` (2 to 12 files, one product each, `items` JSON with
  name, price, offer); every file checked first; a `batches` table and `videos.batch_id`;
  the director gets a note on the templates the rest of the set uses; `/batch` and
  `/batches/<id>` pages.
- 52, MCP: `POST /mcp`, stateless JSON-RPC, three tools; `intake/fetch.py` fetches the video
  over https from public addresses only, pinned to the checked address (SNI and certificate
  on the host name), redirects re-checked, size capped; Origin check; hourly limit.
- 53, memory per brand: `brand_memory.py` sums the shop's games per template from the
  anonymous events (finish and order-tap rates, A/B wins, games made easier); it goes to
  `director_game` (v4) and to the studio. The A/B `leader()` moved to `insights.py`.
- 55, faces: SAM 3.1 with the prompt "face" (up to 30 masks; the worker's limit was raised);
  code blurs every face not mostly inside the product mask of a cosmetics product; the
  frame is replaced in storage and the product cut out again if a face touched it. Without
  SAM, `sprites.face_check` stays `unchecked` and photo templates get the cut-out on the
  shop's colour instead of a frame. No other face model is used (Meta's models only).
- The owner's product name (batch, MCP) is screened by the injection guard and the
  blocked-category check like any other words.

### Later features: 24, 42, 43, 47 and 49 (28 October)

- 24, custom mechanics: `builder/mechanic.py` parses the director's script with esprima and
  allows only plain arithmetic, its own names, `Math` and `api` (no globals, `this`, `new`,
  eval, regexes, `try`, async, `constructor`-like names, even built from literal pieces);
  `templates/custom` hosts it; the builder writes it in its own `<script>` after removing the
  Function constructor; the scripted tester follows the script's `hint`; no Meta export.
  Upload option `lab`; prompt `director_mechanic`; a synthetic example in
  `templates/custom/example-mechanic.txt` (the mock's answer, checked equal by a test).
  The pipeline seeds each game from its ad id, so the example keeps a steady pace (every
  fifth bubble empty, a near-fixed gap); a browser test sweeps five seeds on every tier and
  each must be won in 15 to 30 s. Random empty bubbles had let a lucky seed win in 14.4 s.
- 42, challenges: `engine/src/challenge.ts`; the link carries `beat=score-goal-seconds` and
  `from=share`; events `share` and source `share` are counted.
- 43, sign-ups: `leads` table (the consent, not the number: that stays in the chat record);
  JOIN and STOP are the only words kept from a player's text; the link is added to live
  pages as they are served (`r2p-optin` tag), so the owner's switch applies at once.
- 47, agencies: `agencies`, `agency_members` (hashed keys), `agency_invites` (hashed,
  single use, seven days), `shops.agency_id`; uploads and batches accept `X-Agency-Key`
  for an editor's brands; `shop_out()` is shared with the studio.
- 49, marketplace: `/templates` with demos built from a code-drawn product; submissions
  checked by code, reviewed with `ADMIN_KEY`; never run by the API.

## Next

- Keys and the live run: `HANDOFF.md` section 3, then `reel2play eval run` on the 30 real
  videos (feature 62) and the gallery (61).

## Open questions

- Baseten's docs list the Spark Open id as `meta-models/muse-spark-open`; the brief said
  `meta-models/muse-spark-open-1026`. The default is the docs value; confirm with
  `GET /v1/models` once the key is in.
- The Baseten docs do not show the content-part name for video. The code sends
  `video_url` (the same shape as `image_url` and `audio_url`); confirm on the first live run.
- SAM 3.1: `unsloth/sam3.1` (the repo the spec links, transformers format, SAM License) is
  the default; `facebook/sam3.1` is gated and may need an access request.
- Glimmer's tool-call format under vLLM is not documented; the tester drives it with JSON
  actions in plain text, which works on any OpenAI-compatible server.
- The Modal Sandbox path is checked against the Modal 1.6.3 SDK signatures with a fake in
  the tests; the first live run needs `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`.
- WhatsApp: the request shapes follow Meta's Cloud API docs (Graph `v26.0`, the version in
  their current examples; `GRAPH_API_VERSION` changes it). Supabase's free tier serves HTML
  as plain text, which is why the API serves the game pages itself.
- Instagram import: Meta's docs mix Facebook Login (scopes) and Facebook Login for Business
  (a configuration id); both work here (`META_LOGIN_CONFIG_ID`). Confirm which the app uses.
- SAM 3.1 tracking uses transformers' `Sam3VideoModel`; the first live run should confirm
  it loads from `unsloth/sam3.1` (otherwise set `SAM_MODEL_ID=facebook/sam3`).
- Custom mechanics run on players' phones like every game, after the sandboxed play-test;
  the script checker and the page's CSP are the guard. Keep the option experimental until
  real mechanics from the live model have been reviewed.
- MCP: the endpoint has no sign-in, like the upload page; orders are limited per address
  and every video still needs the shop's confirmation. Add OAuth if it is opened widely.
- A code is issued when the phone says it won: the game runs on the phone, so a win cannot
  be proven. Codes are rate-limited and capped, and the shop still decides the discount.
- The Docker image has not been built here (no registry access in this workspace); Render
  builds it from `Dockerfile`.

## Notes for the next session

- Local PostgreSQL 16: `/usr/lib/postgresql/16/bin`, data in `/var/lib/r2p-pg`, run as the
  `postgres` user; databases `reel2play`, `reel2play_test`, `reel2play_e2e`, and
  `reel2play_test2` for a second test run (`TEST_DATABASE_URL`) while the full suite runs:
  the suite drops and recreates its database's schema, so two runs must not share one.
- Playwright is pinned to 1.63.0 to match the Chromium in `/opt/pw-browsers`.
- The API's builder tests compile real games, so build the engine first (`make engine`).
- No git in this workspace by request: hand over with `make zip`.

### Submission preparation (30 October 2026)

- Added `SUBMISSION/` with a timed three-minute demo script, recording plan, submission write-up draft, evidence checklist, and final hand-in checklist.
- The kit explicitly distinguishes implemented architecture from live-provider verification and real-shop evaluation. It does not add fabricated metrics or mark any feature status as done.
- Current feature counts remain those recorded in `FEATURES.md`; update them only after implementation or verification evidence exists.


### Submission rehearsal preparation (30 October 2026)

- Added a Windows PowerShell runbook for a local mock-mode demo, including dependency checks, safe PostgreSQL inspection, migrations, API/web startup, synthetic rehearsal and recording steps. The runbook explicitly avoids database resets or deletion.
- Added a blank rehearsal/evidence log and a claim matrix to distinguish repository implementation from provider execution and live evaluation evidence.
- Updated `HANDOFF.md` to match the current ZIP-only delivery workflow; it no longer instructs this continuation to push commits to GitHub.
- No app code was changed and no automated tests or live-provider calls were run in this preparation phase.
