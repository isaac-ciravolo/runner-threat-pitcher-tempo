# Scoring-credit source audit

The event-only count does not cover the box-score scoring records. The movement-reason candidate exactly reconciles stolen bases and caught stealing for all 151,791 player/game rows across 7,289 development games. This is agreement within the same MLB feed, not independent scoring validation or proof that all attempted steals are recorded.

| Season | Box-score SB | Event-tag SB | Movement SB | Box-score CS | Event-tag CS | Movement CS | Movement disagreements |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 2,486 | 2,189 | 2,486 | 811 | 385 | 811 | 0 |
| 2023 | 3,503 | 3,022 | 3,503 | 866 | 465 | 866 | 0 |
| 2024 | 3,617 | 3,161 | 3,617 | 961 | 491 | 961 | 0 |

The comparison uses all base states so that its totals match the box-score denominator. Movement CS includes pickoff-caught-stealing reasons; the research parser currently treats those as pickoff actions. This audit does not change that target definition. Error advances and safe ending states remain distinct outcomes.

Direct review of game 663178/PA6 shows Rafael Ortega's caught stealing attached to a pitch through playIndex=0, with no standalone play-event action type. The action parser skips relevant runner movements when the referenced event exists but is unclassified. Therefore internal action coverage is incomplete, and prospective model refitting must wait for that repair. The original event-only audit is preserved as run 892e7010b0fe48379437d21d8679f59b; the follow-up is e73f4dd13bc74fdd924681a12b84801c.

The initial execution stopped on Danny Jansen's two team entries in resumed game 746942. The corrected audit sums both entries and retains boxscore_sides=2. No source value was overwritten. Tests cover SB/CS categories, pickoff-CS, unrelated advances, duplicate movements, missing actors, mismatches and the resumed-game case. No success model, source labels, histories or 2025 feeds were changed by this audit.
