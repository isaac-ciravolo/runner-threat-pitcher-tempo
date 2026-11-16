"""Prepare the leakage-audited first-base-only development dataset.

This module preserves the frozen runner-control window accounting.  It adds
opening-time context, explicit response labels, provenance, data-quality flags,
and proposed chronological split metadata without fitting any model.
"""

from __future__ import annotations

import json
import platform
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts.audit_feeds import extract_events
from scripts.runner_control_audit import load_union_feeds


DISENGAGEMENT_RULE = "MLB_2023_two_disengagements_reset_when_any_runner_advances"
DISENGAGEMENT_LIMIT = 2
EXPECTED_ACCOUNTING = {
    "windows": 12228,
    "pickoff_windows": 675,
    "steal_windows": 205,
    "combined_windows": 2,
    "pickoff_or_steal_windows": 878,
    "interrupted_benchmark_without_detail": 285,
}


def _value(mapping: dict[str, Any] | None, *keys: str) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _pipe(values: list[str]) -> str:
    return "|".join(value for value in values if value)


def _ids(value: Any) -> set[str]:
    if value is None or pd.isna(value) or str(value) == "":
        return set()
    return {item for item in str(value).split("|") if item}


def _person_names(loaded: list[tuple[pd.Series, dict[str, Any]]]) -> dict[int, str]:
    names: dict[int, str] = {}
    for _manifest, feed in loaded:
        for person in (_value(feed, "gameData", "players") or {}).values():
            if person.get("id") is not None:
                names[int(person["id"])] = person.get("fullName") or str(person["id"])
    return names


def _advancement_events(
    loaded: list[tuple[pd.Series, dict[str, Any]]]
) -> dict[str, bool]:
    """Identify events after which the MLB disengagement count resets.

    The applicable public rule resets the plate-appearance limit whenever any
    runner advances.  Batter-only movement from home to first is not a reset.
    """
    advanced: dict[str, bool] = {}
    bases = {"1B", "2B", "3B"}
    for _manifest, feed in loaded:
        game_pk = int(feed["gamePk"])
        for play in _value(feed, "liveData", "plays", "allPlays") or []:
            pa = int(_value(play, "about", "atBatIndex"))
            by_index: dict[Any, list[dict[str, Any]]] = defaultdict(list)
            for item in play.get("runners", []):
                by_index[_value(item, "details", "playIndex")].append(item)
            for event in play.get("playEvents", []):
                index = event.get("index")
                key = f"{game_pk}:{pa}:{int(index)}"
                reset = False
                for item in by_index.get(index, []):
                    movement = item.get("movement") or {}
                    start = movement.get("start") or movement.get("originBase")
                    end = movement.get("end")
                    if start in bases and end in bases.union({"score"}) and end != start:
                        reset = True
                        break
                advanced[key] = reset
    return advanced


