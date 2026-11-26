# TriNetra-Link: Next Steps

> **Updated:** 2026-11-14 · **Watermark:** all synthetic outputs carry `SYNTHETIC DRY RUN — NOT A RESULT`

## Done

- **Steps 1 and 2 are complete** (commit `1bcb31a`): B1 as CP4-only practice, B2 as endpoints, `--mask full|field`, subgroup tables, layered seals (`reconcile/seals.py`, `breach_depth`), generator, viewer badges, No Layered Seals ablation, seal tests.
- **Review fixes** (2026-11-14): see `STATUS.md` §4. 124 tests pass; ruff is clean; CI runs `pytest tests/`.

The software is ready for data collection. Until the physical journeys exist, `PLACEHOLDER=1 bash reproduce.sh` runs the complete pipeline on 120 simulated placeholder journeys (watermarked, never results). **No physical result exists until the steps below are done**; the captured journeys then go to the real paths (`data/trinetra_store.sqlite`, `data/derived/`, `data/restricted/`) and `bash reproduce.sh` runs unchanged.

## Physical study (team work, in order)

1. **Gate G-2 — truth commitment.** Run `python scripts/make_staging_kit.py` to regenerate the 120-journey assignment, then `trinetra truth commit --salt <secret>`; commit the manifest *before* any staging.
2. **Gate G-4 — scales.** For each scale: ≥ 3 loads × 30 readings with `trinetra scale record`, then `trinetra scale fit`; commit `data/derived/scales.json`.
3. **Gate G-3 — pilot.** Stage and capture 10 pilot journeys through the web capture page (`trinetra serve`, with `DEVICE_INGEST_TOKEN` set). Export them and run `trinetra pilot check --fixtures <pilot.json>`; freeze the quality floors.
4. **Main study.** Stage and capture the 120 journeys per `docs/staging_SOP.md` and `docs/capture_SOP.md`; `trinetra split --seed 42`.
5. **Fit and evaluate.** `bash reproduce.sh` (fits θ on the 24 calibration journeys, then runs E1 full/field, E2, E3 on the 96 test journeys).
6. **B4.** Removed (decision D-07). Nothing to run.
7. **Datasheet.** Fill the counts and capture dates in `docs/datasheet.md` from the actual data.

## Open decisions for the team

- **Doorstep substitution label.** The protocol scores it as S1. Confirm or amend before G-2.
- **Visual reconciler.** The simulation study shows the preregistered global 1 − SSIM score responds to pose changes more than to small tamper marks. A registered local scorer is implemented (`--visual-method local`). Adopting it for the physical study needs a protocol amendment before G-2; its threshold is then fitted on the calibration split.
- **Android app.** Not wired to the ingest API. Either wire and test it before the pilot or state in the paper that capture used the web page.
- **Repo layout.** `android/` and `backend/` (Java) are outside the study; consider moving them under `legacy/` once someone can rebuild them.

## Simulation study

Done (see `STATUS.md` §5 and the paper). Re-run with `python -m trinetra_link.sim.run_study main --out results/sim`, then the `sweep` points listed in `trinetra_link/sim/run_study.py`.

## Future work (not started)

- Conformal prediction sets and selective conformal abstention (Experiments E4–E5).

## Running tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q        # 124 passed
ruff check .
```
