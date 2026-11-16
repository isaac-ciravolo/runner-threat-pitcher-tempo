# Runner Threat + Pitcher Tempo

Public-data baseball research for a potential SABR submission.

## Research question
Under what conditions does additional attention to a baserunner prevent more expected runs than it costs against the batter?

The first feasible study is narrower: **with a runner on first only, does prospectively estimated recorded-steal threat improve prediction of a recorded pitcher pickoff in later games?** Event-start timing is a secondary analysis only if its independent validation gate passes.

## Status
The feasibility, aggregate Savant, runner-control representation, and historical-data audits are complete. The public 2022–2024 development pipeline covers all 7,289 eligible completed games and produces 413,081 first-base-only windows with chronological catcher assignments and forward-only runner counts; 2025 remains schedule-only and locked. The aggregate benchmark closely reproduces Savant only in a prespecified action-free sensitivity, revealing a likely undocumented population rule. The frozen video gate remains **`validation_pending`**: feed timestamps are still **not validated release times**. The initial recorded-steal-attempt baseline has been fit on 2022–2023 and evaluated with fixed choices on 2024. Opening context and runner histories improve prediction over training prevalence, but high predicted probabilities remain overconfident. No pitcher-response, timing-response, or causal model has been fit. Originality remains provisional in light of closely overlapping 2026 work.

See the [data feasibility audit](docs/data_feasibility_audit.md), [video protocol](docs/video_timing_validation_protocol.md), [validation status and manual next steps](docs/video_timing_validation_status.md), [aggregate benchmark report](docs/aggregate_tempo_benchmark_report.md), [runner-control report](docs/runner_control_action_audit_report.md), [opportunity dataset report](docs/opportunity_dataset_report.md), [historical pipeline report](docs/historical_pipeline_report.md), [frozen exploratory plan](docs/exploratory_analysis_plan.md), and [source/claim ledger](docs/source_claim_ledger.md). Raw MLB downloads remain local and ignored.

## First milestones
1. Continue full-text literature review and citation tracing; the closest public sources have been screened and broad novelty is not claimed.
2. ~~Audit public event timestamps, interruptions, and opportunity reconstruction.~~ Completed for the fixed 30-game feasibility sample.
3. Validate the frozen stratified sample against public video before calling event-start intervals release-to-release tempo. Protocol and workflow implemented; genuine annotations pending.
4. Complete: collect the chronological frame and execute the initial recorded-attempt baseline. Monthly forward training threat scores are available; freeze the response-stage protocol before fitting pitcher-response models.
5. Test recorded pitcher-pickoff responses on the locked later-season sample.

See [the study plan](docs/study_plan.md) and [literature checklist](docs/literature_review.md).

## Setup
Use Python 3.11 or later:
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
jupyter lab
```

Reproduce the audit from the repository root:
```bash
python scripts/fetch_audit_sample.py
python -m unittest discover -s tests -v
python -m jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/01_data_audit.ipynb
```

Prepare and run the public-video validation gate:

```bash
python scripts/prepare_video_validation.py
python scripts/discover_public_video.py
python -m unittest discover -s tests -v
python -m jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/02_video_timing_validation.ipynb
```

The discovery script is cache-aware. It logs unavailable, edited, access-limited, and unmatched sources rather than manufacturing annotations. Begin manual review with `results/manual_video_review_queue.csv`.

Reproduce the aggregate Savant benchmark:

```bash
python scripts/fetch_tempo_benchmark.py
python -m unittest discover -s tests -v
python -m jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1200 notebooks/03_aggregate_tempo_benchmark.ipynb
```

The benchmark fetcher is cache-aware and uses the frozen pitcher list in `data/tempo_benchmark_pitchers.csv`. Its raw Savant responses, game logs, and feeds remain ignored.

Reproduce the runner-control audit and opportunity preparation from the existing cache:

```bash
python -m unittest discover -s tests -v
python -m jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1200 notebooks/04_runner_control_action_audit.ipynb
python -m jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1200 notebooks/05_opportunity_dataset.ipynb
```

Build or resume the chronological 2022–2024 development frame:

```bash
python -m scripts.historical_collection schedules
python -m scripts.historical_collection pilot-manifest
python -m scripts.historical_collection collect --pilot
python -m scripts.historical_processing all --pilot
python -m scripts.historical_collection collect
python -m scripts.historical_collection status
python -m scripts.historical_processing all
python -m jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1200 notebooks/06_historical_data_quality.ipynb
```

Collection and per-game parsing are resumable. The development commands default to 2022–2024. The separate 2025 feed command requires `--allow-test-data` and remains unauthorized until the final-test policy is frozen.

On Windows, `py` can replace `python`. The fetch script is cache-aware and uses bounded retries. Exact package versions from the executed notebook are in `results/audit_environment.csv`.

## Layout
- `docs/`: study design, literature review, and decisions
- `notebooks/`: reproducible audits and analysis
- `data/raw/`: local source downloads (ignored by Git)
- `data/processed/`: local derived tables (ignored by Git)
- `results/`: reviewed tables and figures
- `scripts/`: reproducible sample retrieval and audit helpers
- `tests/`: state-reconstruction, interval-preservation, blinding, joining, exclusion, and pending-gate checks

## Research safeguards
Use public data only. Freeze predictors before the response interval; never define threat with the same tempo or defensive actions being explained. Include nonattempt opportunities and opportunities ending without another pitch. Separate predictive associations from causal claims. Release-to-release tempo is not set-hold duration or delivery time. Plate location is not target error. Keep raw data, credentials, and notebook outputs out of commits until reviewed.

This project is independent of SIMPSON and xSIMPSON.

## Initial recorded-attempt baseline

See the [frozen baseline specification](docs/recorded_attempt_baseline_spec.md) and [executed results report](docs/recorded_attempt_baseline_report.md). The user-directed split uses 2022–2023 for fitting and 2024 for fixed evaluation; 2025 stays locked. Reuse the existing processed tables:

```powershell
python -m scripts.recorded_attempt_baseline
```

Compact results are in `results/recorded_attempt_baseline/`; fitted preprocessing/model/calibration bundles and keyed predictions are local ignored files under `data/processed/recorded_attempt_baseline/`. The report documents the exact environment, test commands, sample flow, calibration and uncertainty. No data collection is needed when verified processed tables are present.

## Forward threat and calibration

The [forward-stage report](docs/forward_threat_report.md) documents 211,811 prospective training scores and the training-only decision to retain raw probabilities. See the [frozen protocol](docs/forward_threat_protocol.md) and [executed notebook](notebooks/07_forward_threat_calibration.ipynb). A stronger temporal gate found 61 rows in game 716404 with a resumption date used as game start; these rows are quarantined, and the original baseline's chronology check is now known to be incomplete.

```powershell
python -m scripts.forward_threat
# Alternative: rerun the pipeline and notebook checks in a fresh IPython session
python scripts/execute_forward_threat_notebook.py
```

No pitcher-response model has been fit. 2025 remains closed. Raw and prospectively recalibrated training scores are stored separately; do not backfill training scores using a later-selected calibration policy.
