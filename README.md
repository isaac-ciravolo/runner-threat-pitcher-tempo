# Runner Threat + Pitcher Tempo

**Current research gate (2026-11-16):** The G3 completed-play reconstruction and histories pass all-game source checks and independent history validation. Corrected baseline, forward-threat and pitcher-response fits are verified. The original within-play results remain withdrawn. 2025 remains closed.

Public-data baseball research for a potential SABR submission.

## Research question
Under what conditions does additional attention to a baserunner prevent more expected runs than it costs against the batter?

The first feasible study is narrower: **with a runner on first only, does prospectively estimated recorded-steal threat improve prediction of a recorded pitcher pickoff in later games?** Event-start timing is a secondary analysis only if its independent validation gate passes.

## Status
The corrected development pipeline covers 7,289 games and 403,611 first-base-only windows from 2022–2024, including 8,141 recorded-attempt windows. It groups linked outcome annotations with their parent event, recovers explicit runner movement evidence, and freezes pitcher identities and histories before each response. Independent history checks pass 5,562 equalities across 35 reference games.

The corrected recorded-attempt baseline and monthly forward scores are verified. Training-only recalibration improves 2024 development calibration, but high-probability overconfidence remains. The frozen pitcher-response comparison is complete: adding raw forward threat reduces 2024 development log loss by 4.58%, with improvement across the prespecified sensitivities. Response calibration still shows overconfidence. All findings remain predictive associations with recorded feed events.

Video validation is pending: the updated blinded review sample contains 229 unreviewed windows and zero genuine annotations. Feed event timestamps are not validated release times. Conditional success and expected-run work remain deferred under the repair amendment. The outcome audit distinguishes SB/CS credit, error-assisted advancement and subsequent outs. Originality remains provisional; closest-work methods and access limitations are documented.

Current evidence: [history audit](docs/grouped_history_report.md), [attempt baseline](docs/grouped_baseline_report.md), [forward scoring](docs/grouped_forward_report.md), [pitcher response](docs/grouped_response_report.md), [conditional-outcome review](docs/grouped_success_report.md), [video readiness](docs/grouped_video_readiness.md), and [code audit](docs/grouped_code_audit.md). Earlier reports remain archived with superseded-definition notices.

See the [data feasibility audit](docs/data_feasibility_audit.md), [video protocol](docs/video_timing_validation_protocol.md), [validation status and manual next steps](docs/video_timing_validation_status.md), [aggregate benchmark report](docs/aggregate_tempo_benchmark_report.md), [runner-control report](docs/runner_control_action_audit_report.md), [opportunity dataset report](docs/opportunity_dataset_report.md), [historical pipeline report](docs/historical_pipeline_report.md), [frozen exploratory plan](docs/exploratory_analysis_plan.md), and [source/claim ledger](docs/source_claim_ledger.md). Raw MLB downloads remain local and ignored.

## Research gates
1. Continue full-text literature review and citation tracing before any novelty claim.
2. Completed: full G3 reconstruction, opening identities, independent histories and corrected attempt/forward fits.
3. Completed: frozen recorded pitcher-pickoff response comparison, all sensitivities, saved-model verification and reviewed reports.
4. Current next step: [cross-source coverage/reconciliation and measurement-error sensitivity](docs/no_video_validation_amendment.md). Available video controls make annotation impractical; retain the unreviewed sample and defer release-tempo and action-completeness claims.
5. Freeze the full final-test policy after the measurement and literature review. Opening 2025 feeds still requires separate authorization; this workflow does not unlock them.

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

Collection and per-game parsing are resumable. The development commands default to 2022–2024. The separate 2025 feed command requires `--allow-test-data` and remains unauthorized until the final-test policy is frozen and Isaac explicitly authorizes opening it.

On Windows, `py` can replace `python`. The fetch script is cache-aware and uses bounded retries. Exact package versions from the executed notebook are in `results/audit_environment.csv`.

## Corrected G3 analysis

From the repository root, with the verified local 2022–2024 source cache and reconstruction artifacts available:

```bash
python -m scripts.grouped_histories
python -m scripts.grouped_models baseline
python -m scripts.verify_grouped_models baseline
python -m scripts.grouped_models forward
python -m scripts.verify_grouped_models forward
python -m scripts.grouped_models response
python -m scripts.verify_grouped_models response
python -m scripts.audit_grouped_success
python -m scripts.prepare_grouped_video_queue
python -m unittest discover -s tests -q
```

Review each stage before proceeding. Notebooks 10–13 read checksum-verified current runs; execute them with `python -m scripts.execute_forward_threat_notebook notebooks/<name>.ipynb`. The immutable result manifests bind local model bundles and predictions to their published tables. Local raw feeds and processed prediction tables are intentionally not committed. Full reconstruction and its validation prerequisites are documented in the [repair amendment](docs/grouped_event_repair_protocol.md); future caches include the migration driver in their dependency signature.

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

The first recorded-pickoff response analysis is complete. 2025 remains closed. Raw and prospectively recalibrated training scores are stored separately; do not backfill training scores using a later-selected calibration policy.

## Corrected chronology handoff

The [chronology repair report](docs/chronology_repair_report.md) supersedes the v1 threat handoff. All 7,289 cached feeds passed checksum review; corrected histories change 1,253 windows across 55 games. Separate v2 outputs restore the 61 quarantined rows and supply 211,818 prospective training scores. Raw probabilities remain selected. See the [executed audit notebook](notebooks/08_chronology_repair.ipynb) and [frozen pitcher-response protocol](docs/pitcher_response_protocol.md). Conservative rain buffers and anomalous timestamp treatment remain explicit qualifications; 2025 stays closed.

## Pipeline integrity

Forward runs now publish versioned results and models through a single completion pointer. Use `scripts.artifact_runs.resolve_run` to locate the latest validated run; flat filenames remain archived legacy snapshots. See [validation, publication and provenance](docs/pipeline_integrity.md) for the reader API and failure behavior. Rebuilds enforce the audited source snapshot, and runtime integrity gates remain active under Python optimization.

## Recorded pitcher response

See the [executed response report](docs/pitcher_response_report.md) and [QA notebook](notebooks/09_pitcher_response.ipynb). Forward threat improves 2024 recorded-pickoff prediction, with explicit dependence sensitivities and measurement limits. The 179-window video queue remains unreviewed; 2025 remains closed.
