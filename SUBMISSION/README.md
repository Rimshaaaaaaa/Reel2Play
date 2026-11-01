# Reel2Play — Hackathon Submission Kit

**Built with Muse Spark Open.**

This folder is a submission-preparation kit, not proof that live services, real-shop evaluation, or every integration has been verified. Replace every bracketed placeholder with evidence from the actual demo. Do not publish credentials, private shop videos, consent records, phone numbers, or personal data.

## Contents

- `DEMO_SCRIPT.md` — a timed three-minute demo narrative and exact screen sequence.
- `RECORDING_PLAN.md` — recording checklist, shot list, fallback plan, and quality checks.
- `SUBMISSION_WRITEUP.md` — draft project description and technical summary; clearly separates implemented architecture from live verification still required.
- `EVIDENCE_CHECKLIST.md` — evidence needed to support model, safety, evaluation, and feature claims.
- `FINAL_CHECKLIST.md` — deadline-aware hand-in checklist.
- `WINDOWS_DEMO_RUNBOOK.md` — PowerShell steps to start a local mock-mode demo without deleting databases.
- `REHEARSAL_LOG.md` — blank evidence log to complete only after an actual run.
- `CLAIM_MATRIX.md` — safe demo wording and the evidence needed for stronger claims.

## Before using this kit

1. Read the current `FEATURES.md`, `PROGRESS.md`, and `HANDOFF.md`.
2. On Windows, follow `WINDOWS_DEMO_RUNBOOK.md`; keep the default mock mode unless live providers have been verified.
3. Complete `REHEARSAL_LOG.md` from the actual run and use `CLAIM_MATRIX.md` before recording narration.
2. Confirm which providers are actually configured and which ran during the recording.
3. Use only synthetic demo media or shop-owned media with documented permission.
4. Keep synthetic results labelled synthetic. Do not present them as customer or real-world results.
5. Remove placeholders and unsupported claims before submission.
6. Confirm the hackathon portal's current rules, track requirements, team limit, and submission fields directly before submitting.

## Current known limitations to disclose

- `FEATURES.md` currently records 34 features as `done`, 29 as `needs-key`, and 2 as `partial`.
- The 30-video real-shop evaluation and populated evaluation gallery are still partial. The example manifest contains placeholders; CI uses synthetic videos.
- Live model/provider execution, Modal deployment, and third-party integrations must be verified with the actual configured credentials and deployed services. Code presence or mock tests are not live-provider proof.
- The local automated test suite was intentionally not rerun during this continuation. Do not state that this ZIP passed a fresh full test run.

---

Built with Muse Spark Open.
