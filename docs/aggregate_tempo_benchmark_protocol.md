# Aggregate Baseball Savant pitch-tempo benchmark protocol

Version 1.0, frozen 2026-11-15 before any feed-to-Savant agreement was calculated. This is aggregate corroboration only. It does not alter or pass the public-video timing gate, which remains `validation_pending`.

## Benchmark and retrieval observations

The benchmark is Baseball Savant's public [Pitch Tempo Leaderboard](https://baseballsavant.mlb.com/leaderboard/pitch-tempo), checked 2026-11-15. The page defines pitch tempo as the median release-to-release time for pitches that follow a take—called strike or called ball—and are thrown to the same batter. It reports separate bases-empty and runners-on summaries and states that the metric updates weekly.

The current interface exposes:

- seasons 2010 through 2026;
- game types `Regular Season`, `Playoffs`, and `Regular + Playoffs`;
- minimum-pitch choices `Qualified`, 1, 10, 50, 100, 250, 500, 1000, 2000, and 5000;
- pitcher, batter, pitching-team, batting-team, and league entities;
- all-team aggregation, team-stint splitting, a selected team, and a `with team only` option;
- start/end year and split-year controls;
- a CSV download.

No date-range control is exposed. The checked page does not document the formula behind `Qualified`, which appears in the embedded data only as `is_qualified`. It also does not document any long-interval, interruption, missing-tracking, or other exclusion beyond the preceding-take and same-batter rules. Those exclusions will not be invented.

The visible table rounds tempo to one decimal. The page's embedded `tempoServerVals.data` supplies medians to three decimals and counts by base state. On 2026-11-15, `csv=true` returned a malformed header with duplicate `total_pitches` and `median_seconds_empty` fields and repeated the empty-base median in the second median column. The reproducible benchmark therefore uses the embedded page data, retains the raw CSV only as a documented download check, and does not treat the malformed runners-on CSV field as authoritative.

## Population and prespecified pitcher selection

Season: 2024. Game type: regular season. Entity: pitcher, aggregated across teams. Minimum-pitch request: 1 so the full leaderboard population and `is_qualified` flag can be inspected.

Because the leaderboard has no date filter, the fixed 30-game audit sample cannot be matched to full-season pitcher medians. Complete 2024 regular-season appearance coverage will be collected for six frozen pitchers.

Selection uses only published Savant values, before any corresponding feed intervals are retrieved or summarized:

1. require Savant `is_qualified = 1`;
2. require at least 500 published eligible bases-empty pitches and 250 published eligible runners-on pitches to stabilize both medians; these are project coverage floors, not claimed Savant eligibility rules;
3. sort by full-precision published bases-empty median and then MLBAM ID;
4. choose six evenly spaced zero-based positions from the 111-player eligible pool: 0, 22, 44, 66, 88, and 110.

The frozen pitchers are Cooper Criswell (681867), Bailey Ober (641927), Zac Gallen (668678), Albert Suárez (544150), Mitch Spence (687765), and Aaron Nola (605400). Their published bases-empty medians span 11.633 to 18.905 seconds, providing different apparent working speeds without using feed agreement for selection.

MLB's public pitcher game-log endpoint supplies each pitcher's 2024 regular-season game IDs. The union of those games defines the feed population. All appearances are retained; no game is chosen based on interval agreement.

## Primary feed interval definition

Reuse `scripts.audit_feeds.extract_events`, including its chronological runner-state reconstruction. Never use `matchup.splits.menOnBase` as a pre-pitch state.

Within the same game and plate appearance, pair consecutive feed events that are actual pitches. A pair is primary-eligible only when:

- both records have `isPitch = true` and a nonmissing `playId`;
- the preceding pitch's call description is exactly `Ball` or `Called Strike`;
- pitcher ID and batter ID are unchanged;
- both timestamps required for the relevant measure are present and yield a positive interval.

Classify the benchmark base state from the reconstructed occupancy immediately before the following pitch: `bases_empty` if no base is occupied, otherwise `runners_on`. The leaderboard does not state explicitly which member of the pair supplies its base-state label; using the current/following pitch's state is the primary interpretation. A preceding-post-pitch-state classification is reported as a labeled sensitivity.

For every pair, preserve and report intervening nonpitch actions and pitcher/batter-change flags. Do not silently discard long or interrupted intervals.

Candidate measures:

- start-to-start: following `startTime` minus preceding `startTime`;
- end-to-end: following `endTime` minus preceding `endTime`.

Neither field will be called release time. Start-to-start is the audit's existing event-start measure; end-to-end is a timestamp-field sensitivity selected before agreement is inspected.

## Prespecified comparisons and sensitivities

Primary comparison: all documented-rule eligible pairs, separately for each pitcher and base state. Compare the feed median with Savant's embedded full-precision median and with the one-decimal visible value.

Report:

- collected games, feed pitches, eligible intervals, missing timestamps, nonpositive intervals, and action-interrupted intervals;
- feed-minus-Savant differences, median absolute discrepancy, and maximum absolute discrepancy;
- count differences relative to published eligible counts;
- start-to-start and end-to-end values without choosing one solely because it fits better;
- results by pitcher and base state;
- agreement plots with the identity line and discrepancy plots.

Prespecified sensitivity analyses:

1. exclude pairs with any intervening nonpitch action (`no_intervening_actions`);
2. retain only intervals at most 30 seconds (`at_most_30_seconds`), explicitly noting that Savant labels values over 30 as slow rather than documenting their exclusion;
3. classify state from the preceding pitch's reconstructed post-pitch state (`preceding_state_classification`).

These alternatives cannot replace the documented-rule primary result.

## Interpretation boundary and recommendation rule

No numerical pass threshold is imposed because Savant's underlying interval source, undocumented qualifier formula, exact base-state assignment, and complete exclusion logic are not independently available. The benchmark is descriptive corroboration.

- Recommend **continue exploratory analysis using explicitly labeled event-start intervals** only if discrepancies are small and stable relative to the 0.50-second design scale, counts are reasonably aligned, and no timestamp field or sensitivity is selected post hoc.
- Recommend **investigate a specific measurement discrepancy** if a coherent field, base-state, count, or interruption mismatch is identified.
- Recommend **defer timing analysis** if discrepancies are large, unstable, or cannot be localized.

Even strong agreement would not prove exact release timestamps, independence from Savant's data, accuracy for individual or interrupted intervals, suitability for small within-pitcher runner-threat responses, or causal effects.
