# Action-to-pitch timing audit: model interpretation suspended

Checked 2026-11-16 after the conditional-success denominator audit revealed that every recorded attempt occupied a terminal window. Run b97b09e8bfb84542b708b6f084801736 independently resolves explicit raw actionPlayId values to actual pitch playId values, with checksums for every inspected feed.

| Season | Recorded-attempt windows | Explicitly linked to a pitch at/before the feature cutoff | No resolvable explicit pitch link |
|---|---:|---:|---:|
| 2022 | 1,797 | 1,754 | 43 |
| 2023 | 2,377 | 2,323 | 54 |
| 2024 | 2,462 | 2,400 | 62 |

No linked attempt is associated with a pitch after its assigned feature cutoff. The action record's position in the feed cannot be assumed to be the physical action's time. For example, game 663178, plate appearance 20: pitch index 0 reports runnerGoing=true; the following stolen-base action index 1 points back to that pitch's playId. Existing window W-663178-20-e0 opens after pitch 0 with a one-ball count and labels that steal as a future response. Its physical attempt was already underway on the opening pitch. This is direct source evidence of a wrong prediction boundary, not merely a timestamp precision concern.

The 159 unlinked cases are unresolved by this audit; proximity is not enough to assign them. Explicit links are source association evidence, not independently validated release times. Other action classes and interleaved events need their own assessment before generalizing any repair.

## Consequences

The initial attempt model, forward threat scores and response results are retained for reproducibility but are **not valid evidence for the intended prospective runner-threat claim** until opportunity construction is repaired and the affected pipeline rerun. Earlier chronology checks fixed between-game availability; they did not validate within-play physical order. Passing accounting tests did not detect this error. The response metric improvement must not be promoted as a research finding.

Repair must group a pitch with its explicitly associated outcome records, apply their final runner state before opening the next opportunity, attach the attempt to the opportunity ending at that pitch, and avoid artificial post-pitch windows. Preserve raw IDs and a crosswalk, quantify missing/ambiguous links, keep independently occurring nonpitch actions, and rebuild histories from the new denominator. Freeze this amendment before refitting. Do not patch scores or move labels without repairing base state and opening context together.

Code audit: exact unique-ID matching, no proximity inference, verified source hashes, full attempt-record coverage and immutable publication. Regression tests cover absent links and duplicate pitch IDs. All 69 repository tests passed. No 2025 feeds were accessed.
