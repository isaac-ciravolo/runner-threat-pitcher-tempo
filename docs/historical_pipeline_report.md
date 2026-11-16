# Historical collection and forward-history report

Checked and executed 2026-11-15. This report covers public MLB regular-season schedules and live feeds for the 2022–2024 development frame. The 2025 manifest is schedule-only and remains the locked final test. No model was fit, no timing analysis began, and the public-video gate remains `validation_pending`.

## Frozen scope

| Season | Role | Schedule rows | Feed-eligible completed games | Development-feed status |
|---|---|---:|---:|---|
| 2022 | History only | 2,430 | 2,430 | 2,430 validated |
| 2023 | Training | 2,430 | 2,430 | 2,430 validated |
| 2024 | Validation/development | 2,430 | 2,429 | 2,429 validated; one canceled rainout excluded |
| 2025 | Locked final test | 2,430 | Not evaluated in this task | Schedule manifest only; no feed manifest or game feed |

The manifest keeps `game_pk`, regular-season game type, official and schedule dates, scheduled UTC start, status evidence, doubleheader/game numbers, reschedule/resume fields, teams, venue, source URL, manifest version, and a deterministic selection order. Repeated schedule occurrences are collapsed by `game_pk` while preserving all observed dates and statuses. A detailed `Cancelled` state overrides StatsAPI's abstract `Final` label; this correctly excludes 2024 game 746577, which has no completed play.

## Resumable collection

`scripts/historical_collection.py` provides schedule, pilot-selection, collection, retry, and status commands. It uses conservative pacing, timeouts, bounded exponential backoff with jitter, atomic replacement, SHA-256 validation, per-response provenance, checkpointed manifests, and an ignored JSONL attempt ledger. Valid current files and older audit/benchmark caches are checksum-validated and reused. A changed valid response moves the prior current file into a timestamped version directory; invalid responses go to quarantine rather than replacing a valid file.

Final-feed validation checks the requested `gamePk`, regular-season type, final status, at least one completed play, box-score teams, and nonempty play events. Two 2022 rain games legitimately end with a trailing incomplete plate appearance. They are retained because the game is final and completed plays exist; trailing incomplete play and pitch counts are explicit manifest fields. This preserves a terminal pitch instead of silently dropping it.

The main fresh/reuse run processed 7,290 scheduled identifiers in 4,415.2 seconds (73.6 minutes): 7,023 network responses and 267 verified cache reuses. The first pass quarantined the two final rain games plus the canceled 2024 game. A targeted two-response retry under the corrected final-feed rule validated both eligible rain games. The canceled response remains quarantined and excluded. Eligible missing and quarantined counts are therefore zero in every development season.

## Pilot and material fixes

The frozen pilot has 61 unique games: 24 from 2022, 25 from 2023, and 12 from 2024. It separates nine seeded-random games from complete early-date blocks and deliberate edge cases. Available targets include doubleheaders, suspended/resumed games, catcher and pitcher substitutions, a pinch runner, a defensive switch, multiple pickoffs, repeated review/outcome ordinals, and terminal opportunities.

The first collection pass took 43.0 seconds for 56 network responses and five verified reuses (49,428,270 bytes). A restart exposed an all-empty pandas text-column dtype error; it was fixed before scaling. The next restart completed in 12.1 seconds with 61 verified reuses and no network responses. Pilot storage averaged 810,300 bytes/game, projecting 5.50 GiB for 7,289 eligible games; validated feed bytes were ultimately 5.42 GiB. The pilot's fresh-target timing projected 85.6 minutes, compared with the 73.6-minute main run.

The initial catcher pilot also exposed a material chronology bug: it preferred a box score's final/aggregate `position`. Parser v1.1 invalidates those checkpoints. It identifies the unique batting-order starter whose position history contains catcher, can resolve multiple candidates by excluding ordered later catcher entries, applies every later defensive substitution/switch in sequence, and otherwise preserves missingness. The corrected pilot processed 61/61 games with no failures, assigned all 3,662 opportunity windows, and used ordered catcher changes on 91 windows. Pilot histories are deliberately labeled incomplete rather than treated as player histories.

## Incremental opportunity and history construction

Each validated game is parsed independently into an ignored gzip opportunity checkpoint plus a small JSON metadata checkpoint. The parser reuses the frozen first-base-only window builder, retains nonattempts, repeated actions, and terminal windows, and keeps actions separate from outcomes. Checkpoints are valid only when `game_pk`, source SHA-256, and parser version agree.

