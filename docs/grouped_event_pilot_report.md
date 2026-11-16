# Completed-play reconstruction pilot

Executed 2026-11-16 under grouped_event_repair_protocol.md. Full source inventory covers 7,289 checksum-verified development feeds. Revised grouping maps 18,530 annotations/catcher throws. Two unlinked records remain explicit: 717444/59/7 and 745576/18/2. Both occur outside first-only occupancy before and after the event; no artificial link is assigned.

Pilot run e252d1194a344143b1cffdce7e9dd6e0 covers 161 deterministic games: all initial exception games, ordinary games from each season, the motivating regression game and the suspended-game chronology case. It contains 8,944 grouped windows and 179 recorded attempts. The same games previously contained 9,225 windows and 179 attempts. Pitcher-pickoff counts remain 637 in this pilot. Terminal windows decline from 316 to 35; 177 attempts now close at an actual pitch and two remain nonpitch opportunities. These are selected diagnostic games, not representative rate estimates.

The regression game 663178/PA20 now assigns its steal to G2-663178-20-pre, opening at 0 balls and 0 strikes and ending at pitch 0. The former artificial post-pitch window is absent. Grouped IDs have a new G2 prefix; legacy_anchor_id supplies a crosswalk but is not permission to join old scores onto changed labels.

Code review checked source-ID matching, preservation of pre-state, grouped final-state transfer, no duplicated action assignment, forward feature boundaries and transferred disengagement resets. Unresolved eligible groupings fail; no proximity-only relabeling is permitted. Default historical parsing remains available for reproducing archived artifacts. The pilot passed catcher, state-conflict, unknown-action, action-uniqueness and raw-disengagement checks. All 74 repository tests passed before publication, including the delayed-steal regression.

The first publication attempt failed because the paired local artifact directory lacked its cache index. No pointer was published. The rerun writes and verifies that index. Earlier, one test-suite attempt encountered a transient Windows directory-rename PermissionError; its immediate repeat passed. Neither failure was silently counted as a pass.

Git now preserves exact bytes under results/ because published manifests hash byte content. Automatic line-ending conversion must not invalidate a checked-out run. Cached per-game tables are individually checksummed and remain local/ignored.

This pilot clears full development reconstruction, not model validity. Rebuild all histories and re-evaluate the frozen models before restoring any prospective result. Timing, action-completeness, literature and 2025 gates remain unchanged.

## Expanded integration gate

The first full rebuild stopped at game 718573: grouping a step-off with its pickoff-outcome continuation exposed an action-type ordering bug in disengagement reconstruction. Grouped records now retain source event order, and a regression test verifies one disengagement rather than two. No failed full run was published.

The joint identity check then exposed a pre-first-event cutoff error introduced by overwriting a grouped parent's sequence with its final child's sequence. Original sequence and group-end sequence now remain separate; only an after-group cutoff uses the latter. A regression test checks both values.

The final expanded pilot, run 487a2bc8863e438ca57473dcfce8fe66, covers 263 games, including every observed season/event-type/parent-type grouping combination. All 14,717 windows pass grouped parsing and chronological identity application. The identity pass changes 149 opening-pitcher values and introduces 197 history-attribution exclusions, while retaining those prediction windows. Every response boundary is strictly later than its feature cutoff. Evidence is in results/grouped_identity_pilot.json. All 80 tests pass. This supersedes the initial pilot as the full-rebuild entry gate.

## Outside-population raw counter discrepancy

The subsequent full run stopped on game 746241/PA18, also flagged in the archived original processing metadata. Raw review confirmed a feed counter of 3 versus a rule-based count of 1 after an advancement, with zero first-only windows anywhere in that PA. Retain the mismatch and its exact, fail-closed disposition. The 264-game pilot (fa40810c5a394dc59096cd20ca9cd1a5) adds this game; its 31 eligible windows outside PA18 pass independent response and opening-identity checks. See results/disengagement_disposition_audit.json. No parser dependency or existing cached table changed.
