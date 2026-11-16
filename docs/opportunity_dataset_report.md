# Analysis-ready opportunity dataset: preparation report

Executed 2026-11-15 in `notebooks/05_opportunity_dataset.ipynb` under the frozen [exploratory analysis plan](exploratory_analysis_plan.md). “Analysis-ready” here means one row per frozen opportunity with explicit cutoffs, labels, provenance, and quality fields. It does **not** mean the selective cache is ready for threat modeling. The frozen public-video gate remains `validation_pending`.

## Result

The preparation preserves all runner-control audit identities:

| Quantity | Rows/windows |
|---|---:|
| First-base-only opportunity windows | 12,228 |
| Windows with recorded pickoff or steal | 878 |
| Windows with recorded pickoff | 675 |
| Windows with recorded steal attempt | 205 |
| Windows with both | 2 |
| Windows with neither recorded | 11,350 |
| Terminal windows without a later pitch | 315 |

The primary future pitcher response is present in 651 windows: at least one feed-recorded pitcher-initiated pickoff throw. The table separately retains 25 catcher-pickoff windows, one unknown-initiator pickoff window, step-offs, disengagement violations, steal attempts and outcomes, and pickoff outcomes. Counts are feed-recorded action records; “no recorded” is not confirmed real-world absence.

All 1,008 action records assigned to these first-base windows occur in exactly one window and match the frozen v1.1 assignments. The table does not alter the earlier action audit's 1,591 total rows, because many audited actions occur outside a first-base-only opportunity.

## Population and selection

The cached union has 212 manifest rows and 211 unique 2024 regular-season games after deduplicating one overlap with matching SHA-256 values. Its dates run from March 28 through September 29 across 130 dates, all 30 teams, 30 venues, 461 opening pitchers, and 461 opening runners.

The apparent breadth does not make the population representative. Thirty games were selected for a schedule-stratified feasibility audit. The other 182 were collected to cover every 2024 appearance of six deliberately selected tempo-benchmark pitchers. Selection therefore overweights those pitchers, their opponents, and their venues. The union is classified as inspected development data and every row has `final_test_eligible=False`.

The proposed broader frame is every regular-season game needed for 2022 history, 2023 training, 2024 validation, and a locked 2025 test. No additional games were downloaded for this task.

## Row structure and leakage controls

Each row contains three explicit groups:

- **A — opening information:** source/game keys, opening pitcher/batter/runner, count, outs, inning, score, previous pitch, feature cutoff, and reconstructed disengagement state.
- **B — actions and outcomes:** response action IDs, pitcher/catcher/unknown pickoffs, step-offs, steals and their outcomes, coarse nonpitch actions, closure reason, terminal status, and the separately labeled secondary event-start interval.
- **C — quality and eligibility:** state/conflict flags, runner changes, missing catcher/history flags, assignment/cutoff checks, dataset role, and proposed split status.

All response events have an event order strictly after the feature cutoff. The feature dictionary covers every table column and states availability, denominator, missing-data treatment, and the rule preventing same-window outcomes from entering predictors.

Pre-game runner opportunity, attempt, success, and shrunken-rate fields are deliberately missing in all 12,228 rows. The selective cache cannot produce their denominators without selection bias. Opening catcher is also missing in all rows because a chronological defense reconstruction has not been completed; it was not inferred from a final lineup.

## Disengagement state

The reconstruction applies the documented post-2023 rule: pitcher pickoffs and step-offs count toward the plate-appearance limit, and the count resets after any runner advances. It preserves unknown-initiator pickoffs separately.

There are 1,126 action records with a raw feed `disengagementNum`; every comparable ordinal agrees with the reconstruction. Two reviewed/outcome action events repeat the immediately preceding pickoff's raw ordinal. They remain separate feed records but are explicitly marked `continuation_of_prior_pickoff_record=True` and do not increment rule state a second time. This resolves a representation detail without rewriting the frozen window labels.

## Missingness, exclusions, and terminal opportunities

No frozen row is deleted. The preparation instead reports:

| Condition | Windows | Treatment |
|---|---:|---|
| Terminal without next pitch | 315 | retained |
| Runner identity changes within window | 234 | retained; preliminary model-ineligible |
| Unknown pickoff initiator | 1 | retained separately |
| Unknown action classification | 0 | retained as an explicit possible category |
| Opening catcher not reconstructed | 12,228 | missing predictor |
| Complete pre-game runner history unavailable | 12,228 | blocks threat modeling |
| Preliminary structural-response ineligible | 235 | flagged, not removed |

The known game 746690 plate-appearance conflict remains in the source audit but contributes no first-base-only opportunity. The aggregate timing benchmark still has 285 interrupted intervals with only coarse nonpitch information and no mapped detailed runner-control action; those records are not relabeled as clean or action-free.

## Secondary timing subset

The table identifies 4,584 same-plate-appearance event-start intervals after a called ball/called strike with no intervening nonpitch event. This is a labeled secondary subset, not a primary response and not release tempo. Conditioning on no action occurs after threat is measured and can select on pitcher/runner behavior. Terminal and action windows remain in the action denominator even when they cannot contribute a completed timing interval.

The aggregate Savant result does not pass the video gate, and the two Zac Gallen runners-on count-gap intervals were not matched by guesswork.

## Readiness and recommendation

The present artifact is ready for schema review, collection design, and reproducibility checks. It is not ready for a threat-tempo or recorded-pickoff model because its sampling is selective and complete forward runner histories are unavailable.

Recommendation: **collect the complete broader frame, construct leakage-safe runner histories forward in time, and then proceed with an explicitly labeled recorded-pitcher-pickoff model if completeness checks pass.** That action model does not require release-time video validation. Defer timing analysis; if later retained, use only the secondary event-start label and keep the video gate pending until genuinely validated.

## Reproducible artifacts

- `results/opportunity_development_table.csv`: one row per frozen opportunity.
- `results/opportunity_feature_dictionary.csv`: complete field dictionary and leakage rules.
- `results/opportunity_population_summary.csv`, `opportunity_exclusion_summary.csv`, and `opportunity_coverage.csv`: population, treatments, and date/team/venue/pitcher/runner coverage.
- `results/opportunity_disengagement_checks.csv` and `opportunity_validation_checks.csv`: rule-state and integration checks.
- `results/opportunity_proposed_splits.csv` and `opportunity_additional_data_needed.csv`: frozen expansion plan.
- `scripts/prepare_opportunity_dataset.py`: deterministic preparation code.
