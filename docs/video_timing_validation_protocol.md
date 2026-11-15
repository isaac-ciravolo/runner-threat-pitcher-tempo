# Public-video timing validation protocol

Version 1.1, frozen 2026-11-15 before any video timing errors were observed. Version 1.1 corrects the initial ordinary-stratum quotas so the prespecified coverage floor is attainable; the added candidates are simply the next seeded rows and were not chosen using availability or agreement. This is a feasibility pilot, not evidence of accuracy across all MLB games, parks, broadcasts, or seasons.

## Scope and measurement

The feed measure remains an **event-start interval**. It is the elapsed time in seconds between `playEvents[].startTime` on two consecutive records with `isPitch = true`, ordered as supplied within the same `gamePk` and `about.atBatIndex`. The audit retains every intervening event and flags changes of pitcher or batter. No long interval or interruption is removed merely because it is long or unlabeled.

Stable interval key:

`(game_pk, at_bat_index, preceding_event_index, following_event_index)`

The feed interval is not shown to an annotator. It is regenerated from cached feeds and joined only after annotation by the stable key.

## Video release and interval definition

A video release is the **first displayed frame in which the pitched ball is visibly separated from the pitcher's hand/fingers**. Apply the same definition to both releases.

For each interval:

1. Use one continuous video segment that visibly contains both releases and the elapsed time between them.
2. Record source URL, game/event identifiers, clip offsets, access date, and continuity evidence.
3. If a native frame index and verified frame rate are available, record both release frames and the verified rate. Otherwise record player time offsets in seconds and the smallest reliable time increment. Never assume 30 or 60 frames per second.
4. If separation spans ambiguous or blurred frames, record the selected first-separated frame/time and an uncertainty bound. If release cannot be identified consistently, mark the annotation ambiguous and unusable.
5. A broadcast camera cut is acceptable only when the source itself is continuous and audio/timecode shows no removed elapsed time. Edited highlights, condensed games, separate pitch clips, replays, and clips with an unverifiable discontinuity are unusable for elapsed-time validation.
6. Separate clips of the two pitches are never combined unless they share a verified continuous clock that spans the missing footage.

Derived video interval:

- release-time route: `release_2_video_seconds - release_1_video_seconds`;
- frame route: `(release_2_frame - release_1_frame) / verified_frame_rate`.

If both routes are supplied, they must agree within the recorded timing uncertainty. Missing values remain missing; feed values are never used to fill annotations.

## Blinded annotation

Annotators work from `data/video_validation_annotations.csv`, which contains identifiers and blank video fields but no feed timestamps, feed intervals, or error columns. Sampling strata and feed interruption labels live in the candidate file, not the annotation sheet.

Each usable primary annotation must have:

- verified continuous footage;
- two release times or two frames plus a verified frame rate;
- a positive video interval;
- an annotator, annotation date, timebase description, timing uncertainty, and observed interruption category;
- no exclusion reason.

The sample deterministically flags 12 primary intervals for a second annotation. Use `independent_second` only for a different reviewer. If the same person repeats the work after a washout period, label it `repeat_same_reviewer`; do not describe it as independent review.

## Candidate sample

Source population: the 6,532 within-plate-appearance consecutive-pitch event-start intervals from the fixed 30-game audit sample.

Selection seed: `20241116`. Intervals receive one mutually exclusive stratum in this priority order:

1. `unusually_long`: interval greater than 60 seconds;
2. `pickoff`: recorded pickoff between releases;
3. `step_off`: recorded step-off between releases;
4. `timeout`: recorded timeout between releases;
5. `other_interruption`: mound visit, substitution, pitcher/batter change, or another recorded nonpitch event;
6. `after_foul`: preceding pitch call contains `Foul`;
7. `ordinary_runner_first_only`: no recorded intervening action, first occupied and second/third empty after the preceding pitch;
8. `ordinary_bases_empty`: no recorded intervening action and bases empty after the preceding pitch.

Primary quota: 15 intervals in each ordinary stratum and 10 in each of the six challenge strata, 90 total. Reserve quota: the next 3 seeded intervals per stratum, 24 total. Candidates are selected before timing agreement is assessed. The version 1.1 ordinary additions use the same seed and ordering rule and were made before any video errors were available. The script asserts coverage of at least 10 games and several venues; observed coverage is reported with the generated sample.

