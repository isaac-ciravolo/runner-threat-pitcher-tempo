# Decision log

| Date | Decision | Rationale | Status |
|---|---|---|---|
| 2026-11-15 | Begin with runner on first only | Narrow opportunity definition | Proposed design |
| 2026-11-15 | Start with a 2024 analysis season | Avoid pooling rule eras in the initial study | Proposed; verify rules in source review |
| 2026-11-15 | Validate timestamps before tempo modeling | Event start is not established as ball release | Required gate |
| 2026-11-15 | Defer net-run optimization | Predictive validation alone does not identify action effects | Required scope limit |
| 2026-11-15 | Fix the feasibility sample with schedule metadata only | Seed 20241115; 10 games each from early, middle, and late 2024; distinct date and venue within each window; no timing or running outcomes inspected | Executed; 30 games, 21 venues, 24 teams |
| 2026-11-15 | Preserve all play events and call consecutive pitch `startTime` differences event-start intervals | Field naming and millisecond formatting do not establish ball release or measurement precision; long and action-interrupted intervals remain in the data | Executed audit definition |
| 2026-11-15 | Reconstruct occupancy from runner movements plus explicit runner-placement and pinch-runner actions | `matchup.splits.menOnBase` aligned with plate-appearance end state, not a frozen pre-action state; multi-segment paths require collapsing | Executed; one terminal third-out conflict retained |
| 2026-11-15 | Use a provisional audit opportunity after a pitch leaves first occupied and second/third empty when another pitch or later action remains | Preserves ordinary nonattempts and action-only endings while auditing representation; this is not the final denominator | Provisional; freeze before modeling |
| 2026-11-15 | Set video timing acceptance before threat analysis | Smallest meaningful difference 0.50 s; require median absolute error <=0.10 s, 95th percentile <=0.25 s, absolute mean bias <=0.10 s, and stratum medians <=0.25 s | Required next gate; no video validation yet |
| 2026-11-15 | Conditional go for timing validation; no-go for threat-tempo modeling | Structural data passed the small audit, but timestamp semantics and accuracy remain unvalidated | Current recommendation |
| 2026-11-15 | Define video release as first visible frame with ball separated from the pitcher's hand | Provides one repeatable visual landmark; ambiguous releases are excluded rather than imputed | Frozen before timing-error inspection |
| 2026-11-15 | Use an 80-interval stratified pilot plus 24 same-stratum reserves | Seed 20241116; balances ordinary first-only/empty states with pickoff, step-off, timeout, foul, other-interruption, and long intervals | Superseded before timing-error review; ordinary quota could not reach the coverage floor |
| 2026-11-15 | Keep feed timing out of annotator-facing files | Join feed event-start intervals only after video release annotation using the four-field stable key | Required blinding rule |
| 2026-11-15 | Prespecify timing coverage and error criteria | 0.50 s smallest-meaningful-difference design assumption; add mean absolute error <=0.15 s and explicit coverage/subgroup rules to the previously logged bias, median, and tail limits | Frozen before timing-error inspection |
| 2026-11-15 | Keep runner-state validation independent of timing validation | Terminal third-out conflict and end-state `matchup.splits.menOnBase` semantics are unrelated to release timing accuracy | Required separate gate |
| 2026-11-15 | Leave the timing gate pending after the first public-source search | All 30 game-content endpoints were searched, but the only continuous-title public item did not match a frozen inning; access-limited archives and edited highlights cannot supply genuine blinded annotations | `validation_pending`; 0 usable annotations |
| 2026-11-15 | Correct the pilot to 90 primaries plus 24 reserves | Raise each ordinary stratum from 10 to 15 so the already-prespecified 15-per-state gate is attainable; additions are the next rows under the same seed and were made without timing errors or agreement | Protocol v1.1 frozen before timing-error review |

Record changes before inspecting affected outcomes. No analysis choices are preregistered merely by appearing in this repository.
