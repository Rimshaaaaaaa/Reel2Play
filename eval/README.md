# Evaluation

The evaluation runs the whole pipeline on 30 real product videos, five from each of six
kinds of business (clothing, bakeries and food, shoes, cosmetics, phone accessories, home
decor), and reports the build spec's measures:

| Measure | How it is counted |
| --- | --- |
| First-try success | Share of videos whose first game passes every gate with no fixes |
| Success after fixes | Share that passes within three fix rounds |
| Time to ad | Median minutes from upload to a passed game |
| Blind preference | Share of people who pick the game over a still ad of the same product (`/compare`) |
| Completion | Share of plays on the hosted pages that reach the end card |

It also reports how often the director read the kind of business correctly, and what the
run cost in model calls.

## Files

| File | What it is |
| --- | --- |
| `videos.example.json` | The 30 slots to fill in. Copy it to `videos.json`. |
| `videos/` | The videos themselves. Shops' own footage: kept on your machine, never committed or zipped. |
| `ci.json` | Three synthetic videos on the mock model, run by CI to check the harness works. Its numbers say nothing about real shops. |
| `results/` | One folder per run: `results.json` and `report.md`. Commit the real run's folder. |

## Running it

Only videos a shop agreed to, or that the team filmed; `consent` in the manifest says who
agreed and when.

```bash
cd api
AI_MODE=live uv run reel2play eval run ../eval/videos.json --gallery
```

`--gallery` puts every published game in the public gallery. Preference and completion come
from visitors after the run; to refresh them later:

```bash
uv run reel2play eval report ../eval/results/<run folder>/results.json
```

On the mock model (no keys), `uv run reel2play eval run ../eval/ci.json` runs in a few
minutes.

Built with Muse Spark Open.

## Before a real evaluation

1. Obtain permission for processing each video. Obtain separate approval before making any
   resulting game or preview public. See [`CONSENT.md`](CONSENT.md) for a private record
   checklist; keep completed permission records outside the repository.
2. Collect exactly five videos for each of the six business kinds listed in the build spec:
   clothing, bakery/food, shoes, cosmetics, phone accessories, and home decor.
3. Copy `videos.example.json` to `videos.json`, replace every placeholder, and check that
   each `file` points to a real local video under the project directory. Do not put private
   contact information in `consent` or public reports.
4. Keep original audio muted. Confirm rights to the footage and product assets, and ensure
   bystander faces are blurred or excluded by the safe fallback before publication.
5. Run the real evaluation only with the live provider configuration. The CI manifest is
   synthetic and uses recorded mock answers; its results are a harness check, not evidence
   of real-shop performance.
6. Review each generated game and preview with the shop before adding it to the public gallery.
   `--gallery` adds successfully published ads automatically, so use it only when that
   publication approval has been obtained for every video in that run. Otherwise run without
   `--gallery` and curate approved ads later with `reel2play gallery add <ad-id>`.
7. Refresh the report after real visitors have generated completion and blind-preference data.
   Until then those visitor measures correctly remain `not yet`.

The full real evaluation target is 30 videos (five per business kind). Do not invent missing
videos, consent, visitor votes, or performance numbers to fill the report.
