# Public-data feasibility audit

## Executive finding

**Conditional go for the measurement-validation stage; no-go for a runner-threat/tempo model yet.** The public MLB feed supported reproducible event extraction, interruption retention, and a provisional first-base-only opportunity reconstruction in this 30-game sample. It did not establish that `playEvents.startTime` is ball release, that unlabeled intervals are uninterrupted, or that public video can meet the preregistered error tolerance.

The single most useful next task is to manually validate approximately 100 stratified intervals against public video using `data/video_validation_template.csv`, including ordinary intervals, pickoffs, step-offs, timeouts, and other interruptions.

## What ran and when

- Sample schedule and 30 live feeds retrieved from MLB's public Stats API from 2026-11-15 20:14:43 through 20:14:49 UTC. All returned HTTP 200; there were no retrieval failures.
- Final audit notebook executed from a fresh kernel at 2026-11-15 20:40:45 UTC.
- State and interval tests executed successfully with `py -m unittest discover -s tests -v`.
- Environment: Python 3.14.4, pandas 3.0.2, NumPy 2.4.4, requests 2.34.0, JupyterLab 4.6.1, nbconvert 7.17.1, and nbformat 5.10.4. Exact executed versions are in `results/audit_environment.csv`.

The live endpoint was verified by direct request as `https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live`. The selection schedule used `https://statsapi.mlb.com/api/v1/schedule`. These are public, unauthenticated endpoints, but the checked sources provide no service-level or schema-stability guarantee. The [source and claim ledger](source_claim_ledger.md) records direct and supporting sources.

## Sample selection and coverage

The selection script used schedule metadata only and seed `20241115`. It sorted eligible completed regular-season games, shuffled reproducibly within each window, and accepted the first 10 games having a distinct date and venue within that window. It did not inspect live-feed timing, steal, score, or outcome fields before selection.

| Window | Eligible dates | Selected-date span | Games | Venues within window |
|---|---|---|---:|---:|
| Early | 2024-03-28 through 2024-04-30 | 2024-04-01 through 2024-04-29 | 10 | 10 |
| Middle | 2024-06-15 through 2024-07-15 | 2024-06-16 through 2024-07-13 | 10 | 10 |
| Late | 2024-09-01 through 2024-09-29 | 2024-09-07 through 2024-09-29 | 10 | 10 |

Overall coverage is 30 games, 21 unique venues, and 24 teams. Exact game IDs, dates, teams, parks, rationale, feed URLs, retrieval times, and checksums are in `data/audit_sample_manifest.csv`. The schedule download and all game-feed requests are in `data/audit_download_ledger.csv`. Raw downloads remain ignored in `data/raw/`.

## Automated structural checks

The audit preserved 10,156 play events: 8,808 pitch events and 1,348 nonpitch events across 2,283 plate appearances.

| Check | Result |
|---|---:|
| Missing or invalid event `startTime` | 0 |
| Missing or invalid event `endTime` | 0 |
| Duplicate `(game_pk, at_bat_index, event_index)` keys | 0 |
| Nonincreasing event indexes within a plate appearance | 0 |
| Negative adjacent event-start differences within a plate appearance | 0 |
| Zero adjacent event-start differences within a plate appearance | 7 |
| Missing or nonpositive consecutive-pitch event-start intervals | 0 |
| Unattached runner-movement records | 0 |
| Runner-state conflicts after documented rules | 1 |

The seven zero differences occur in four games (745919: 1; 746043: 4; 745883: 1; 745368: 1) and involve substitutions/defensive switches or automatic intentional balls sharing a timestamp with another event. They were retained. The full by-game table, including games with zero anomalies, is `results/audit_game_quality.csv`.

There were 6,532 consecutive-pitch event-start intervals. Median was 18.356 seconds, the 95th percentile 33.012 seconds, and the maximum 290.200 seconds. Thirty-three intervals exceeded 60 seconds; none was silently removed. Recorded intervening-action flags included 72 intervals with pickoffs, 43 with step-offs, 377 with timeouts, 13 with mound visits, 2 with substitutions, and 70 with other nonpitch actions. The refined change flags identify 1 interval with a pitching change and 0 with a batter change. A flag describes the feed record, not the completeness of real-world interruption observation.

### Timestamp format versus precision

Every audited `startTime` and `endTime` string had three fractional-second digits. This demonstrates millisecond formatting only. No checked MLB source defines event start as ball release, explains the collection clock, or quantifies accuracy. The seven exact ties also show that displayed digits cannot be interpreted as guaranteed ordering precision.

Until video validation passes, the outcome is **event-start interval**, not release-to-release tempo.

### Recorded nonpitch labels

The 1,348 nonpitch records comprised 412 batter timeouts, 176 mound visits, 100 pickoff records, 57 step-offs, 377 substitution/switch records, and 226 other records. Pickoff attempts (98) and step-offs (57) generally used the top-level record `type` with no `details.eventType`; retaining only `eventType` would lose them. Other labels included game advisories, automatic/no-pitch records, wild pitches, steals, caught stealing, runner placement, ejections, passed balls, defensive indifference, and a balk. Exact combinations are in `results/audit_action_label_inventory.csv`.

Absence of a label is not evidence that no interruption occurred.

## Opportunity and state reconstruction

