# Modal workers

Reel2Play's GPU and sandbox work runs on Modal, paid from the hackathon credits.

| App | File | What it does | Settings it feeds |
| --- | --- | --- | --- |
| `reel2play-sam` | `sam.py` | SAM 3.1: product masks from a text prompt (feature 6) | `SAM_URL` |
| `reel2play-glimmer` | `glimmer.py` | Muse Glimmer behind vLLM's OpenAI-compatible server (feature 25) | `GLIMMER_BASE_URL` |
| `reel2play-playtest` | none to deploy | Sandboxes the API starts for each play-test, with networking blocked (feature 57) | `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, `PLAYTEST_APP` |

## One-time setup

```bash
cd workers/modal
uv sync
uv run modal token new                       # opens the browser to log in to Modal
uv run modal secret create huggingface HF_TOKEN=<your Hugging Face token>
```

Accept the model terms on Hugging Face first if the model page asks for it.

Both endpoints need a **Modal proxy token** (Modal dashboard → Settings → Proxy Auth Tokens,
or `uv run modal workspace proxy-tokens`). Put it in the API settings as
`MODAL_PROXY_TOKEN=<token id>.<token secret>` and use the same value for `GLIMMER_API_KEY`.

## Deploy

```bash
uv run modal deploy sam.py        # prints Sam.segment → SAM_URL and Sam.track → SAM_TRACK_URL
uv run modal deploy glimmer.py    # prints the server URL → GLIMMER_BASE_URL (add /v1)
```

The first request after a deploy downloads the weights into the `huggingface-cache` volume,
so it takes a few minutes; later cold starts are faster. Check both with:

```bash
cd ../../api && AI_MODE=live uv run reel2play model-check
```

## Play-test Sandboxes

Nothing to deploy. The API creates the `reel2play-playtest` app on first use and starts one
Sandbox per test from the official Playwright image (`mcr.microsoft.com/playwright/python:v1.63.0-noble`)
with `block_network=True`, then runs `api/src/reel2play/playtest/harness.py` inside it and
talks to it over stdin and stdout. The API needs a Modal **API token** for this (Modal
dashboard → Settings → API Tokens): set `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` on Render.
Without them, production refuses to test games; development and CI use a local Chromium.

## Tests

`uv run pytest` checks the request and response code in `sam_core.py` without a GPU.
