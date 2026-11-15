# Aggregate Baseball Savant tempo benchmark

Checked and executed 2026-11-15. This benchmark asks whether feed-derived event-start intervals reproduce Baseball Savant's published pitcher-level pitch-tempo medians. It is aggregate corroboration, not independent release-time validation. The frozen public-video gate remains **`validation_pending`**.

## Benchmark verification

Baseball Savant defines pitch tempo as the median release-to-release time for a pitch following a take—called ball or called strike—to the same batter. The leaderboard separates bases empty from runners on and says it updates weekly.

The interface exposed seasons 2010–2026; regular season, playoffs, or combined game types; qualified or numeric minimum-pitch filters; pitcher/batter/team/league entities; team and team-stint controls; year ranges; split-year control; and a CSV download. It did not expose a date filter, so the existing 30-game audit sample could not be matched to full-season medians.

The page did not document its `Qualified` formula or any interruption, long-interval, missing-tracking, or similar exclusion. In the retrieved 2024 data, 378 rows had `is_qualified = 1`; the smallest qualified total was 324 and the largest unqualified total was 321. Those are snapshot observations, not a claimed eligibility formula.

The visible table rounds tempo to one decimal. Embedded page data supplied three-decimal medians and base-state counts. The official CSV download returned 854 rows but had duplicate `total_pitches` and `median_seconds_empty` headers and repeated the bases-empty median in its second median column. The benchmark therefore used the page's embedded data and retained the CSV only to document the defect.

## Frozen population and coverage

Six pitchers were frozen before their feed agreement was calculated: Cooper Criswell, Bailey Ober, Zac Gallen, Albert Suárez, Mitch Spence, and Aaron Nola. They were evenly spaced across the published bases-empty tempo distribution after requiring Savant qualification plus project coverage floors of 500 bases-empty and 250 runners-on eligible pitches.

MLB public game logs identified complete 2024 regular-season appearances. The union contained 182 games on 117 dates at 30 venues. All six game logs, all 182 feeds, the Savant HTML, and the Savant CSV downloaded successfully and are checksummed in `data/tempo_benchmark_download_ledger.csv`. Raw files remain ignored.

The feed reconstruction found 14,858 pitch events for the six pitchers and no distinction between `isPitch` events and pitch events with a `playId`. It retained 6,915 documented-rule pairs: 4,445 classified bases empty and 2,470 runners on. Of those, 485 contained at least one intervening nonpitch action. No documented-rule interval had a missing or nonpositive start or end timestamp.

## Primary comparison: documented public rules

Primary results retain long intervals and all intervening nonpitch actions.

| Timestamp measure | Base state | Median signed difference (feed − Savant) | Median absolute discrepancy | Maximum absolute discrepancy |
|---|---|---:|---:|---:|
| Start-to-start | Bases empty | +0.099 s | 0.099 s | 0.162 s |
| Start-to-start | Runners on | +0.283 s | 0.283 s | 0.524 s |
| End-to-end | Bases empty | +0.869 s | 0.869 s | 1.148 s |
| End-to-end | Runners on | +1.177 s | 1.177 s | 1.618 s |

Every primary start-to-start cell was higher than Savant. Bases-empty differences ranged from +0.074 to +0.162 seconds. Runners-on differences ranged from +0.132 to +0.524 seconds and were largest for Zac Gallen (+0.524), Mitch Spence (+0.413), and Aaron Nola (+0.306).

Rounding to the visible one-decimal display did not remove the pattern: start-to-start differences were 0.1–0.2 seconds with bases empty and 0.1–0.5 seconds with runners on. End-to-end remained systematically much higher. End-to-end is therefore not an interchangeable reproduction of the published benchmark.

Primary feed counts exceeded Savant by 21–42 bases-empty intervals and 25–81 runners-on intervals per pitcher. Across pitchers, the feed had 188 excess bases-empty intervals and 295 excess runners-on intervals—the same scale as the retained action-interrupted pairs.

The nonexclusive action labels show what drives this population difference. Bases-empty interrupted pairs were dominated by recorded timeouts (173 category occurrences). Runners-on pairs included pickoffs (114), timeouts (74), other nonpitch actions (67), step-offs (38), and mound visits (15). Category totals can exceed pair totals when more than one action type occurs between pitches.

## Prespecified sensitivities

The `no_intervening_actions` sensitivity produced the most diagnostic result:

- bases empty: 4,257 feed intervals versus 4,257 Savant intervals;
- runners on: 2,173 feed intervals versus 2,175 Savant intervals;
- counts matched exactly in 11 of 12 pitcher/base-state cells; the remaining cell was Zac Gallen runners-on, short by two;
- start-to-start median absolute discrepancy was 0.003 seconds with bases empty and 0.001 seconds with runners on;
- maximum absolute discrepancy was 0.017 seconds with bases empty and 0.027 seconds with runners on.

This near-identity supports an inference that Savant's aggregate population likely omits intervals containing intervening nonpitch feed actions, or applies a rule with nearly the same effect. The checked leaderboard does not document that exclusion, so the sensitivity is not promoted to the primary definition and the two Gallen intervals remain unresolved.

Restricting intervals to at most 30 seconds reduced runners-on discrepancies but did not align counts. Reclassifying by the preceding pitch's post-pitch state did not resolve the primary mismatch. These results localize the discrepancy to intervening-action eligibility rather than rounding or the base-state member of the pair.

## Interpretation

The aggregate results strongly corroborate that `playEvents.startTime` differences reproduce Savant's published pitcher medians for the apparent action-free population. They also suggest that Savant and the feed-derived calculation may share the same or closely related underlying timestamp source, so this is not independent validation.

The benchmark does **not** prove:

- that `startTime` is an exact pitch-release timestamp;
- individual-interval accuracy or interruption accuracy;
- independence from Savant's underlying data;
- suitability for detecting small within-pitcher responses to runner threat;
- runner-state validity, strategic effects, or causal effects.

## Recommendation

**Investigate a specific measurement discrepancy:** determine whether Savant excludes every interval with an intervening nonpitch action and resolve the two missing Zac Gallen runners-on intervals. Until that rule is independently documented or reproduced, retain the documented-rule result as primary, use action-free results only as a labeled sensitivity, and continue calling the measure an **event-start interval**. Do not begin threat-tempo modeling, and do not change the video gate from `validation_pending`.
