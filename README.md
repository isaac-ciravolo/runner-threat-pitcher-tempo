# Runner Threat + Pitcher Tempo

Public-data baseball research for a potential SABR submission.

## Research question
Under what conditions does additional attention to a baserunner prevent more expected runs than it costs against the batter?

The first study is narrower: **with a runner on first only, does independently estimated steal threat predict within-pitcher changes in tempo, and does the relationship persist in later games?**

## Status
The first reproducible 30-game public-data feasibility audit is complete, the public-video validation gate is implemented, and a separate aggregate Baseball Savant benchmark has been executed. The aggregate benchmark closely reproduces Savant only in a prespecified action-free sensitivity, revealing a likely undocumented population rule that still needs investigation. The frozen video gate remains **`validation_pending`**: feed timestamps are still **not validated release times**. No runner-threat model or causal analysis has been fit. Originality remains provisional.

See the [data feasibility audit](docs/data_feasibility_audit.md), [video protocol](docs/video_timing_validation_protocol.md), [validation status and manual next steps](docs/video_timing_validation_status.md), [aggregate benchmark report](docs/aggregate_tempo_benchmark_report.md), [sample manifest](data/audit_sample_manifest.csv), and [source/claim ledger](docs/source_claim_ledger.md). Raw MLB downloads remain local and ignored.

## First milestones
1. Complete the focused literature review and citation tracing.
2. ~~Audit public event timestamps, interruptions, and opportunity reconstruction.~~ Completed for the fixed 30-game feasibility sample.
3. Validate the frozen stratified sample against public video before calling event-start intervals release-to-release tempo. Protocol and workflow implemented; genuine annotations pending.
4. Construct a simple historical recorded-steal-attempt predictor.
5. Test pitcher responses on a chronological held-out sample.

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