Starting defense and ordered substitutions determine the catcher at each opening cutoff. Pitcher, runner, and batter changes are checked within the event sequence. The 2022 rows are explicitly labeled pre-disengagement-limit; the two-disengagement/reset reconstruction applies only from 2023 onward.

Runner counts are snapshotted before the game starts and queued only after the feed's actual completion time. A strict `completion < next start` rule prevents same-day and suspended games from leaking into earlier starts. Counts are stored for all regimes, 2022 only, and 2023 onward: eligible opportunities, attempted opportunities, attempt records, recorded successes, unsuccessful outcomes, and ambiguous outcomes. Status fields distinguish incomplete coverage, no prior eligible exposure, observed zero attempts with positive exposure, and observed prior attempts. Every row is marked left-truncated at the 2022 collection boundary; these are not career histories.

## Full development quality

| Season | Games | Events | Pitches | Opportunities | Terminal | Attempt-history eligible | Pitcher-pickoff windows | Steal-attempt windows |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 2,430 | 781,319 | 708,540 | 137,732 | 3,135 | 134,963 | 11,524 | 1,797 |
| 2023 | 2,430 | 818,768 | 717,945 | 138,862 | 3,828 | 136,310 | 7,479 | 2,377 |
| 2024 | 2,429 | 816,024 | 709,512 | 136,487 | 3,911 | 133,955 | 7,633 | 2,462 |

All 7,289 eligible games processed with zero parser failures. All 413,081 windows have an assigned chronological catcher; 10,452 use an ordered later catcher assignment. There are zero unknown-action windows, known state conflicts, unresolved game chronologies, or incomplete-history windows. The parser retains 10,874 terminal windows. The 2022 final-rain feeds account for the two games with trailing incomplete plays.

Runner-identity changes exclude 2,769 windows in 2022, 2,552 in 2023, and 2,532 in 2024 from history counting; the rows remain in the opportunity tables with explicit reasons. No other history-count exclusion reason occurs. Conditional-success eligibility is much smaller (1,796, 2,377, and 2,462 windows) and is not used to create a combined threat score here.

| Season | No prior exposure | Positive exposure, zero prior attempts | Prior attempts observed | Incomplete coverage |
|---|---:|---:|---:|---:|
| 2022 | 4,167 (3.03%) | 56,822 | 76,743 | 0 |
| 2023 | 728 (0.52%) | 29,837 | 108,297 | 0 |
| 2024 | 630 (0.46%) | 18,056 | 117,801 | 0 |

These statuses sum to every season's opportunity count. “No prior exposure” means no earlier eligible window within otherwise complete coverage since the 2022 boundary; it does not mean no earlier career exposure. The chunked final validator passes all 22 checks: row counts, opportunity-ID uniqueness, nonnegative counts, all-regime decomposition, history-status logic, pre-game freezing, catcher coverage, and zero post-2023 history in 2022.

## Reproduction and resume commands

Run from the repository root after installing `requirements.txt`:

```powershell
py -3 -m scripts.historical_collection schedules
py -3 -m scripts.historical_collection pilot-manifest
py -3 -m scripts.historical_collection collect --pilot
py -3 -m scripts.historical_processing all --pilot
py -3 -m scripts.historical_collection collect --checkpoint-every 100
py -3 -m scripts.historical_collection collect --retry-problems
py -3 -m scripts.historical_collection status
py -3 -m scripts.historical_processing process --checkpoint-every 100
py -3 -m scripts.historical_processing histories
py -3 -m unittest discover -s tests -v
py -3 -m jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1200 notebooks/06_historical_data_quality.ipynb
```

Any interrupted collection or processing command can be rerun unchanged. Valid raw files and per-game parser checkpoints are reused. `collect --retry-problems` restricts work to nonvalidated manifest rows.

The eventual locked-test command is deliberately separate and was **not** run:

```powershell
py -3 -m scripts.historical_collection collect --seasons 2025 --allow-test-data
```

Before that command is authorized, preprocessing, model, calibration, and refitting policies must be frozen. During eventual chronological 2025 evaluation, histories may update only with earlier games demonstrably completed before the current start; parameters and tuning choices may not update from test outcomes.

## Boundaries

Schedule/feed reconciliation establishes complete coverage of the public eligible-game frame, not completeness of recorded pickoff attempts or steal decisions. Feed action representation remains only partially corroborated. Chronological counts remain left-truncated at 2022, and ambiguous outcomes stay separate. The data support a later predictive/associational workflow only; they do not identify causal effects, optimal pitcher attention, exact release timing, or net runs prevented.
