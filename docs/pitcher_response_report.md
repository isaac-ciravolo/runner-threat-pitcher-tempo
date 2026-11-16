# Recorded pitcher-pickoff response results

**Superseding audit, 2026-11-16:** Prospective interpretation is suspended. See action_pitch_link_audit_report.md: the input threat target assigns pitch-associated steal records after their physical pitch. Metrics below describe the archived implementation, not a validated prospective result.

Executed 2026-11-16 under the frozen response protocol. Forward runner threat improves recorded-pickoff prediction in previously inspected 2024 development games beyond the specified opening context and regularized pitcher/catcher identity terms. This is incremental predictive association, not evidence that throwing over prevents runs or that runner threat causes a response.

## Population and design

Primary fitting uses all 138,862 2023 windows from 2,430 games, with 7,479 recorded-pitcher-pickoff windows. Evaluation retains 136,487 2024 windows from 2,429 games, including 7,633 positives, 3,911 terminal windows and 2,532 runner-change windows. No primary rows are removed for observed response actions. The chronological diagnostic fits 69,255 windows and scores 68,864; 743 windows in 12 boundary-crossing games are omitted from that diagnostic but retained in the final fit. Unknown-initiator and catcher records are reported separately in sample_flow.csv. Metrics' `attempts` column denotes binary response-positive windows here, not steal attempts.

Threat inputs are keyed one-to-one to the verified chronology-v2 scores. Training scores remain forward predictions; 2024 threat parameters use only 2022–2023. The opening-feature allowlist, C=1, preprocessing, sensitivities and 500 paired bootstrap resamples were fixed before response fitting. No response recalibration or 2024 tuning was performed. Game, pitcher and runner cluster intervals condition on fitted models and are not a full crossed-cluster variance estimate.

## Primary metrics

| split | model | n | attempts | log_loss | brier | average_precision | calibration_intercept | calibration_slope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| diagnostic_2023 | constant | 68864 | 3598 | 0.205186 | 0.049529 | 0.052248 | nan | nan |
| diagnostic_2023 | context | 68864 | 3598 | 0.202108 | 0.049218 | 0.084093 | -1.055255 | 0.633912 |
| diagnostic_2023 | context_threat | 68864 | 3598 | 0.192757 | 0.048288 | 0.121026 | -0.565115 | 0.804489 |
| development_2024 | constant | 136487 | 7633 | 0.215645 | 0.052801 | 0.055925 | nan | nan |
| development_2024 | context | 136487 | 7633 | 0.214467 | 0.052669 | 0.078172 | -1.180476 | 0.559280 |
| development_2024 | context_threat | 136487 | 7633 | 0.205546 | 0.051807 | 0.114492 | -0.612648 | 0.747655 |

The 2024 log-loss reduction is approximately 4.16% relative to context alone. Brier improves from 0.052669 to 0.051807, and AP from 0.078172 to 0.114492. All three dependence sensitivities support the same direction; their differing widths remain relevant. No individual player rankings or coefficients are interpreted.

| cluster | metric | delta | lower | upper |
| --- | --- | --- | --- | --- |
| game_pk | log_loss | -0.008921 | -0.009774 | -0.008056 |
| game_pk | brier | -0.000862 | -0.001050 | -0.000684 |
| game_pk | average_precision | 0.036320 | 0.033158 | 0.040138 |
| pitcher_id | log_loss | -0.008921 | -0.009913 | -0.007847 |
| pitcher_id | brier | -0.000862 | -0.001043 | -0.000657 |
| pitcher_id | average_precision | 0.036320 | 0.032135 | 0.040286 |
| runner_id | log_loss | -0.008921 | -0.010683 | -0.007011 |
| runner_id | brier | -0.000862 | -0.001154 | -0.000520 |
| runner_id | average_precision | 0.036320 | 0.029476 | 0.043160 |

## Prespecified sensitivities

| variant | model | n | attempts | log_loss | brier | average_precision |
| --- | --- | --- | --- | --- | --- | --- |
| primary | context | 136487 | 7633 | 0.214467 | 0.052669 | 0.078172 |
| primary | context_threat | 136487 | 7633 | 0.205546 | 0.051807 | 0.114492 |
| calibrated_threat | context | 136487 | 7633 | 0.214467 | 0.052669 | 0.078172 |
| calibrated_threat | context_threat | 136487 | 7633 | 0.205789 | 0.051804 | 0.113903 |
| history_depth | context | 136487 | 7633 | 0.213430 | 0.052579 | 0.082404 |
| history_depth | context_threat | 136487 | 7633 | 0.205350 | 0.051846 | 0.115418 |
| known_initiator | context | 136478 | 7625 | 0.214448 | 0.052637 | 0.077972 |
| known_initiator | context_threat | 136478 | 7625 | 0.205269 | 0.051757 | 0.114887 |

All sensitivity estimates and intervals remain in the published tables; none replaces the primary analysis. The known-initiator sensitivity removes nine 2024 windows, eight of which also contain a recorded pitcher pickoff, and explicitly changes the population using response information. The history-depth sensitivity assesses whether exposure depth alone accounts for the threat contribution. The score itself contains context and history, so this is not a clean causal decomposition into runner skill.

## Code and research audit

The 65-test suite passes, including response-field exclusion, unseen identities and context/threat separation. Every fitted response bundle reproduces its saved predictions exactly. The independent chronology verifier was rerun: 5,364 history equalities and all 211,818 forward training/136,487 development scores pass. The executed four-cell notebook validates complete result tables and calibration/subgroup accounting. Staged publication and artifact hashes protect completed outputs. The post-run review also added denominator reconciliation to the publication validator; this stronger validator passes on the completed run and was executed by the notebook. Statistical choices did not change.

Remaining limitations include final-feed revision timing, conservative rain buffers, the isolated anomalous timestamp, unverified real-world action completeness, omitted score/handedness/previous-pitch fields, residual repeated-player dependence, and previously inspected 2024 data. Passing tests is evidence for the checked implementation, not a certification of causal validity or complete measurement.

## Measurement queue and reproduction

A seeded stratified queue contains 179 unreviewed windows in 43 strata, with selection probabilities recorded. It covers positive and negative labels, pre-first-event/other openings, terminal windows, catcher/unknown-initiator records and action interruptions. All annotation fields are blank. This is sampling preparation, not completed video validation.

```powershell
python -m scripts.pitcher_response
python scripts/execute_forward_threat_notebook.py notebooks/09_pitcher_response.ipynb
python -m scripts.prepare_response_video_queue
```

The queue command refuses to overwrite existing annotations. Resolve the current result/model pair with `resolve_run(ROOT/'results/pitcher_response', ROOT/'data/processed/pitcher_response')`. Compact tables and provenance are committed under the referenced results run; models and keyed predictions remain ignored local artifacts. Full analysis takes several minutes, primarily for clustered resampling.

2025 remains closed. The next stage is full-text prior-work comparison and honest video-source/annotation assessment. Conditional success, tempo and expected-run trade-offs remain separate later work.
