# Runner Threat + Pitcher Tempo

Public-data baseball research for a potential SABR submission.

## Research question
Under what conditions does additional attention to a baserunner prevent more expected runs than it costs against the batter?

The first study is narrower: **with a runner on first only, does independently estimated steal threat predict within-pitcher changes in tempo, and does the relationship persist in later games?**

## Status
The first reproducible 30-game public-data feasibility audit is complete. The feed supports structural event and provisional opportunity reconstruction, but its timestamps are **not validated release times**. No runner-threat model or causal analysis has been fit. Originality remains provisional.

See the [data feasibility audit](docs/data_feasibility_audit.md), [sample manifest](data/audit_sample_manifest.csv), and [source/claim ledger](docs/source_claim_ledger.md). Raw MLB downloads remain local and ignored.

## First milestones
1. Complete the focused literature review and citation tracing.
2. ~~Audit public event timestamps, interruptions, and opportunity reconstruction.~~ Completed for the fixed 30-game feasibility sample.
3. Validate approximately 100 stratified event-start intervals against public video before calling them release-to-release tempo.
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

On Windows, `py` can replace `python`. The fetch script is cache-aware and uses bounded retries. Exact package versions from the executed notebook are in `results/audit_environment.csv`.

## Layout
- `docs/`: study design, literature review, and decisions
- `notebooks/`: reproducible audits and analysis
- `data/raw/`: local source downloads (ignored by Git)
- `data/processed/`: local derived tables (ignored by Git)
- `results/`: reviewed tables and figures
- `scripts/`: reproducible sample retrieval and audit helpers
- `tests/`: small state-reconstruction and interval-preservation checks

## Research safeguards
Use public data only. Freeze predictors before the response interval; never define threat with the same tempo or defensive actions being explained. Include nonattempt opportunities and opportunities ending without another pitch. Separate predictive associations from causal claims. Release-to-release tempo is not set-hold duration or delivery time. Plate location is not target error. Keep raw data, credentials, and notebook outputs out of commits until reviewed.

This project is independent of SIMPSON and xSIMPSON.