This design intentionally oversamples difficult intervals. It is not a representative estimate of the league-wide error distribution.

## Availability and replacement

Search primaries in deterministic `candidate_order`. Record every search in `data/video_availability_log.csv` as one of:

- `continuous_verified`;
- `located_continuity_unverified`;
- `edited_or_discontinuous`;
- `inaccessible`;
- `not_found`;
- `not_searched`.

Record URLs even when footage is unusable. When a primary is unusable, take the lowest `replacement_order` reserve in the same stratum. Do not cross strata, skip a reserve without logging it, or choose a replacement based on feed/video agreement. If the three reserves are exhausted, retain a stratum shortfall.

## Interruption groups

Report ordinary intervals separately from pickoff, step-off, timeout, other interruption, after-foul, and unusually long strata. Also report runner-on-first-only and bases-empty states separately where sample sizes permit. Absence of a feed label does not prove uninterrupted play; annotators record video-observed interruptions independently.

## Error analysis

For usable primary/replacement annotations:

- signed error = feed event-start interval minus video release interval;
- absolute error = absolute signed error;
- median bias = median signed error;
- also report mean signed error, mean absolute error, median absolute error, and 95th-percentile absolute error.

Show feed-versus-video agreement and signed/absolute error plots. Summarize by game, base state, and validation stratum when counts allow. Correlation may be descriptive but is never an acceptance criterion.

If at least 10 games have usable annotations, use a fixed-seed 2,000-replicate game-cluster bootstrap for uncertainty on aggregate error summaries. With fewer games, report point estimates without pretending pitch-level independence and label uncertainty inadequate.

## Prespecified decision gate

The smallest meaningful tempo difference is a **design assumption of 0.50 seconds**, carried forward from the feasibility audit. It is not an estimated effect. The tail-error limit is half that target so measurement error does not routinely consume most of the contrast.

Minimum coverage for an unrestricted decision:

- at least 60 usable intervals from at least 10 games and 5 venues;
- at least 15 ordinary runner-first-only intervals;
- at least 15 ordinary bases-empty intervals;
- at least 20 combined interrupted/after-foul/unusually-long intervals;
- at least 3 usable intervals in each of pickoff, step-off, timeout, after-foul, and unusually-long strata.

Error criteria:

- absolute mean signed error <= 0.10 seconds;
- absolute median signed error <= 0.10 seconds;
- mean absolute error <= 0.15 seconds;
- median absolute error <= 0.10 seconds;
- 95th-percentile absolute error <= 0.25 seconds;
- median absolute error <= 0.25 seconds in ordinary runner-first-only, ordinary bases-empty, and combined challenge intervals; apply the same 0.25-second subgroup limit to any named stratum with at least 5 usable intervals.

Outcomes:

- `proceed_validated_scope`: coverage and all applicable criteria pass;
- `proceed_restricted_scope`: the prespecified ordinary within-plate-appearance subset has at least 30 usable intervals across at least 10 games, passes the aggregate error criteria within that subset, and challenge strata are explicitly excluded;
- `collect_more_evidence`: coverage, timebase, continuity, or subgroup evidence is inadequate; any provisional error failures are reported but cannot establish rejection without adequate evidence;
- `reject_timing_measure`: adequate evidence fails global criteria and no defensible restricted subset passes;
- `validation_pending`: no usable annotations or annotation is still materially incomplete.

Thresholds will not be tuned after errors are inspected. No gate can pass with inadequate coverage.

## Runner-state validation is separate

Timing agreement does not validate opportunity reconstruction. A separate fixed sample covers ordinary nonattempts, pickoffs, steals, caught stealing, and opportunities ending without another pitch. Independent video/play-by-play observations must record pre-action occupancy and outcome without using `matchup.splits.menOnBase` as a predictor.

The documented game 746690 / plate appearance 38 terminal-third-out conflict remains unresolved at the event level: a force out at third ends the half-inning while the feed omits the irrelevant 1B-to-2B advance and places the batter at occupied first. The half-inning reset protects subsequent state, but this play remains flagged and cannot validate generic movement completeness.

Passing the timing gate will not validate runner states, attempt labels, causal claims, or the full research design.
