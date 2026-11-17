# Public-video timing validation status

**2026-11-16 feasibility update:** Isaac reports that available scrubbing controls are too coarse for practical annotation. Preserve the unreviewed sample; the gate remains pending and timing analysis is deferred. Continue the narrower recorded-action study under [the no-video validation amendment](no_video_validation_amendment.md).

Status checked 2026-11-15. The protocol, sample, annotation workflow, analysis code, and decision gate are implemented. The timing gate is **`validation_pending`** because no frozen candidate has a genuine usable video annotation.

## Implemented

- Frozen release definition, continuity rules, exclusion rules, uncertainty recording, replacement order, subgroup reporting, and decision thresholds in `docs/video_timing_validation_protocol.md`.
- Deterministic sample of 90 primaries and 24 same-stratum reserves from 6,532 feed event-start intervals. Each ordinary stratum has 15 primaries; each of the six challenge strata has 10. Every stratum has 3 reserves. The primaries cover 29 games and 21 venues.
- Blinded annotator sheet with identifiers but no feed timestamp, feed interval, stratum, or error columns.
- Separate availability log and a 12-candidate first-pass manual review queue.
- Post-annotation join, eligibility checks, error summaries, game-cluster bootstrap, plots, and prespecified gate evaluation in `notebooks/02_video_timing_validation.ipynb`.
- Independent 21-case runner-state review sheet, including the retained game 746690 / plate appearance 38 terminal-state conflict.

## Video discovery completed

The reproducible metadata search queried the MLB game-content endpoint for all 30 audit games. All 30 requests succeeded. It found one public item whose title and duration suggest continuous footage: the 7:37 “Full 9th inning of Ronel Blanco's no-hitter” for game 746409. That item does not match the frozen sample, whose game 746409 candidates occur in innings 5 and 7. Its continuity has not been visually verified.

Archived-broadcast metadata was present for 106 candidate records but indicated `freeGame=false`; those records are logged as access-limited rather than treated as public evidence. Eight records had no same-inning continuous item in the checked metadata. Public condensed games and highlights were located for several sampled games, but they are edited and are not usable for elapsed-time annotation.

Video playback could not be opened in the available computer-use environment, and no local video decoder was available. Therefore:

- videos visually inspected: **0**;
- frozen intervals annotated from video: **0**;
- fabricated or inferred annotations: **0**;
- timing gate: **`validation_pending`**, not pass, fail, or restricted-scope approval.

The search results are retained in `data/public_video_search_log.csv`, the metadata candidates in `data/public_video_source_candidates.csv`, and per-interval availability in `data/video_availability_log.csv`.

## Exact next manual actions

1. Open `results/manual_video_review_queue.csv` and search in `candidate_order`. It begins with one primary from each stratum, followed by distinct games to broaden source discovery.
2. For each row, search the linked MLB.TV game page and MLB Film Room, MLB game/video pages, or another lawfully accessible public source. Accept a source only if one continuous segment spans both releases. Do not combine individual pitch clips.
3. In `data/video_availability_log.csv`, set `search_method` to `manual` and record the reviewer, `search_status`, source, URL, access date, continuity status, clip offsets, and search notes even when the source is unusable. Rows marked manual are preserved when metadata discovery is rerun.
4. If a primary is unusable, take only the lowest `replacement_order` reserve in the same stratum. Log every skipped or exhausted reserve; never replace based on timing agreement.
5. In `data/video_validation_annotations.csv`, record the source and clip offsets, verified continuity evidence, timebase type, verified frame rate only when known, two release seconds or frames, timing uncertainty, video-observed interruption, selection/usability flags, exclusion reason when applicable, annotator, round, and date. Do not add feed values.
6. Mark release at the first displayed frame where the pitched ball is visibly separated from the pitcher's hand/fingers. Mark ambiguity and exclude the interval when that landmark cannot be identified consistently.
7. For the 12 rows flagged `second_annotation_requested`, add a separate annotation row after the primary review. Use `independent_second` only for a different reviewer; use `repeat_same_reviewer` for a repeat by the same person after a washout.
8. Execute the validation notebook from a fresh kernel. It will join feed values only after annotation, create agreement/error results when eligible data exist, and apply the frozen gate without threshold changes.

```powershell
py -m jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/02_video_timing_validation.ipynb
```

## Separate runner-state work

Review `data/runner_state_validation_sample.csv` against independent public video or play-by-play. Record pre-action bases and the observed outcome without using `matchup.splits.menOnBase` as the predictor. Resolve or retain the game 746690 / plate appearance 38 flag explicitly. Timing validation cannot clear this gate.