def build_disengagement_history(
    events: pd.DataFrame,
    actions: pd.DataFrame,
    loaded: list[tuple[pd.Series, dict[str, Any]]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reconstruct recorded pitcher disengagement history within each PA."""
    advances = _advancement_events(loaded)
    action_groups = {
        key: frame.sort_values("action_id")
        for key, frame in actions.groupby("event_key", sort=False)
    }
    history_rows: list[dict[str, Any]] = []
    check_rows: list[dict[str, Any]] = []

    for (game_pk, pa), group in events.groupby(["game_pk", "at_bat_index"], sort=False):
        since_reset = 0
        pickoffs_since_reset = 0
        stepoffs_since_reset = 0
        unknown_since_reset = 0
        total_prior = 0
        reset_count = 0
        for event in group.sort_values("event_order").itertuples(index=False):
            key = event.event_key
            detail = action_groups.get(key, pd.DataFrame(columns=actions.columns))
            pitcher_pickoffs = detail.loc[
                detail["action_type"].eq("pickoff_throw")
                & detail["initiator_role"].eq("pitcher")
            ]
            stepoffs = detail.loc[detail["action_type"].eq("step_off")]
            violations = detail.loc[detail["action_type"].eq("disengagement_violation")]
            unknown_pickoffs = detail.loc[
                detail["action_type"].eq("pickoff_throw")
                & detail["initiator_role"].eq("unknown")
            ]
            before = since_reset
            checked = pd.concat([pitcher_pickoffs, stepoffs, violations], ignore_index=True)
            for action in checked.itertuples(index=False):
                raw_number = pd.to_numeric(action.raw_disengagement_num, errors="coerce")
                # Two cached plays encode a pickoff attempt in one event and its
                # reviewed/out result in the immediately following action event.
                # Both records expose the same disengagementNum.  Preserve both
                # action records, but do not count the outcome continuation as a
                # second disengagement.
                continuation = bool(
                    pd.notna(raw_number)
                    and since_reset > 0
                    and raw_number == since_reset
                    and action.action_type == "pickoff_throw"
                )
                if not continuation:
                    since_reset += 1
                    total_prior += 1
                    if action.action_type == "pickoff_throw":
                        pickoffs_since_reset += 1
                    elif action.action_type == "step_off":
                        stepoffs_since_reset += 1
                check_rows.append(
                    {
                        "action_id": action.action_id,
                        "game_pk": int(game_pk),
                        "at_bat_index": int(pa),
                        "event_index": int(event.event_index),
                        "action_type": action.action_type,
                        "raw_disengagement_num": raw_number,
                        "reconstructed_disengagement_num": since_reset,
                        "raw_number_available": pd.notna(raw_number),
                        "raw_number_matches": bool(raw_number == since_reset)
                        if pd.notna(raw_number)
                        else pd.NA,
                        "continuation_of_prior_pickoff_record": continuation,
                        "counts_as_disengagement": not continuation,
                        "runner_advance_reset_same_event": bool(advances.get(key, False)),
                    }
                )

            unknown_since_reset += len(unknown_pickoffs)
            reset_on_event = bool(advances.get(key, False))
            if reset_on_event:
                since_reset = 0
                pickoffs_since_reset = 0
                stepoffs_since_reset = 0
                unknown_since_reset = 0
                reset_count += 1
            history_rows.append(
                {
                    "event_key": key,
                    "recorded_disengagements_before_event": before,
                    "recorded_disengagements_since_reset_after_event": since_reset,
                    "recorded_pitcher_pickoffs_since_reset_after_event": pickoffs_since_reset,
                    "recorded_stepoffs_since_reset_after_event": stepoffs_since_reset,
                    "recorded_unknown_pickoffs_since_reset_after_event": unknown_since_reset,
                    "recorded_disengagements_prior_in_pa_after_event": total_prior,
                    "recorded_disengagement_reset_count_after_event": reset_count,
                    "runner_advance_reset_on_event": reset_on_event,
                }
            )
    return pd.DataFrame(history_rows), pd.DataFrame(check_rows)


def _source_memberships(sources: pd.DataFrame) -> dict[int, str]:
    return (
        sources.groupby("game_pk")["source_population"]
        .agg(lambda values: "|".join(sorted(set(values.astype(str)))))
        .to_dict()
    )


def prepare_opportunity_table(
    root: Path,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    sources, selected, loaded = load_union_feeds(root)
    events, _state_audit = extract_events(loaded)
    # These are the executed, frozen protocol-v1.1 outputs.  Reusing them keeps
    # this notebook focused on table preparation and also verifies that no later
    # code silently changes the audited denominator.
    actions = pd.read_csv(root / "results" / "runner_control_actions.csv", low_memory=False)
    windows = pd.read_csv(root / "results" / "runner_control_opportunities.csv", low_memory=False)
    history, history_checks = build_disengagement_history(events, actions, loaded)

    event_groups = {
        key: frame.sort_values("event_order").reset_index(drop=True)
        for key, frame in events.groupby(["game_pk", "at_bat_index"], sort=False)
    }
    action_groups = {
        key: frame.sort_values(["event_order", "action_id"]).reset_index(drop=True)
        for key, frame in actions.groupby(["game_pk", "at_bat_index"], sort=False)
    }
    history_lookup = history.set_index("event_key")
    source_lookup = selected.set_index("game_pk")
    memberships = _source_memberships(sources)
    names = _person_names(loaded)
    rows: list[dict[str, Any]] = []

    for window in windows.itertuples(index=False):
        game_pk = int(window.game_pk)
        pa = int(window.at_bat_index)
        group = event_groups[(game_pk, pa)]
        open_order = int(window.open_event_order)
        close_order = int(window.close_event_order)
        first = group.iloc[0]
        pre_first = open_order == -1
        anchor = None if pre_first else group.loc[group["event_order"].eq(open_order)].iloc[0]
        response_events = group.loc[
            group["event_order"].gt(open_order) & group["event_order"].le(close_order)
        ].copy()
        response_nonpitch = response_events.loc[~response_events["is_pitch"]]
        detail = action_groups.get((game_pk, pa), pd.DataFrame(columns=actions.columns))
        detail = detail.loc[
            detail["event_order"].gt(open_order) & detail["event_order"].le(close_order)
        ].copy()

        if pre_first:
            cutoff_sequence = int(first["game_sequence"]) - 1
            cutoff_timestamp = first["pa_start_time"]
            open_away_score = first["pre_away_score"]
            open_home_score = first["pre_home_score"]
            history_values = {
                "recorded_disengagements_since_reset_after_event": 0,
                "recorded_pitcher_pickoffs_since_reset_after_event": 0,
                "recorded_stepoffs_since_reset_after_event": 0,
                "recorded_unknown_pickoffs_since_reset_after_event": 0,
                "recorded_disengagements_prior_in_pa_after_event": 0,
                "recorded_disengagement_reset_count_after_event": 0,
            }
        else:
            cutoff_sequence = int(anchor["game_sequence"])
            cutoff_timestamp = anchor["end_time"]
            open_away_score = anchor["post_away_score"]
            open_home_score = anchor["post_home_score"]
            history_values = history_lookup.loc[anchor["event_key"]].to_dict()

        previous_pitches = group.loc[
            group["event_order"].le(open_order)
            & group["is_pitch"]
            & group["play_id"].notna()
        ]
        previous_pitch = previous_pitches.tail(1).iloc[0] if len(previous_pitches) else None
        source = source_lookup.loc[game_pk]
        top_half = str(window.half_inning).lower() == "top"
        batting_team = source["away_team"] if top_half else source["home_team"]
        pitching_team = source["home_team"] if top_half else source["away_team"]
        pitching_diff = (
            open_home_score - open_away_score
            if top_half
            else open_away_score - open_home_score
        )

        pitcher_pickoffs = detail.loc[
            detail["action_type"].eq("pickoff_throw")
            & detail["initiator_role"].eq("pitcher")
        ]
        catcher_pickoffs = detail.loc[
            detail["action_type"].eq("pickoff_throw")
            & detail["initiator_role"].eq("catcher")
        ]
        unknown_pickoffs = detail.loc[
            detail["action_type"].eq("pickoff_throw")
            & detail["initiator_role"].eq("unknown")
        ]
        all_pickoffs = detail.loc[detail["action_type"].eq("pickoff_throw")]
        steals = detail.loc[detail["action_type"].eq("steal_attempt")]
        stepoffs = detail.loc[detail["action_type"].eq("step_off")]
        audit_ids = _ids(window.action_ids)
        prepared_ids = set(detail["action_id"].astype(str))

        coarse_counts = response_nonpitch["action_category"].value_counts().to_dict()
        opening_runner_id = window.runner_id
        runner_change = False
        for event in response_events.itertuples(index=False):
            if event.bases_after == "1B" and pd.notna(event.runner_1b_after):
                if pd.notna(opening_runner_id) and int(event.runner_1b_after) != int(opening_runner_id):
                    runner_change = True
                    break
        pinch_runner_count = int(
            response_events["action_position_code"].astype(str).eq("12").sum()
        )

        first_response_start = response_events["start_time"].dropna().min()
        timestamp_order_valid = (
            bool(cutoff_timestamp <= first_response_start)
            if pd.notna(cutoff_timestamp) and pd.notna(first_response_start)
            else pd.NA
        )
        event_order_valid = bool(
            response_events["event_order"].gt(open_order).all()
            and response_events["event_order"].le(close_order).all()
        )

        unknown_classification = bool(detail["action_type"].eq("unknown_candidate").any())
        movement_anomaly = bool(
            response_events["movement_anomaly"].fillna("").astype(str).str.len().gt(0).any()
        )
        open_context_missing = any(
            pd.isna(value)
            for value in (
                window.pitcher_id,
                window.runner_id,
                window.open_balls,
                window.open_strikes,
                window.open_outs,
                open_away_score,
                open_home_score,
            )
        )
        ineligibility: list[str] = []
        if pd.isna(window.pitcher_id):
            ineligibility.append("missing_pitcher")
        if pd.isna(window.runner_id):
            ineligibility.append("missing_opening_runner")
        if runner_change:
            ineligibility.append("runner_identity_changed_within_window")
        if len(unknown_pickoffs):
            ineligibility.append("unknown_pickoff_initiator")
        if bool(window.known_state_conflict):
            ineligibility.append("known_state_conflict")
        if unknown_classification:
            ineligibility.append("unknown_action_classification")

        recorded_pickoff_count = len(all_pickoffs)
        recorded_steal_count = len(steals)
        opening_is_pitch = bool(anchor["is_pitch"] and pd.notna(anchor["play_id"])) if anchor is not None else False
        closing = response_events.loc[response_events["event_order"].eq(close_order)].iloc[-1]
        timing_value = np.nan
        secondary_eligible = False
        if (
            opening_is_pitch
            and bool(window.following_pitch_exists)
            and len(response_nonpitch) == 0
            and (anchor["call_description"] or anchor["description"]) in {"Ball", "Called Strike"}
            and pd.notna(anchor["start_time"])
            and pd.notna(closing["start_time"])
        ):
            timing_value = (closing["start_time"] - anchor["start_time"]).total_seconds()
            secondary_eligible = bool(timing_value > 0)

        row = {
            # Stable identifiers and source provenance.
            "opportunity_id": window.opportunity_id,
            "game_pk": game_pk,
            "official_date": window.official_date,
            "game_type": source.get("game_type", "R") if pd.notna(source.get("game_type", "R")) else "R",
            "away_team_id": source["away_team_id"],
            "away_team": source["away_team"],
            "home_team_id": source["home_team_id"],
            "home_team": source["home_team"],
            "batting_team": batting_team,
            "pitching_team": pitching_team,
            "venue_id": source["venue_id"],
            "venue": source["venue"],
            "source_sample_membership": memberships[game_pk],
            "selected_source_population": source["source_population"],
            "source_overlap_game": int(source["source_count_for_game"]) > 1,
            "source_cache_path": source["cache_path"],
            "source_url": source["feed_url"],
            "source_retrieved_utc": source["retrieved_utc"],
            "source_sha256": source["sha256"],
            "inning": window.inning,
            "half_inning": window.half_inning,
            "at_bat_index": pa,
            # A. Information available when the window opens.
            "pitcher_id": window.pitcher_id,
            "pitcher_name": window.pitcher_name,
            "opening_catcher_id": pd.NA,
            "opening_catcher_name": pd.NA,
            "opening_catcher_identity_status": "not_reconstructed_chronologically",
            "batter_id": window.batter_id,
            "batter_name": window.batter_name,
            "runner_id": window.runner_id,
            "runner_name": names.get(int(window.runner_id)) if pd.notna(window.runner_id) else pd.NA,
            "opening_base_state": "1B",
            "open_timing": window.open_timing,
            "open_anchor": window.open_anchor,
            "opening_anchor_event_index": anchor["event_index"] if anchor is not None else pd.NA,
            "opening_anchor_event_order": open_order if anchor is not None else pd.NA,
            "opening_anchor_event_key": anchor["event_key"] if anchor is not None else pd.NA,
            "opening_anchor_play_id": anchor["play_id"] if anchor is not None else pd.NA,
            "opening_anchor_is_actual_pitch": opening_is_pitch,
            "opening_anchor_event_type": (anchor["event_type"] or anchor["event_record_type"]) if anchor is not None else pd.NA,
            "opening_anchor_call": anchor["call_description"] if anchor is not None else pd.NA,
            "opening_anchor_description": anchor["description"] if anchor is not None else pd.NA,
            "feature_cutoff_game_sequence": cutoff_sequence,
            "feature_cutoff_event_order": open_order,
            "feature_cutoff_timestamp": cutoff_timestamp,
            "feature_cutoff_definition": "before_first_event" if pre_first else "after_opening_anchor_event",
            "open_balls": window.open_balls,
            "open_strikes": window.open_strikes,
            "open_outs": window.open_outs,
            "open_away_score": open_away_score,
            "open_home_score": open_home_score,
            "open_pitching_team_score_diff": pitching_diff,
            "previous_pitch_event_index": previous_pitch["event_index"] if previous_pitch is not None else pd.NA,
            "previous_pitch_play_id": previous_pitch["play_id"] if previous_pitch is not None else pd.NA,
            "previous_pitch_call": previous_pitch["call_description"] if previous_pitch is not None else pd.NA,
            "previous_pitch_description": previous_pitch["description"] if previous_pitch is not None else pd.NA,
            "recorded_disengagements_since_reset_at_open": history_values["recorded_disengagements_since_reset_after_event"],
            "recorded_pitcher_pickoffs_since_reset_at_open": history_values["recorded_pitcher_pickoffs_since_reset_after_event"],
            "recorded_stepoffs_since_reset_at_open": history_values["recorded_stepoffs_since_reset_after_event"],
            "recorded_unknown_pickoffs_since_reset_at_open": history_values["recorded_unknown_pickoffs_since_reset_after_event"],
            "recorded_disengagements_prior_in_pa_at_open": history_values["recorded_disengagements_prior_in_pa_after_event"],
            "recorded_disengagement_resets_prior_in_pa_at_open": history_values["recorded_disengagement_reset_count_after_event"],
            "disengagement_limit_without_penalty": DISENGAGEMENT_LIMIT,
            "disengagements_remaining_without_penalty": max(0, DISENGAGEMENT_LIMIT - int(history_values["recorded_disengagements_since_reset_after_event"])),
            "disengagement_limit_reached_at_open": int(history_values["recorded_disengagements_since_reset_after_event"]) >= DISENGAGEMENT_LIMIT,
            "disengagement_rule_version": DISENGAGEMENT_RULE,
            "disengagement_history_complete_within_pa": True,
            # Complete pre-game runner history is deliberately unavailable here.
            "runner_pre_game_history_complete": False,
            "runner_pre_game_history_missing_reason": "selective_cached_games_do_not_supply_complete_prior_history",
            "runner_prior_eligible_opportunities": pd.NA,
            "runner_prior_recorded_steal_attempts": pd.NA,
            "runner_prior_recorded_steal_successes": pd.NA,
            "runner_attempt_rate_shrunk": pd.NA,
            "runner_success_rate_shrunk": pd.NA,
            # B. Actions and outcomes observed after the feature cutoff.
            "response_action_ids": _pipe(detail["action_id"].astype(str).tolist()),
            "recorded_runner_control_action_count": len(detail),
            "recorded_pitcher_pickoff_count": len(pitcher_pickoffs),
            "recorded_pitcher_pickoff_indicator": len(pitcher_pickoffs) > 0,
            "recorded_catcher_pickoff_count": len(catcher_pickoffs),
            "recorded_catcher_pickoff_indicator": len(catcher_pickoffs) > 0,
            "recorded_unknown_initiator_pickoff_count": len(unknown_pickoffs),
            "recorded_unknown_initiator_pickoff_indicator": len(unknown_pickoffs) > 0,
            "recorded_any_pickoff_count": recorded_pickoff_count,
            "recorded_any_pickoff_indicator": recorded_pickoff_count > 0,
            "recorded_steal_attempt_count": recorded_steal_count,
            "recorded_steal_attempt_indicator": recorded_steal_count > 0,
            "recorded_pickoff_and_steal_indicator": recorded_pickoff_count > 0 and recorded_steal_count > 0,
            "recorded_no_pickoff_or_steal_indicator": recorded_pickoff_count == 0 and recorded_steal_count == 0,
            "recorded_stepoff_count": len(stepoffs),
            "recorded_stepoff_indicator": len(stepoffs) > 0,
            "recorded_balk_count": int(detail["action_type"].eq("balk").sum()),
            "recorded_disengagement_violation_count": int(detail["action_type"].eq("disengagement_violation").sum()),
            "recorded_timer_violation_count": int(detail["action_type"].eq("timer_violation").sum()),
            "recorded_pickoff_safe_return_count": int(all_pickoffs["outcome_type"].eq("safe_return").sum()),
            "recorded_pickoff_runner_out_count": int(all_pickoffs["runner_out"].fillna(False).sum()),
            "recorded_pickoff_caught_stealing_count": int(all_pickoffs["outcome_type"].eq("caught_stealing").sum()),
            "recorded_pickoff_error_advance_count": int(all_pickoffs["outcome_type"].eq("error_advance").sum()),
            "recorded_steal_success_count": int(steals["outcome_type"].isin(["advance", "error_advance", "advance_then_out"]).sum()),
            "recorded_steal_caught_count": int(steals["outcome_type"].eq("caught_stealing").sum()),
            "recorded_steal_advance_then_out_count": int(steals["outcome_type"].eq("advance_then_out").sum()),
            "recorded_runner_advance_indicator": bool(detail["runner_advance"].fillna(False).any()),
            "recorded_runner_out_indicator": bool(detail["runner_out"].fillna(False).any()),
            "coarse_nonpitch_event_count": len(response_nonpitch),
            "coarse_pickoff_event_count": int(coarse_counts.get("pickoff", 0)),
            "coarse_stepoff_event_count": int(coarse_counts.get("step_off", 0)),
            "coarse_timeout_event_count": int(coarse_counts.get("timeout", 0)),
            "coarse_mound_visit_event_count": int(coarse_counts.get("mound_visit", 0)),
            "coarse_substitution_event_count": int(coarse_counts.get("substitution", 0)),
            "coarse_other_nonpitch_event_count": int(coarse_counts.get("other_nonpitch", 0)),
            "close_event_index": window.close_event_index,
            "close_event_order": close_order,
            "close_event_key": closing["event_key"],
            "close_reason": window.close_reason,
            "following_pitch_exists": bool(window.following_pitch_exists),
            "following_pitch_play_id": window.following_pitch_play_id,
            "terminal_window": bool(window.terminal_without_pitch),
            "runner_identity_changed_within_window": runner_change,
            "pinch_runner_substitution_count": pinch_runner_count,
            "first_response_event_order": int(response_events["event_order"].min()),
            "last_response_event_order": int(response_events["event_order"].max()),
            "secondary_action_free_take_interval_eligible": secondary_eligible,
            "secondary_event_start_interval_seconds": timing_value if secondary_eligible else np.nan,
            # C. Data quality, eligibility, and split status.
            "action_population_eligible": True,
            "structural_response_model_eligible_preliminary": len(ineligibility) == 0,
            "structural_response_model_ineligibility_reason": _pipe(ineligibility),
            "threat_response_model_ready": False,
            "threat_response_not_ready_reason": "complete_pre_game_runner_history_not_collected",
            "known_state_conflict": bool(window.known_state_conflict),
            "movement_anomaly_within_window": movement_anomaly,
            "opening_context_missing": open_context_missing,
            "opening_runner_missing": pd.isna(window.runner_id),
            "opening_catcher_missing": True,
            "unknown_action_classification_within_window": unknown_classification,
            "unknown_pickoff_initiator_within_window": len(unknown_pickoffs) > 0,
            "feature_cutoff_event_order_valid": event_order_valid,
            "feature_cutoff_timestamp_order_valid": timestamp_order_valid,
            "action_assignment_matches_frozen_audit": audit_ids == prepared_ids,
            "dataset_role": "inspected_cached_development",
            "analysis_split": "development_only_not_final_test",
            "final_test_eligible": False,
        }
        rows.append(row)

    table = pd.DataFrame(rows).sort_values(
        ["official_date", "game_pk", "at_bat_index", "feature_cutoff_event_order"]
    ).reset_index(drop=True)
    supporting = {
        "sources": sources,
        "selected_sources": selected,
        "events": events,
        "actions": actions,
        "frozen_windows": windows,
        "disengagement_history": history,
        "disengagement_checks": history_checks,
    }
    return table, supporting


def build_population_summary(
    table: pd.DataFrame, supporting: dict[str, pd.DataFrame], root: Path
) -> pd.DataFrame:
    sources = supporting["sources"]
    tempo_join = pd.read_csv(root / "results" / "runner_control_tempo_interval_join.csv")
    interrupted_without_detail = int((~tempo_join["has_runner_control_detail"]).sum())
    metrics = [
        ("manifest_rows", len(sources), "source rows before game deduplication"),
        ("unique_cached_games", table["game_pk"].nunique(), "deduplicated game population"),
        ("feasibility_audit_games", sources.loc[sources["source_population"].eq("feasibility_audit"), "game_pk"].nunique(), "schedule-stratified audit source"),
        ("tempo_benchmark_games", sources.loc[sources["source_population"].eq("tempo_benchmark"), "game_pk"].nunique(), "games containing appearances by six selected benchmark pitchers"),
        ("overlap_games", int(sources.groupby("game_pk").size().gt(1).sum()), "deduplicated overlap"),
        ("first_game_date", table["official_date"].min(), "cached development coverage"),
        ("last_game_date", table["official_date"].max(), "cached development coverage"),
        ("unique_dates", table["official_date"].nunique(), "cached development coverage"),
        ("unique_teams", len(set(table["away_team"]).union(set(table["home_team"]))), "game participation"),
        ("unique_venues", table["venue"].nunique(), "cached development coverage"),
        ("unique_pitchers", table["pitcher_id"].nunique(), "window-opening identity"),
        ("unique_runners", table["runner_id"].nunique(), "window-opening identity"),
        ("opportunity_windows", len(table), "all frozen first-base-only windows"),
        ("recorded_pickoff_or_steal_windows", int((table["recorded_any_pickoff_indicator"] | table["recorded_steal_attempt_indicator"]).sum()), "explicit combined label"),
        ("recorded_pickoff_windows", int(table["recorded_any_pickoff_indicator"].sum()), "pitcher, catcher, or unknown initiator"),
        ("recorded_steal_windows", int(table["recorded_steal_attempt_indicator"].sum()), "recorded steal attempt"),
        ("recorded_pickoff_and_steal_windows", int(table["recorded_pickoff_and_steal_indicator"].sum()), "both types in one window"),
        ("recorded_pitcher_pickoff_windows", int(table["recorded_pitcher_pickoff_indicator"].sum()), "primary future response"),
        ("recorded_catcher_pickoff_windows", int(table["recorded_catcher_pickoff_indicator"].sum()), "separate response"),
        ("recorded_unknown_initiator_pickoff_windows", int(table["recorded_unknown_initiator_pickoff_indicator"].sum()), "preserved unknown"),
        ("recorded_steal_attempt_windows", int(table["recorded_steal_attempt_indicator"].sum()), "separate runner response"),
        ("recorded_no_pickoff_or_steal_windows", int(table["recorded_no_pickoff_or_steal_indicator"].sum()), "no recorded action, not confirmed absence"),
        ("terminal_windows", int(table["terminal_window"].sum()), "retained without requiring a following pitch"),
        ("windows_with_following_pitch", int(table["following_pitch_exists"].sum()), "closure at next actual pitch"),
        ("pre_first_event_windows", int(table["open_timing"].eq("before_first_event").sum()), "opens before first event/pitch"),
        ("runner_identity_change_windows", int(table["runner_identity_changed_within_window"].sum()), "retained and flagged"),
        ("opening_catcher_missing_windows", int(table["opening_catcher_missing"].sum()), "not inferred from final lineup"),
        ("incomplete_pre_game_runner_history_windows", int((~table["runner_pre_game_history_complete"]).sum()), "blocks threat modeling"),
        ("secondary_action_free_take_intervals", int(table["secondary_action_free_take_interval_eligible"].sum()), "secondary event-start sensitivity only"),
        ("interrupted_benchmark_intervals_without_mapped_runner_control", interrupted_without_detail, "coarse nonpitch actions retained separately"),
    ]
    return pd.DataFrame(metrics, columns=["metric", "value", "definition"])


def build_exclusion_summary(table: pd.DataFrame) -> pd.DataFrame:
    rows = [
        ("frozen_action_population", len(table), "retained", "all first-base-only windows"),
        ("terminal_without_next_pitch", int(table["terminal_window"].sum()), "retained", "later pitch is not an eligibility condition"),
        ("runner_identity_changed_within_window", int(table["runner_identity_changed_within_window"].sum()), "flagged_for_model_review", "occupancy window retained; opening runner no longer describes full exposure"),
        ("unknown_pickoff_initiator", int(table["unknown_pickoff_initiator_within_window"].sum()), "preserved_separately", "not coded as pitcher or catcher"),
        ("unknown_action_classification", int(table["unknown_action_classification_within_window"].sum()), "preserved_separately", "not silently coerced"),
        ("known_state_conflict", int(table["known_state_conflict"].sum()), "preserved_separately", "game 746690 PA 38 contributes no windows"),
        ("opening_catcher_not_reconstructed", int(table["opening_catcher_missing"].sum()), "missing_predictor", "requires verified chronological defense reconstruction"),
        ("complete_pre_game_runner_history_unavailable", int((~table["runner_pre_game_history_complete"]).sum()), "blocks_threat_model", "selective cache cannot provide denominators"),
        ("preliminary_structural_response_ineligible", int((~table["structural_response_model_eligible_preliminary"]).sum()), "not_dropped_from_table", "identity/classification flags only"),
        ("secondary_action_free_take_interval", int(table["secondary_action_free_take_interval_eligible"].sum()), "secondary_subset", "conditioning on no action can select on post-threat behavior"),
    ]
    return pd.DataFrame(rows, columns=["category", "windows", "treatment", "reason"])


def build_coverage(table: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    def summarize(dimension: str, id_column: str | None, name_column: str) -> None:
        keys = [name_column] if id_column is None else [id_column, name_column]
        summary = (
            table.groupby(keys, dropna=False)
            .agg(
                games=("game_pk", "nunique"),
                windows=("opportunity_id", "size"),
                recorded_pitcher_pickoff_windows=("recorded_pitcher_pickoff_indicator", "sum"),
                recorded_catcher_pickoff_windows=("recorded_catcher_pickoff_indicator", "sum"),
                recorded_steal_windows=("recorded_steal_attempt_indicator", "sum"),
                terminal_windows=("terminal_window", "sum"),
            )
            .reset_index()
        )
        summary.insert(0, "dimension", dimension)
        summary["dimension_id"] = summary[id_column].astype(str) if id_column else summary[name_column].astype(str)
        summary["dimension_name"] = summary[name_column].astype(str)
        frames.append(summary[[
            "dimension", "dimension_id", "dimension_name", "games", "windows",
            "recorded_pitcher_pickoff_windows", "recorded_catcher_pickoff_windows",
            "recorded_steal_windows", "terminal_windows",
        ]])

    summarize("date", None, "official_date")
    summarize("pitching_team", None, "pitching_team")
    summarize("venue", "venue_id", "venue")
    summarize("pitcher", "pitcher_id", "pitcher_name")
    summarize("runner", "runner_id", "runner_name")
    return pd.concat(frames, ignore_index=True).sort_values(
        ["dimension", "dimension_name", "dimension_id"]
    ).reset_index(drop=True)


def proposed_splits() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("history_only", "2022-04-07", "2022-10-05", False, False, "pregame priors only; old rule environment retained as labeled history"),
            ("training", "2023-03-30", "2023-10-01", True, True, "fit baselines, regularized models, preprocessing, and shrinkage"),
            ("validation", "2024-03-20", "2024-09-30", False, True, "select features and penalties; cached subset is already inspected"),
            ("final_test", "2025-03-18", "2025-09-28", False, False, "locked one-time evaluation; whole games only"),
        ],
        columns=["split", "start_date", "end_date", "fit_parameters", "tuning_allowed", "use"],
    ).assign(game_separation="whole_game", chronological_order="strict")


def additional_data_needed() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (1, "Complete regular-season schedules and live feeds", "2022 history plus every 2023-2025 regular-season game", "Build unbiased denominators and pre-game histories; preserve URLs, retrieval times, and checksums", "required_before_modeling"),
            (2, "Chronological catcher identity", "Starting defensive alignments plus every catcher substitution for collected games", "Opening catcher cannot be inferred from the final lineup and is a planned context variable", "required_before_catcher_adjustment"),
            (3, "Forward runner opportunity/attempt/success histories", "All eligible windows dated strictly before each game", "Generate leakage-safe attempt and conditional-success predictors with training-estimated shrinkage", "required_before_modeling"),
            (4, "As-of player metadata", "Handedness and roster/team identity available on each game date", "Opening context and sparse/new-player handling", "required_before_modeling"),
            (5, "Lagged Statcast sprint-speed snapshots", "Prior-season value or documented pre-game snapshot only", "Optional threat feature; final-season values would leak future information", "optional_after_primary_baseline"),
            (6, "Expanded independent action review", "Event-complete source or video sample for positive and no-recorded-action windows", "Estimate label sensitivity where feasible; absence is currently unvalidated", "recommended_for_interpretation"),
            (7, "Continuous video release annotations", "Frozen video sample only", "Required only for any release-tempo claim; not required for recorded-pickoff analysis", "required_only_for_timing_secondary"),
        ],
        columns=["priority", "data", "scope", "reason", "status"],
    )


def build_feature_dictionary(table: pd.DataFrame) -> pd.DataFrame:
    """Create one dictionary row per development-table column."""
    specs: dict[str, dict[str, str]] = {}

    def add(fields: list[str], group: str, availability: str, role: str, source: str, denominator: str, missing: str, leakage: str) -> None:
        for field in fields:
            specs[field] = {
                "field": field,
                "group": group,
                "definition": field.replace("_", " "),
                "source": source,
                "availability_time": availability,
                "analysis_role": role,
                "denominator": denominator,
                "missing_data_handling": missing,
                "leakage_rule": leakage,
            }

    add(
        ["opportunity_id", "game_pk", "official_date", "game_type", "away_team_id", "away_team", "home_team_id", "home_team", "batting_team", "pitching_team", "venue_id", "venue", "source_sample_membership", "selected_source_population", "source_overlap_game", "source_cache_path", "source_url", "source_retrieved_utc", "source_sha256", "inning", "half_inning", "at_bat_index"],
        "identifier_provenance", "before_window_opens", "identifier", "manifest/live feed", "one row per frozen opportunity", "never impute identifiers; retain source missingness", "not a response predictor unless explicitly listed",
    )
    opening_fields = [
        "pitcher_id", "pitcher_name", "opening_catcher_id", "opening_catcher_name", "opening_catcher_identity_status", "batter_id", "batter_name", "runner_id", "runner_name", "opening_base_state", "open_timing", "open_anchor", "opening_anchor_event_index", "opening_anchor_event_order", "opening_anchor_event_key", "opening_anchor_play_id", "opening_anchor_is_actual_pitch", "opening_anchor_event_type", "opening_anchor_call", "opening_anchor_description", "feature_cutoff_game_sequence", "feature_cutoff_event_order", "feature_cutoff_timestamp", "feature_cutoff_definition", "open_balls", "open_strikes", "open_outs", "open_away_score", "open_home_score", "open_pitching_team_score_diff", "previous_pitch_event_index", "previous_pitch_play_id", "previous_pitch_call", "previous_pitch_description", "recorded_disengagements_since_reset_at_open", "recorded_pitcher_pickoffs_since_reset_at_open", "recorded_stepoffs_since_reset_at_open", "recorded_unknown_pickoffs_since_reset_at_open", "recorded_disengagements_prior_in_pa_at_open", "recorded_disengagement_resets_prior_in_pa_at_open", "disengagement_limit_without_penalty", "disengagements_remaining_without_penalty", "disengagement_limit_reached_at_open", "disengagement_rule_version", "disengagement_history_complete_within_pa",
    ]
    add(opening_fields, "A_opening_information", "at_feature_cutoff", "candidate_predictor_or_context", "chronological live-feed reconstruction", "all opportunity windows", "use explicit missing indicator; do not infer catcher from final lineup", "may be used only if known at or before feature cutoff")
    history_fields = ["runner_pre_game_history_complete", "runner_pre_game_history_missing_reason", "runner_prior_eligible_opportunities", "runner_prior_recorded_steal_attempts", "runner_prior_recorded_steal_successes", "runner_attempt_rate_shrunk", "runner_success_rate_shrunk"]
    add(history_fields, "A_pre_game_history", "strictly_before_game", "planned_threat_predictor", "future complete historical opportunity dataset", "runner-games with complete prior coverage", "currently missing by design; pooled prior for new/sparse players after collection", "never derive from current/future game or final-season totals")
    outcome_fields = [column for column in table.columns if column.startswith("recorded_") and column not in opening_fields and column not in history_fields]
    add(outcome_fields, "B_window_actions_outcomes", "after_window_closes", "outcome_or_diagnostic", "linked action records within window", "all opportunity windows unless field states another denominator", "retain zero as no recorded event; unknown initiator remains separate", "never use as a predictor for the same window")
    coarse_fields = [column for column in table.columns if column.startswith("coarse_")]
    add(coarse_fields, "B_window_actions_outcomes", "after_window_closes", "diagnostic_outcome", "all nonpitch play events within window", "all opportunity windows", "retain explicit zero and raw category", "post-cutoff; never use as same-window predictor")
    closure_fields = ["response_action_ids", "close_event_index", "close_event_order", "close_event_key", "close_reason", "following_pitch_exists", "following_pitch_play_id", "terminal_window", "runner_identity_changed_within_window", "pinch_runner_substitution_count", "first_response_event_order", "last_response_event_order", "secondary_action_free_take_interval_eligible", "secondary_event_start_interval_seconds"]
    add(closure_fields, "B_window_closure", "after_window_closes", "outcome_or_eligibility", "chronological window reconstruction", "all windows; timing value only on labeled secondary subset", "retain terminal/missing next pitch; timing otherwise missing", "post-cutoff; action-free eligibility is selection on post-threat behavior")
    quality_fields = [column for column in table.columns if column not in specs]
    add(quality_fields, "C_quality_eligibility", "audit_time", "quality_flag", "derived audit checks", "all opportunity windows", "preserve unknown/missing states; never recode to confirmed absence", "flags determine reporting/eligibility, not predictor values")

    # Replace generic definitions for the fields most likely to be misused.
    overrides = {
        "recorded_pitcher_pickoff_indicator": "One or more feed-recorded pickoff throws initiated by the pitcher after cutoff and before closure; primary future response.",
        "recorded_catcher_pickoff_indicator": "One or more feed-recorded catcher-initiated pickoff throws; separate from primary response.",
        "recorded_unknown_initiator_pickoff_indicator": "One or more recorded pickoffs whose pitcher/catcher initiator is unresolved; never coded as pitcher or catcher.",
        "recorded_steal_attempt_indicator": "One or more feed-recorded stolen-base or caught-stealing attempts within the response window.",
        "recorded_pickoff_and_steal_indicator": "Both a recorded pickoff and recorded steal attempt occur in the same window; nonexclusive combined label.",
        "recorded_no_pickoff_or_steal_indicator": "No pickoff or steal is recorded in the feed window; this is not confirmed real-world absence.",
        "runner_attempt_rate_shrunk": "Training-estimated shrinkage of prior recorded steal attempts divided by prior eligible opportunities, generated strictly before the game.",
        "runner_success_rate_shrunk": "Training-estimated shrinkage of prior recorded successes divided by prior recorded attempts, generated strictly before the game.",
        "feature_cutoff_event_order": "Last event order whose information may enter predictors; all response events have a strictly larger order.",
        "recorded_disengagements_since_reset_at_open": "Recorded pitcher pickoffs plus step-offs since the most recent runner advance in the plate appearance, measured after the opening anchor.",
        "secondary_event_start_interval_seconds": "Following pitch event start minus opening pitch event start for action-free same-PA windows following a take; not release tempo.",
    }
    for field, definition in overrides.items():
        specs[field]["definition"] = definition
    dictionary = pd.DataFrame([specs[column] for column in table.columns])
    if set(dictionary["field"]) != set(table.columns):
        raise ValueError("Feature dictionary does not cover every development-table field")
    return dictionary


def validate_outputs(
    table: pd.DataFrame,
    supporting: dict[str, pd.DataFrame],
    population: pd.DataFrame,
    splits: pd.DataFrame,
) -> pd.DataFrame:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append((name, bool(passed), detail))

    pickoff = table["recorded_any_pickoff_indicator"]
    steal = table["recorded_steal_attempt_indicator"]
    record("unique_opportunity_id", table["opportunity_id"].is_unique, "stable one-row key")
    record("window_count", len(table) == EXPECTED_ACCOUNTING["windows"], str(len(table)))
    record("pickoff_window_identity", int(pickoff.sum()) == EXPECTED_ACCOUNTING["pickoff_windows"], str(int(pickoff.sum())))
    record("steal_window_identity", int(steal.sum()) == EXPECTED_ACCOUNTING["steal_windows"], str(int(steal.sum())))
    record("combined_window_identity", int((pickoff & steal).sum()) == EXPECTED_ACCOUNTING["combined_windows"], str(int((pickoff & steal).sum())))
    record("union_window_identity", int((pickoff | steal).sum()) == EXPECTED_ACCOUNTING["pickoff_or_steal_windows"], str(int((pickoff | steal).sum())))
    record("action_assignments_match", bool(table["action_assignment_matches_frozen_audit"].all()), "no duplicate or missing action joins")
    assigned_action_ids = [
        action_id
        for value in table["response_action_ids"]
        for action_id in _ids(value)
    ]
    record(
        "action_assignment_unique_across_windows",
        len(assigned_action_ids) == len(set(assigned_action_ids)),
        f"{len(assigned_action_ids)} assigned records",
    )
    record("terminal_windows_retained", int(table["terminal_window"].sum()) == 315, str(int(table["terminal_window"].sum())))
    record("cutoff_event_order", bool(table["feature_cutoff_event_order_valid"].all()), "all response orders exceed cutoff")
    record("predictor_outcome_separation", not any(column.startswith("recorded_") for column in ["runner_attempt_rate_shrunk", "runner_success_rate_shrunk"]), "history fields are pre-game placeholders")
    record("incomplete_history_explicit", bool((~table["runner_pre_game_history_complete"]).all()), "all selective-cache histories marked incomplete")
    record("unknown_states_preserved", "recorded_unknown_initiator_pickoff_indicator" in table and "unknown_action_classification_within_window" in table, "separate flags")
    record("no_cached_final_test", bool((~table["final_test_eligible"]).all()), "cached games are development only")
    split_dates = splits.assign(start=pd.to_datetime(splits["start_date"]), end=pd.to_datetime(splits["end_date"]))
    ordered = bool((split_dates["start"].iloc[1:].reset_index(drop=True) > split_dates["end"].iloc[:-1].reset_index(drop=True)).all())
    record("split_integrity", ordered, "nonoverlapping chronological periods")
    record("population_summary_present", population["metric"].eq("opportunity_windows").any(), "population artifact")
    history_checks = supporting["disengagement_checks"]
    available = history_checks.loc[history_checks["raw_number_available"]]
    record("disengagement_raw_number_agreement", bool(available["raw_number_matches"].all()), f"{len(available)} comparable records")
    result = pd.DataFrame(checks, columns=["check", "passed", "detail"])
    if not result["passed"].all():
        failures = result.loc[~result["passed"], "check"].tolist()
        raise AssertionError(f"Opportunity preparation checks failed: {failures}")
    return result


def run_preparation(root: Path, *, write: bool = True) -> dict[str, pd.DataFrame]:
    table, supporting = prepare_opportunity_table(root)
    population = build_population_summary(table, supporting, root)
    exclusions = build_exclusion_summary(table)
    coverage = build_coverage(table)
    splits = proposed_splits()
    dictionary = build_feature_dictionary(table)
    needed = additional_data_needed()
    checks = validate_outputs(table, supporting, population, splits)
    environment = pd.DataFrame(
        [
            ("python", platform.python_version()),
            ("pandas", pd.__version__),
            ("numpy", np.__version__),
            ("generated_date", "2026-11-15"),
            ("dataset_role", "inspected_cached_development"),
        ],
        columns=["item", "value"],
    )
    outputs = {
        "opportunities": table,
        "feature_dictionary": dictionary,
        "population_summary": population,
        "exclusion_summary": exclusions,
        "coverage": coverage,
        "proposed_splits": splits,
        "additional_data_needed": needed,
        "disengagement_checks": supporting["disengagement_checks"],
        "validation_checks": checks,
        "environment": environment,
    }
    if write:
        output_paths = {
            "opportunities": "opportunity_development_table.csv",
            "feature_dictionary": "opportunity_feature_dictionary.csv",
            "population_summary": "opportunity_population_summary.csv",
            "exclusion_summary": "opportunity_exclusion_summary.csv",
            "coverage": "opportunity_coverage.csv",
            "proposed_splits": "opportunity_proposed_splits.csv",
            "additional_data_needed": "opportunity_additional_data_needed.csv",
            "disengagement_checks": "opportunity_disengagement_checks.csv",
            "validation_checks": "opportunity_validation_checks.csv",
            "environment": "opportunity_environment.csv",
        }
        for key, filename in output_paths.items():
            outputs[key].to_csv(root / "results" / filename, index=False)
    return outputs


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    generated = run_preparation(project_root, write=True)
    print(generated["population_summary"].to_string(index=False))
