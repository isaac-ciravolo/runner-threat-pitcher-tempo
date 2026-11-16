# Runner-control action representation audit

Executed 2026-11-15 under the frozen [v1.1 protocol](runner_control_action_audit_protocol.md). The notebook is `notebooks/04_runner_control_action_audit.ipynb`. This audit does not change the public-video timing gate: it remains `validation_pending`.

## Result

The public feed has explicit, usable representations for pitcher and catcher pickoff throws, step-offs, steal attempts and outcomes, balks, timer violations, and one disengagement violation. Event fields and runner movements can be linked with retained provenance. A later rule-state check identified two attempt/outcome continuation records with the same raw disengagement ordinal; they remain in the frozen action-row accounting and are flagged rather than silently merged. Representation accuracy is **partially corroborated, but action completeness is unvalidated**. The results support auditing recorded actions; they do not establish that unrecorded attempts are absent.

The final recommendation is **investigate a specific measurement discrepancy**: identify Savant's undocumented interruption/population rule, especially for runners-on intervals, before using these event-start intervals for small threat-response effects. Do not begin threat-tempo modeling from this result.

## Coverage and provenance

The two cached public-feed populations contained 212 manifest rows and 211 unique games. One game, 745855, occurred in both manifests; its cached SHA-256 values agreed. The feasibility-audit copy was retained by the prespecified source priority, and every event was deduplicated on game and feed event key.

The explicit mapping uses `playEvent.type`, `details.eventType`, `details.fromCatcher`, violation type, runner `playIndex`, movements, and fielding credits. Descriptions are retained as evidence but do not silently create categories. The executed audit produced 1,591 action rows:

| Recorded action | Rows | Important split |
|---|---:|---|
| Pickoff throw | 857 | 801 pitcher, 55 catcher, 1 initiator unknown |
| Step-off | 353 | all explicitly pitcher-labeled |
| Steal attempt | 319 | 276 ordinary advances, 17 error advances, 25 caught stealing, 1 advance-then-out |
| Timer violation | 49 | 38 pitcher, 10 batter, 1 catcher |
| Balk | 12 | all with base-runner advances |
| Disengagement violation | 1 | explicit `forced_balk` + `pitcher_disengagement` schema |

Among pickoff records, 819 recorded safe returns without a movement, 17 direct pickoffs, 10 pickoff/caught-stealing outcomes, and 11 error advances. The 857 rows are feed action-event records, not a guaranteed count of unique physical throws. In games 745821 and 747220, an attempt event is followed by a reviewed/outcome event carrying the same `disengagementNum`; the opportunity preparation preserves both rows but marks the latter as a continuation and increments disengagement state once. Binary pickoff-window accounting is unchanged. Simultaneous runner paths are retained under one event or split into runner-specific steal attempts only when the movement evidence identifies distinct attempts.

Pitcher and runner identities are complete for all pickoff rows. Catcher identity is populated only when fielding credits support it: 6 of the 55 catcher-initiated pickoffs have an event-level catcher ID, while 49 safe-return throws expose `fromCatcher=true` but no catcher identity. Those names were not inferred from a final box-score lineup. Step-offs and timer violations correctly have no target-runner identity when no base-runner movement is attached.

## First-base-only opportunity windows

Chronological reconstruction produced 12,228 pitch-bounded windows with first occupied and second/third empty:

- 878 contained at least one recorded pickoff or steal attempt; 11,350 contained none.
- 675 contained a pickoff throw and 205 contained a steal attempt; two windows contained both types.
- 37 windows contained multiple pickoff throws before closure.
- 3,259 opened before the plate appearance's first event, and 134 of those contained an attempt.
- 315 ended without another pitch; 241 of these contained at least one recorded action.

This denominator therefore includes ordinary nonattempts, repeated throws, actions before a first pitch, state exits, and terminal action sequences. It does not create a zero-exposure opportunity after a terminal pitch.

