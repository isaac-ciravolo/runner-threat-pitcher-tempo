# Forward threat and calibration results

Executed 2026-11-15. Monthly forward prediction produced 211,811 scored training windows. Recalibration did not meet the frozen training-period adoption rule, so the selected policy remains identity (raw probabilities). This is a useful negative finding: simple recalibration cannot be assumed to improve both scoring rules prospectively. The scores are now available for a separately frozen pitcher-response analysis; they are not calibrated strategic recommendations.

## Protocol and population

The protocol in `docs/forward_threat_protocol.md` was written before execution. It reuses the declared primary separate-history model, original window denominator and opening-time predictor allowlist. Monthly base fits use only games completed strictly before the monthly origin. Calibration uses only earlier forward predictions from completed games in the same rule era. Both preprocessing and base parameters are fit from earlier data only. Monthly historical features can still update after earlier games complete. No current-game labels enter either fitted component.

Of 276,594 training windows, 64,722 April–June 2022 windows are model warmup and 61 windows are quarantined for inconsistent timestamps. The 211,811 scored windows comprise 73,010 in 2022 (953 attempts) and 138,801 in 2023 (2,376 attempts). They retain 5,465 terminal windows and 3,985 runner-change windows. The score file preserves all 276,594 rows with explicit unscored status rather than dropping them. Of the scored rows, 46,514 use identity fallback because earlier same-era calibration data have fewer than 200 attempts; the remaining 165,297 receive prospective logistic recalibration. Both raw and prospective-calibration columns are saved.

## Chronology defect and amendment

The first execution stopped at a game-overlap assertion before selection or 2024 scoring. Game 716404 has `gameData.datetime.dateTime` equal to its scheduled resumption (2023-10-02 17:10 UTC), while its last recorded completion timestamp is 2023-09-29 01:22 UTC. The cached feed explicitly carries original/resumed-from date 2023-09-28 and resume date 2023-10-02. This confirms the header timestamp is not a reliable original game-start field for that game; merely parsing it as a timestamp was insufficient.

A timestamp-only audit of all three tables found exactly 61 completion-before-start rows, all in that game. They include one attempt, two terminal windows and one runner-change window. These rows are quarantined from all new fits and scores and remain in `chronology_quarantine.csv` and the full training-score table. Final 2024 scoring refits on 276,533 valid training rows, so it differs slightly from the original baseline. The original artifacts are preserved, but their reported chronology gate was incomplete. Other games retain the existing completion-time-based histories; this stage does not independently revalidate every feed timestamp or rewrite upstream histories. Restoring the quarantined rows requires reconstructing their actual opening history with a corrected start-time policy.

## Training-only calibration decision

The prespecified selection set contains 69,104 late-2023 windows and 1,158 attempts. Adopt recalibration only if its log loss is lower and Brier no higher. The calibrated model improves Brier but slightly worsens log loss; therefore identity is selected before reading 2024 outcomes in this stage.

| model | n | attempts | log_loss | brier | average_precision |
| --- | --- | --- | --- | --- | --- |
| raw | 69104 | 1158 | 0.071575 | 0.015991 | 0.089067 |
| prospective_calibrated | 69104 | 1158 | 0.071612 | 0.015911 | 0.088785 |

The paired whole-game bootstrap 95% interval for calibrated-minus-raw log loss is [-0.0000915, 0.0001707], while Brier is [-0.0001150, -0.0000416]. There is no clear log-loss improvement. This comparison selects a policy; it is not an unbiased estimate of that selected policy's performance. Historical raw and prospective-calibration columns are left unchanged, and there is no retrospective selected-policy training column.

## 2024 development audit

2024 was already inspected during the baseline stage. Its results cannot be used to overturn the training-only decision. The final candidate calibrator uses 138,801 forward-predicted 2023 rows and 2,376 attempts, with intercept -0.277537 and slope 0.908110. Applying that map to a full-training refit assumes calibration transfers from rolling fits.

