# Initial recorded-steal-attempt baseline

Executed 2026-11-15 from checkpoint `4af9c1d`. Opening-time context and completion-time-aware runner histories improve recorded-attempt prediction in 2024 relative to pooled training prevalence. The primary separate-history model is not well calibrated across the entire probability range. These results support continued predictive research, not a recommendation to increase or decrease pitcher attention.

## Checkpoint and sample

The initial Git worktree was clean at the reported commit. All three processed season tables were present under `data/processed/historical/development/`; no collection or rebuilding was required. Existing collection manifests report complete coverage of 7,289 eligible games, zero eligible missing/quarantined feeds and one excluded canceled game. The saved QA notebook has nine executed code cells and no error outputs. All 22 historical table invariants were rerun and passed. Raw feeds were reused through the processed tables, not independently re-downloaded or rehashed in this task; SHA256 values of all model input tables are saved in `results/recorded_attempt_baseline/provenance.json`.

| season | windows | games | attempts | terminal | runner_change | history_eligible | excluded_model_rows | attempt_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2022 | 137732 | 2430 | 1797 | 3135 | 2769 | 134963 | 0 | 0.013047 |
| 2023 | 138862 | 2430 | 2377 | 3828 | 2552 | 136310 | 0 | 0.017118 |
| 2024 | 136487 | 2429 | 2462 | 3911 | 2532 | 133955 | 0 | 0.018038 |

All rows remain eligible for prediction, including terminal windows and windows with runner changes. The target is any feed-recorded attempt within the frozen window; it is not necessarily an attempt by the opening runner after a substitution. History counting retains the existing identity-change exclusions. No model-row exclusions or missing-history imputations were needed. Context has no ordinary missing values; the two rule-limit fields are structurally absent in all 2022 rows and are represented as zero with a rule-era indicator. Cold starts receive a training-prevalence-centered rate and an explicit zero-exposure indicator, separately by history regime.

## Frozen design and deviations

`docs/recorded_attempt_baseline_spec.md` was written before fitting and new 2024 outcome inspection. As explicitly requested, 2022 joins 2023 for fitting instead of serving only as history. The previously inspected 2024 development season receives a fixed held-out evaluation, with no tuning or recalibration. It is not an untouched final test. All four models and hyperparameters were fixed; separate-history logistic was declared primary. Calibration is identity. The internal chronological diagnostic fits 206,987 windows (3,008 attempts) from games completed before July 1, 2023 UTC and scores 69,165 windows (1,159 attempts) from games starting on/after that cutoff. The 442 windows in games crossing the cutoff are omitted only from that diagnostic. Final models fit all 276,594 windows from 2022–2023 (4,174 attempts).

The planned history comparison is implemented as distinct pre-2023 and post-2023 blocks versus post-2023 history alone, not one stationary pooled runner rate. This milestone omits success-history features to focus on attempts, and omits identities, score and previous-pitch predictors. No coefficients or individual player rankings are interpreted. The model does not produce training scores suitable for subsequent pitcher-response estimation; that stage still requires rolling out-of-sample threat scores.

## Held-out 2024 performance

Lower log loss and Brier are better; higher average precision is better.

| model | log_loss | brier | average_precision | mean_prediction | calibration_intercept | calibration_slope |
| --- | --- | --- | --- | --- | --- | --- |
| constant | 0.090578 | 0.017722 | 0.018038 | 0.015091 | nan | nan |
| context | 0.080335 | 0.017253 | 0.069794 | 0.017286 | 0.081863 | 1.010724 |
| post_history | 0.076763 | 0.017297 | 0.092239 | 0.017795 | -0.469837 | 0.850706 |
| separate_history | 0.076797 | 0.017221 | 0.087251 | 0.017716 | -0.409529 | 0.867768 |

The primary model has log loss 0.076797 versus 0.090578 for the constant baseline, a 15.2% reduction. Its Brier score is 0.017221 versus 0.017722, a 2.8% reduction. Average precision is 0.087251 versus prevalence 0.018038. The post-only variant has slightly better log loss and average precision, but worse Brier than the primary model and even the context-only model. There is no uniformly superior history variant, and these 2024 comparisons do not change the frozen primary designation.

Whole-game bootstrap intervals use 200 resamples, seed 20261115, with fixed fitted models. Primary log-loss 95% interval: [0.074271, 0.079695]; Brier: [0.016577, 0.017974]; average precision: [0.081395, 0.094780]. Paired differences from the constant baseline are [-0.014985, -0.012822], [-0.000614, -0.000378], and [0.063465, 0.076278], respectively. These intervals condition on the training fit; they do not capture refitting uncertainty, cross-game player dependence, measurement error or unobserved distribution shifts. All model/diagnostic intervals are in `game_bootstrap.csv`.

