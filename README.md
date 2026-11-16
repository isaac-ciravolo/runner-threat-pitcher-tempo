# Runner Threat + Pitcher Tempo

Public-data baseball research for a potential SABR submission.

## Research question
Under what conditions does additional attention to a baserunner prevent more expected runs than it costs against the batter?

The first feasible study is narrower: **with a runner on first only, does prospectively estimated recorded-steal threat improve prediction of a recorded pitcher pickoff in later games?** Event-start timing is a secondary analysis only if its independent validation gate passes.

## Status
The feasibility, aggregate Savant, and runner-control representation audits are complete. A one-row-per-window development table and leakage-audited exploratory plan are now frozen, but the 211 cached games are selective and lack complete pre-game runner histories. The aggregate benchmark closely reproduces Savant only in a prespecified action-free sensitivity, revealing a likely undocumented population rule. The frozen video gate remains **`validation_pending`**: feed timestamps are still **not validated release times**. No runner-threat, pitcher-response, timing-response, or causal model has been fit. Originality remains provisional in light of closely overlapping 2026 work.

See the [data feasibility audit](docs/data_feasibility_audit.md), [video protocol](docs/video_timing_validation_protocol.md), [validation status and manual next steps](docs/video_timing_validation_status.md), [aggregate benchmark report](docs/aggregate_tempo_benchmark_report.md), [runner-control report](docs/runner_control_action_audit_report.md), [opportunity dataset report](docs/opportunity_dataset_report.md), [frozen exploratory plan](docs/exploratory_analysis_plan.md), and [source/claim ledger](docs/source_claim_ledger.md). Raw MLB downloads remain local and ignored.

## First milestones
1. Continue full-text literature review and citation tracing; the closest public sources have been screened and broad novelty is not claimed.
2. ~~Audit public event timestamps, interruptions, and opportunity reconstruction.~~ Completed for the fixed 30-game feasibility sample.
3. Validate the frozen stratified sample against public video before calling event-start intervals release-to-release tempo. Protocol and workflow implemented; genuine annotations pending.
4. Collect the complete chronological frame and construct a forward historical recorded-steal-attempt predictor.
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