| model | n | attempts | log_loss | brier | average_precision | calibration_slope |
| --- | --- | --- | --- | --- | --- | --- |
| raw | 136487 | 2462 | 0.076796 | 0.017220 | 0.087265 | 0.867785 |
| prospective_calibrated | 136487 | 2462 | 0.076570 | 0.017127 | 0.087265 | 0.945808 |

The candidate happens to improve both 2024 scoring rules, but it remains unselected. In 2024, `prospective_calibrated` denotes the fixed training-fitted candidate, not a monthly 2024 update. Its positive slope preserves ranking, so average precision is unchanged. High-tail miscalibration persists: the candidate's >20% bin has 773 windows and 130 attempts, with mean prediction 28.10% versus 16.82% observed. The selected raw model's corresponding bin has 1,057 windows and 173 attempts, 29.43% predicted versus 16.37% observed.

Calibration bins and subgroup audits include observation and attempt counts. Paired uncertainty uses 200 whole-game bootstrap resamples with seed 20261115 and fixed predictions. It does not include model refitting, across-game player dependence or feed-measurement uncertainty.

## Reproduction and artifacts

From the repository root, with the existing Python environment and processed data:

```powershell
New-Item -ItemType Directory -Force data/processed/test_tmp | Out-Null
$env:TEMP = (Resolve-Path data/processed/test_tmp).Path
$env:TMP = $env:TEMP
python -m unittest discover -s tests -q
python -m scripts.forward_threat
python scripts/execute_forward_threat_notebook.py
```

The Jupyter launcher and subprocess kernel startup stalled and were interrupted. The helper executes cells in a fresh in-process IPython session, preserving stream and rich outputs, with IPython state directed to the workspace. The notebook itself reruns the pipeline in a fresh Python process, then checks temporal inequalities, probability bounds, unique opportunity IDs, warmup/quarantine accounting, the frozen protocol hash and calibration/subgroup denominators. The standalone script and notebook are alternative reproduction paths; running both repeats the fit for verification.

- Protocol: `docs/forward_threat_protocol.md`; execution: `scripts/forward_threat.py`.
- Notebook: `notebooks/07_forward_threat_calibration.ipynb`; focused tests: `tests/test_forward_threat.py`.
- Compact outputs: `results/forward_threat/` contains `origins.csv`, `sample_flow.csv`, `chronology_quarantine.csv`, `policy.json`, `metrics.csv`, `calibration.csv`, `subgroups.csv`, `paired_bootstrap.csv` and input/protocol/code hashes in `provenance.json`.
- Local ignored outputs: `data/processed/forward_threat/training_forward_scores.csv.gz`, `development_2024_scores.csv.gz`, monthly model/calibrator bundles and `final_bundle.joblib`. The final bundle explicitly records the selected policy; its candidate calibrator must not be applied when that policy is identity.

## Next research boundary

Freeze the pitcher-response protocol before fitting context-only versus context-plus-threat models. Prefer the raw forward score as the primary threat input to match the selected identity policy, with the prospective calibrated column a declared sensitivity if desired. The warmup and quarantined rows cannot enter a response model requiring threat scores. Fit on the scored population, preserve terminal/nonattempt windows within that population, and report the resulting sample flow. No pitcher-response model was fit here.

2025 remains unopened. Video validation remains pending. These probabilities describe feed-recorded attempts, not real-world action completeness or causal effects. No broad originality claim is made; full-text prior-work comparison remains a submission prerequisite.

## Completed verification

All 37 repository tests pass. The executed notebook contains six completed code cells and no error outputs. Reloading every monthly bundle reproduces all 211,811 saved forward predictions and their calibration values; the final bundle reproduces all 136,487 development predictions. The selected-probability column equals raw probabilities exactly. Protocol/code hashes and calibration/subgroup accounting checks pass. Compact evidence is saved in `results/forward_threat/verification.json`. No execution blocker remains for this stage; the 61 quarantined rows remain unavailable until their upstream chronology is repaired. Changes are saved locally and are uncommitted.