### Observed field semantics

- `playEvents[].count` is event-associated. Balls and strikes behave like post-pitch values on ordinary pitches, but outs are not uniformly post-resolution. In game 746690, plate appearance 38, the terminal force-play event retains `outs = 2` while runner movement records `outNumber = 3`.
- Event `details.awayScore` and `homeScore` occur on some actions; `play.result` contains the plate-appearance final score. A frozen pre-action score must be carried chronologically, not read from the final result.
- Base occupancy is not supplied as a complete pre-event state on every record. It was reconstructed by applying runner movements tied by `details.playIndex`, plus explicit `runner_placed` and pinch-runner actions.
- The same runner can have multiple movement segments at one play index (for example, 1B to 3B and then 3B to score); those segments must be collapsed into one path for state application.
- `matchup.splits.menOnBase` matched the reconstructed end-of-plate-appearance occupancy bucket in all 2,283 plays. It matched the state before the first pitch in only 1,334 of the 2,276 plays having a pitch. It must not be used as a frozen pre-action predictor.
- Substitutions are explicit nonpitch actions. Pinch runners require the action's `base`, `player`, and `replacedPlayer` fields to update runner identity.

After these rules, no runner movement lacked a play index. One conflict remained: game 746690, plate appearance 38 ends the half-inning on a force out at third, while the feed omits the now-irrelevant 1B-to-2B advance and also places the batter at occupied first. The half-inning reset makes subsequent occupancy unambiguous, but the conflict is retained in `results/audit_state_issues.csv`.

### Audit opportunities

The provisional audit reconstruction found 1,253 first-base-only response opportunities: 1,171 ordinary next-pitch nonattempts, 56 with a recorded pickoff before a later pitch, 16 with a recorded stolen base, 9 with recorded caught stealing, and 1 ending on a pickoff without another pitch. These are representation checks, not a finalized modeling denominator or attempt label.

Five representative sequences were manually traced in the raw public play-by-play: an ordinary nonattempt, a pickoff followed by a pitch, a steal, a caught stealing followed by a pitch, and an inning-ending pickoff with no later pitch. All matched the extraction. MLB's indexed [Game Story for game 746655](https://www.mlb.com/stories/game/746655) separately corroborated the inning-ending pickoff. The dynamic Gameday pitch UI could not be visually inspected because browser automation was unavailable, so `results/manual_play_by_play_checks.csv` labels the four feed-only checks as non-independent. No supplementary games were required for these requested event types.

Opportunity reconstruction is therefore reliable enough for a larger, explicitly tested reconstruction stage, but not yet frozen for modeling. Additional schema checks should cover other seasons, reviews/corrections, mid-plate-appearance substitutions, and opportunities ending through all action-only paths.

## Independent timing validation preparation

No video intervals were measured in this audit. `data/video_validation_template.csv` includes game, plate-appearance and event identifiers; source and URL; two observed release times; video and feed intervals; error fields; intervening actions; interruption agreement; reviewer; and notes.

Feasible sources and limitations:

- [MLB Film Room](https://www.mlb.com/video): MLB's [launch documentation](https://www.mlb.com/news/mlb-film-room-launch) says its searchable library includes every MLB pitch since 2017. The current interface is dynamic; clip boundaries may omit the preceding release or intervening action, and reliable frame stepping/timebase must be checked manually.
- MLB Game Stories and individual official clips are publicly accessible but selective and cannot support a representative interval sample alone.
- [MLB.TV archives](https://www.mlb.com/live-stream-games/help-center/subscription-access-how-to-watch-mlbtv-on-android-mobile-devices) can provide continuous broadcasts, but require subscriber access and may have access restrictions. They cannot be the only reproducible source.

### Prerecorded acceptance criterion

Before any threat association is inspected, define 0.50 seconds as the smallest tempo difference worth interpreting in the first study. For an approximately 100-interval stratified validation sample, accept feed event-start difference as a release-interval proxy only if:

1. median absolute feed-minus-video error is at most 0.10 seconds;
2. the 95th percentile absolute error is at most 0.25 seconds (half the smallest meaningful difference);
3. absolute mean signed error is at most 0.10 seconds; and
4. ordinary and recorded-interruption strata each have median absolute error at most 0.25 seconds, with interruption-label agreement reported separately.

Failure means no release-tempo model with this field. The project should retain event-start intervals as a feed-process measure or pivot to validated pickoff/pitch-selection outcomes.

## Limitations and unresolved issues

- Timestamp meaning and accuracy remain undocumented and unvalidated.
- Feed labels may omit real interruptions; broadcast video may also omit time or change camera/timebase.
- The sample is a schedule-stratified feasibility audit, not a power calculation or league estimate.
- Runner intent, unrecorded attempts, foul-ball attempts, leads, and defensive attention are not observed.
- Manual traces checked representation, not independent timing or complete Gameday/UI agreement.
- Public endpoint stability and retrospective corrections are not guaranteed; cached checksums identify exactly what was audited.
- No threat variable, causal estimand, strategic recommendation, or originality claim was evaluated.

## Recommendation

Proceed only to the independent timing-validation task. Do not construct the full-season opportunity dataset and do not fit the runner-threat model until the video gate is resolved and the opportunity definition—including action-only endings—is frozen in the decision log.
