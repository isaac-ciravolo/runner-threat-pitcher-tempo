# Runner Threat + Pitcher Tempo

Public-data baseball research for a potential SABR submission.

## Research question
Under what conditions does additional attention to a baserunner prevent more expected runs than it costs against the batter?

The first study is narrower: **with a runner on first only, does independently estimated steal threat predict within-pitcher changes in tempo, and does the relationship persist in later games?**

## Status
Project setup only. No analytical findings or validated release-time measurements are included. Originality remains provisional. Earlier exploratory checks must be reproduced and documented before being treated as evidence.

## First milestones
1. Complete the focused literature review and citation tracing.
2. Audit public event timestamps, interruptions, and opportunity reconstruction.
3. Validate event-start intervals against public video before calling them release-to-release tempo.
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

Open `notebooks/01_data_audit.ipynb`. It is an unexecuted starter, not a completed audit. Run notebooks from the repository or notebooks directory. Record exact package versions with `python -m pip freeze > requirements-lock.txt` when the analysis environment is validated.

## Layout
- `docs/`: study design, literature review, and decisions
- `notebooks/`: reproducible audits and analysis
- `data/raw/`: local source downloads (ignored by Git)
- `data/processed/`: local derived tables (ignored by Git)
- `results/`: reviewed tables and figures

## Research safeguards
Use public data only. Freeze predictors before the response interval; never define threat with the same tempo or defensive actions being explained. Include nonattempt opportunities and opportunities ending without another pitch. Separate predictive associations from causal claims. Release-to-release tempo is not set-hold duration or delivery time. Plate location is not target error. Keep raw data, credentials, and notebook outputs out of commits until reviewed.

This project is independent of SIMPSON and xSIMPSON.