## Primary calibration

| bin | n | attempts | mean_prediction | observed_rate |
| --- | --- | --- | --- | --- |
| (-0.001, 0.005] | 46111 | 33 | 0.001162 | 0.000716 |
| (0.005, 0.01] | 30772 | 219 | 0.007238 | 0.007117 |
| (0.01, 0.02] | 29816 | 508 | 0.014227 | 0.017038 |
| (0.02, 0.05] | 19713 | 765 | 0.030484 | 0.038807 |
| (0.05, 0.1] | 6319 | 463 | 0.068671 | 0.073271 |
| (0.1, 0.2] | 2697 | 301 | 0.137564 | 0.111605 |
| (0.2, 1.0] | 1059 | 173 | 0.294291 | 0.163362 |

The overall mean prediction (1.772%) is close to the observed 1.804%, but this conceals overprediction at high scores and underprediction in intermediate bins. In the >20% bin, 1,059 windows contain 173 attempts: 29.4% mean prediction versus 16.3% observed. The diagnostic calibration slope is 0.868. This diagnostic fit was not applied to predictions. Subgroup tables include both windows and attempts for opening disengagements, history depth, terminal status and runner changes. These are audits, not reasons to filter the denominator or rank individual players.

## Reproduction and artifacts

Run from the repository root using the installed `python` (Python 3.14.4, pandas 3.0.2, NumPy 2.4.4, scikit-learn 1.8.0):

```powershell
python -m pip install -r requirements.txt
New-Item -ItemType Directory -Force data/processed/test_tmp | Out-Null
$env:TEMP = (Resolve-Path data/processed/test_tmp).Path
$env:TMP = $env:TEMP
python -m unittest discover -s tests -q
python -c "from scripts.historical_processing import validate_historical_outputs; checks=validate_historical_outputs((2022,2023,2024)); assert checks.passed.all(); print(checks)"
python -m scripts.recorded_attempt_baseline
```

The first attempted `py -3` run selected Python 3.12 without dependencies. The existing `python` installation supplied the required packages. A sandbox temporary-directory permission error in one original test was resolved by the workspace-local TEMP/TMP settings above. No permission escalation or full rebuild was needed.

- Frozen definitions: `docs/recorded_attempt_baseline_spec.md`; deviation entry: `docs/decision_log.md`.
- Reproducible implementation: `scripts/recorded_attempt_baseline.py`; targeted tests: `tests/test_recorded_attempt_baseline.py`.
- Compact results: `results/recorded_attempt_baseline/{sample_flow,context_missingness,metrics,calibration,subgroups,game_bootstrap}.csv` and `provenance.json`.
- Local ignored artifacts: `data/processed/recorded_attempt_baseline/` contains four fitted joblib bundles (fitted preprocessing, training prior, estimator and identity-calibration policy), plus chronological diagnostic and held-out prediction tables keyed by opportunity/game. Recreate these from the script on another checkout.

Verification: 34 repository tests passed; 22 historical invariants passed; reloaded model predictions agree with saved predictions to numerical precision; every calibration and subgroup table sums to its evaluation denominator and positive count; the frozen spec hash matches provenance. No blockers remain for this baseline. Files are saved but not committed.

## Evidence limits and originality

The existing literature review and source/claim ledger identify Loughin and Bargen, Price, Powers, Melville and colleagues, the Yale pitch-selection analysis, and Smith's timing study as overlapping precedents. This run adds an executed public-data chronological benchmark; it does not establish novelty. Full-text method comparison and reference tracing remain required before a SABR originality claim, as documented in `docs/literature_review.md`. No new literature-completeness claim is made here.

The public-feed label does not verify real-world steal-action completeness. Histories begin in 2022. Pitchers and runners choose actions jointly, so predictive associations are not causal effects. 2025 feeds remain unopened and the video gate remains `validation_pending`. Steal success, pitcher response, tempo and expected-run trade-offs remain later stages.

## Subsequent chronology finding

The forward-stage audit found 61 rows in game 716404 whose feed header start is a scheduled resumption after the recorded completion timestamp. The original baseline fit included those rows, so its chronology verification was incomplete. The original results above remain preserved for provenance; the subsequent stage quarantines these rows and refits the same primary model. See [the forward-stage report](forward_threat_report.md) for corrected population accounting and development metrics.
