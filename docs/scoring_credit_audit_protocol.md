# Source scoring-credit reconciliation

Frozen 2026-11-16 before the complete reconciliation. This exploratory audit follows inspection of two ordinary stolen-base and two caught-stealing records. It does not select or fit a conditional-success target.

For every checksum-verified 2022–2024 eligible feed, compare per-player game box-score stolenBases and caughtStealing with explicit event tags. Candidate SB counts use only stolen_base_2b, stolen_base_3b and stolen_base_home. Candidate CS counts use the three caught_stealing tags and the three pickoff_caught_stealing tags. Attribute an event only through its explicit player.id. Inventory all related tags, including error variants, separately; do not silently fold them into a credit category. Preserve missing actors and every per-player disagreement.

This uses all base states to match game box-score totals, not the first-only research denominator. Agreement is internal consistency within one public data source, not independent scorer verification or action completeness. Pickoff-caught-stealing events are presently classified as pickoff actions in the research pipeline; record that distinction rather than change the frozen attempt label. No history, threat, response label or existing result is modified.

Publish source hashes, exact tag vocabulary, season accounting, discordant player/game rows and a local complete reconciliation table. Unit tests must distinguish ordinary SB/CS, pickoff-CS, error variants, missing actors and box-score mismatches. An unresolved discrepancy prevents calling the tag proxy verified official credit. Conditional-success estimation, safe-ending labels, expected-run comparisons and 2025 feeds remain gated.
