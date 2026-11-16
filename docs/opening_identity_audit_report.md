# Opening pitcher identity audit

Executed 2026-11-16, run 0a05cf9df8c64d5cb2194693809f3566. All 7,289 development feeds were checksum verified. Starting pitchers from ordered team pitcher lists plus explicit substitutions/position-1 switches reconcile to every final plate-appearance pitcher identity; zero games remain unresolved.

| Season | Pitcher changes | Pinch-hitter changes | Raw events checked |
|---|---:|---:|---:|
| 2022 | 16,047 | 3,254 | 781,319 |
| 2023 | 15,804 | 3,768 | 818,768 |
| 2024 | 15,850 | 3,829 | 816,024 |

This is an internal chronological identity check, not independent video confirmation. In game 718729/PA11, the final matchup identifies Jeff Lindgren even for events preceding his replacement of Johnny Cueto. Using that final identity as an opening predictor can leak a later substitution. The new pass reads the pitcher active at the exact cutoff and keeps the former identity for audit. It also marks pitcher and pinch-hitter changes inside each response window and applies the existing history-attribution exclusions. Prediction windows remain in the population.

Batter identity is explicitly marked as final-PA metadata, not permitted as an opening predictor. It is absent from the frozen attempt and response feature allowlists. No new batter effect is added.

Code audit checked starter initialization, fielding-half separation, exact event-sequence cutoffs, missing substitution identities, final-PA reconciliation and response-after-cutoff ordering. Tests demonstrate that the final matchup cannot overwrite the starter before substitution, that undocumented changes fail, and that identity/history eligibility change together without mutating input rows. All 80 repository tests passed. Full-table impact counts will be generated during grouped history reconstruction; no corrected model result is claimed yet.