The known reconstruction conflict in game 746690, plate appearance 38, produces no first-base-only window and no classified runner-control action. Excluding it changes none of the 12,228 windows, 878 attempt windows, or 1,591 action rows. This is a sensitivity result, not a rewrite of the retained conflict.

## Public review

The deterministic queue contains 74 positive records across action/role/outcome strata and 20 no-attempt controls. Seven were reviewed in the compact public-review table:

- An independent Giants recap says a Ryan Walker pickoff erased the eighth-inning runner, partially corroborating the queued pitcher-pickoff/out record. [McCovey Chronicles](https://www.mccoveychronicles.com/2024/9/8/24239502/mlb-final-giants-padres-9-8-2024-recap-tyler-fitzgerald-marco-luciano-matt-chapman)
- An MLB Game Story explicitly labels Korey Lee picking off Rob Refsnyder, corroborating the catcher-pickoff record but not independently of MLB's systems. [MLB Game Story](https://www.mlb.com/stories/game/746785)
- An MLB narrative says Wilyer Abreu stole second and then stepped off the bag, supporting the unusual advance-then-out sequence. [MLB recap](https://www.mlb.com/news/rays-drop-second-consecutive-game-to-red-sox)
- A third-party game summary records Nico Hoerner moving to second but does not identify the disengagement mechanism. [StatMuse game summary](https://www.statmuse.com/mlb/game/7-11-2024-chc-at-bal-230610)

Three negative controls were reviewed, but no independent, event-complete public source was found for the exact within-plate-appearance windows. They remain inconclusive: lack of an indexed mention is not evidence that no action occurred. The review supports several positive labels but cannot estimate sensitivity or false-negative rates.

## Contribution to the aggregate tempo benchmark

All 485 documented-rule action-interrupted intervals remain in the primary benchmark: 188 bases-empty and 297 runners-on. Detailed runner-control records join to 200 intervals (7 empty, 193 on); the other 285 contain timeouts, mound visits, or coarse nonpitch actions without a mapped runner-control record. Fifteen intervals contain more than one category, so contribution counts are nonexclusive.

The largest categories are:

| Base state | Category | Interrupted intervals | Median start-to-start (s) |
|---|---|---:|---:|
| Empty | Timeout | 173 | 24.977 |
| Empty | Mound visit | 8 | 50.367 |
| On | Pitcher pickoff throw | 105 | 38.456 |
| On | Timeout | 74 | 30.892 |
| On | Steal attempt | 44 | 35.121 |
| On | Step-off | 38 | 38.607 |
| On | Other nonpitch | 23 | 35.204 |
| On | Mound visit | 15 | 59.419 |
| On | Catcher pickoff throw | 9 | 24.967 |

Under documented public rules, the 12 pitcher/base-state cells have a median absolute Savant discrepancy of 0.153 seconds and maximum 0.524. Excluding all nonpitch-action intervals changes those to 0.001 and 0.0265 seconds, respectively, but that is still an undocumented sensitivity. One-at-a-time exclusions show that timeouts have the largest broad effect (median absolute discrepancy 0.0695, maximum 0.453); excluding pitcher pickoffs yields 0.139 and 0.345. Other single-category exclusions leave the median absolute discrepancy around 0.1525–0.153. No category is promoted to a primary exclusion merely because agreement improves.

For Zac Gallen with runners on, the documented-rule feed count is 448 at a 20.130-second median versus Savant's 367 at 19.606. The action-free feed subset is 365 at 19.606, two below Savant. Because the public leaderboard supplies no event-level IDs, the two Savant intervals cannot be identified; assigning that gap to any two feed events would be fabricated precision.

## Boundaries

The audit does not establish unrecorded-action completeness, runner intent, independent timing accuracy, release timestamps, Savant's internal exclusion rule, suitability for small within-pitcher responses, or causality. The near-exact action-free aggregate match remains strong population-level evidence and a useful diagnostic, not permission to rename feed event starts as release times or to pass the frozen video gate.
