# Grouped-event reconstruction amendment

Frozen 2026-11-16 after the action/pitch audit and before corrected modeling. This is a corrective exploratory amendment, not preregistration. Existing v1.1/chronology-v2 models remain archived and their prospective interpretation suspended.

Treat source-linked outcome annotations as part of their parent event. An exact actionPlayId must identify a unique earlier playId in the same plate appearance. Parents may be pitches, pickoffs or no-pitch records. Accept only contiguous groups with no intervening unrelated event, substitution or independently timed action. Require explicit links for steal/caught-stealing annotations; do not infer physical timing from adjacency, timestamps or runnerGoing alone. Inventory unresolved links and interleaving before deciding any exclusion rule.

Group runner-state transitions and labeled actions together. A pitch-ending opportunity includes its linked outcome records; its next opportunity opens only after the final grouped state. Keep opening count from the preceding completed group, never from the upcoming pitch. Preserve raw event/action IDs, source hashes and a raw-to-effective-event crosswalk. Transfer disengagement resets to the effective group boundary. Do not count linked outcome records twice or omit nonpitch terminal opportunities.

First run a source-level grouping inventory and a small integration pilot. Audit initial-state preservation, final-state conservation, exact action assignment, terminal/pitch distinctions, unresolved sources and before/after denominator changes. Only then rebuild the full development table and pre-game histories into new versioned locations. Any unresolved grouping that could change eligibility blocks promotion until a documented disposition is frozen. No partial corrected table may be substituted into the old model runs.

After the table passes, repeat the previously specified attempt, forward calibration and response procedures without selecting new parameters using 2024. Compare results openly with the archived defective pipeline. Conditional-success and expected-run stages remain deferred. No 2025 data access is permitted by this amendment.

## Inventory-informed disposition before reconstruction

The first complete source inventory found 149 exceptions. All 147 interleaved cases contain exactly one catcher throw (`type=pickoff`, `fromCatcher=true`) sharing the pitch association. Include explicitly linked catcher throws in the completed pitch-play group, including safe returns, so the prediction boundary is after the pitch and its associated fielding response. This is a completed-play boundary, not a release-time boundary. Do not apply this rule to independent pitcher pickoffs.

Two annotations lack a unique parent: game 717444/PA59 stolen home and a 2024 caught-stealing-error play. Keep their source order without inventing links. Reconstruction may retain such a record only when both its before/after occupancy are outside first-only; an eligible unresolved record fails the gate. Inventory exceptions remain published even when outside the analysis risk set. This disposition is based on source schema and population, not model performance.
