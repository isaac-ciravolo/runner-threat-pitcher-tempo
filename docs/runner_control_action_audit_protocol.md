# Runner-control action audit protocol

Version 1.1, frozen 2026-11-15 after inspecting raw field vocabulary and a schema-only dry run, before finalizing classified action or opportunity totals. Version 1.1 adds the one observed explicit disengagement-violation schema and excludes batter-only movements from runner outcomes. This is a representation audit, not runner-threat modeling. It does not alter the frozen video gate, which remains `validation_pending`.

## Population and deduplication

Use the union of the fixed 30-game feasibility audit manifest and the 182-game aggregate tempo-benchmark manifest. Deduplicate on `game_pk` before parsing. If a game is present in both manifests, retain the feasibility-audit copy, record both provenance rows, and compare the cached SHA-256 values. An event is uniquely keyed by `(game_pk, at_bat_index, event_index)`; movement evidence is linked by the runner record's `details.playIndex`. A movement represented on the same play index as an action event is evidence for that event, not a second action.

The field-vocabulary inventory is descriptive and precedes taxonomy mapping. Text searches identify candidates, but production categories require the explicit fields below. Descriptions remain provenance and review evidence; they do not silently expand the taxonomy.

## Frozen evidence mapping

Action and outcome are separate. `action_type` describes the recorded act; `initiator_role` describes who initiated it when the feed supports that distinction; outcome fields describe safe return, advance, out, error, or no recorded movement.

| Raw evidence | `action_type` | Initiator / outcome rule |
|---|---|---|
| `playEvents[].type == "pickoff"` | `pickoff_throw` | `details.fromCatcher == true` means catcher; `false` means pitcher; missing is unknown. Code `1`, `2`, or `3` supplies the target base. A linked pickoff movement is attached to this row. |
| `playEvents[].type == "stepoff"` or code `PSO` | `step_off` | Initiator is pitcher. This is not counted as a throw. |
| `details.eventType` begins `pickoff_` on an action event or linked runner movement | `pickoff_throw` | Infer pitcher or catcher only from `fromCatcher` or fielding credits at position 1 or 2. `pickoff_caught_stealing_*` remains a pickoff throw with a caught-stealing outcome; it is not also counted as a separate steal action. |
| `details.eventType` begins `stolen_base_` | `steal_attempt` | Initiator is runner; successful advance is the outcome. Multiple runner movements on one event remain separate runner attempts under stable sub-IDs. |
| `details.eventType` begins `caught_stealing_` | `steal_attempt` | Initiator is runner; caught stealing is the outcome. Catcher or pitcher fielding credits are retained as throwing/fielding evidence, not counted as an additional pickoff action. |
| `details.eventType == "balk"` | `balk` | Initiator is pitcher; all tied advances attach to one event row. |
| `details.eventType == "forced_balk"` with `details.violation.type == "pitcher_disengagement"` | `disengagement_violation` | Initiator is pitcher; the tied forced advance is the runner outcome. |
| no-pitch code `VP`, `VC`, or `AC` | `timer_violation` | Initiator is pitcher, catcher, or batter respectively. |

Timeouts, mound visits, substitutions, and unrelated actions are retained in the vocabulary and context tables but are not runner-control actions. Candidate records that contain runner-control text without one of the mapped fields are labeled `unknown_candidate`, placed in the review queue, and never silently coerced.

For a linked base-runner movement, `runner_out` comes from `movement.isOut`; `advance` from a non-out terminal `movement.end` different from its start/origin; `error` from an `eventType` containing `error`; `safe_return` is a pickoff throw with no out and no recorded advance; and `no_recorded_movement` is explicit when no base-runner movement is linked. Batter-only walk or strikeout movements tied to a timer violation remain in raw movement provenance but do not become runner outcomes. One action event may retain multiple linked movements in its outcome summary, while one multi-runner stolen-base event produces one runner-attempt row per distinct runner path. Genuine separate throws have separate event indices and therefore separate action IDs.

## First-base-only opportunity windows

The audit denominator is every maximal exposure window in which first base is occupied and second and third are empty. Occupancy comes only from chronological runner reconstruction, never `matchup.splits.menOnBase`.

A window opens:

1. before the first event of a plate appearance when its reconstructed pre-event state is first-base only;
2. immediately after an actual pitch when its reconstructed post-event state is first-base only; or
3. immediately after a nonpitch event changes the state into first-base only.

The window closes at the earliest next actual pitch, exit from first-base-only state, plate-appearance end, or half-inning end. If a closing pitch leaves first-base only, it immediately opens the next window. Thus windows include ordinary nonattempts, action sequences before the first pitch, multiple throws before one pitch, and terminal windows with no following pitch. A pickoff that leaves the runner safe does not split a window. Attempts are nested within windows; windows and actions are not interchangeable denominators.

An event-anchored window is opened only when at least one later event remains in the plate appearance. This prevents a terminal pitch from creating a zero-exposure denominator after the plate appearance has already ended; it does not remove a terminal action from the window that preceded it.

For every window, retain the opening and closing keys, pitcher/batter/runner context, counts and outs, every linked action ID, attempt count, whether a following pitch exists, terminal reason, and conflict flags. The primary audit includes all reconstructed windows. A labeled sensitivity excludes game 746690, plate appearance 38, whose terminal third-out movement conflict is already documented; this sensitivity may affect eligibility or terminal bookkeeping but cannot rewrite the reconstruction.

## Review and accuracy status

Before consulting independent public descriptions, select a deterministic review set with seed 20241117: up to five rows per observed runner-control action type/initiator combination, all `unknown_candidate` rows up to twenty, and twenty first-base-only no-attempt windows. Positive and negative-control records are frozen by stable keys. Official MLB feed fields are internal consistency evidence, not independent confirmation. Public game stories, box scores, or video may corroborate a reviewed item, but selective coverage cannot validate missing actions. Unverified rows remain `pending_public_review`; no absence claim is made from a missing highlight.

## Aggregate-tempo join

Rebuild the six-pitcher 2024 benchmark exactly as frozen. Join action IDs by game, plate appearance, and strict event order between the preceding and following actual pitches. Preserve all 485 documented-rule action-interrupted intervals as the primary population. Report nonexclusive category contributions and one-at-a-time exclusion sensitivities for start-to-start pitcher/base-state medians. Do not promote an exclusion because it improves agreement.

The two-count Zac Gallen runners-on gap is investigated only at aggregate level because the Savant leaderboard provides counts and medians, not pitch identities. Candidate feed events may be described, but no two events can be declared the missing Savant records without an event-level benchmark.

## Interpretation boundary

This audit can establish how the public live feed represents recorded runner-control actions and how those records contribute to aggregate tempo discrepancies. It cannot establish the completeness of unrecorded attempts, independent timestamp accuracy, release time, runner intent, small within-pitcher effects, or causality. No threat-tempo predictor or response is estimated here.
