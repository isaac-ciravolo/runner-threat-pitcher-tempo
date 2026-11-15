"""Helpers for the public MLB feed feasibility audit.

The functions preserve every play event and runner movement.  They deliberately
call differences between pitch-event start timestamps "event-start intervals";
the feed fields have not been validated as ball-release measurements.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


BASES = ("1B", "2B", "3B")
FRACTION_RE = re.compile(r"\.(\d+)(?:Z|[+-]\d\d:\d\d)$")


def _value(mapping: dict[str, Any] | None, *keys: str) -> Any:
    current: Any = mapping or {}
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _joined(values: Iterable[Any]) -> str:
    return " | ".join(str(value) for value in values if value not in (None, ""))


def _base_string(bases: dict[str, Any]) -> str:
    occupied = [base for base in BASES if base in bases]
    return "+".join(occupied) if occupied else "empty"


def _fractional_digits(value: Any) -> float:
    if not isinstance(value, str):
        return np.nan
    match = FRACTION_RE.search(value)
    return float(len(match.group(1))) if match else 0.0


def _men_on_bucket(base_state: Any) -> str | None:
    if not isinstance(base_state, str):
        return None
    occupied = set() if base_state == "empty" else set(base_state.split("+"))
    if occupied == set():
        return "Empty"
    if occupied == set(BASES):
        return "Loaded"
    if "2B" in occupied or "3B" in occupied:
        return "RISP"
    return "Men_On"


def load_feeds(root: Path) -> tuple[pd.DataFrame, list[tuple[pd.Series, dict[str, Any]]]]:
    manifest = pd.read_csv(root / "data" / "audit_sample_manifest.csv")
    loaded: list[tuple[pd.Series, dict[str, Any]]] = []
    for _, manifest_row in manifest.sort_values("selection_order").iterrows():
        path = root / str(manifest_row["cache_path"])
        if not path.exists():
            continue
        feed = json.loads(path.read_text(encoding="utf-8"))
        if int(feed.get("gamePk", -1)) != int(manifest_row["game_pk"]):
            raise ValueError(f"{path}: gamePk does not match the sample manifest")
        loaded.append((manifest_row, feed))
    return manifest, loaded


def _movement_text(item: dict[str, Any]) -> str:
    movement = item.get("movement", {})
    details = item.get("details", {})
    runner = _value(details, "runner", "fullName") or _value(details, "runner", "id")
    start = movement.get("start") or movement.get("originBase") or "plate"
    if movement.get("isOut"):
        destination = f"out@{movement.get('outBase') or '?'}"
    else:
        destination = movement.get("end") or "none"
    event_type = details.get("eventType") or details.get("event") or "unlabeled"
    return f"{runner}: {start}->{destination} ({event_type})"


def _apply_movements(
    bases: dict[str, Any],
    movements: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Apply runner movements while respecting multi-segment paths.

    The feed can encode one runner as multiple records tied to one play index
    (for example, 1B->3B followed by 3B->score).  Those records describe one
    path, not two simultaneous runners.  Collapse each runner to the origin
    present before the event and the last recorded destination, then remove all
    origins before filling destinations.
    """
    updated = bases.copy()
    anomalies: list[str] = []
    paths: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for position, item in enumerate(movements):
        runner_id = _value(item, "details", "runner", "id")
        key = runner_id if runner_id is not None else ("unknown", position)
        paths[key].append(item)

    normalized: list[tuple[Any, str | None, str | None, bool]] = []
    for key, items in paths.items():
        runner_id = None if isinstance(key, tuple) else key
        first_movement = items[0].get("movement", {})
        first_start = first_movement.get("start") or first_movement.get("originBase")
        starts = [
            item.get("movement", {}).get("start")
            or item.get("movement", {}).get("originBase")
            for item in items
        ]
        if first_start is None:
            start = None
        else:
            present_starts = [
                start for start in starts if start in BASES and updated.get(start) == runner_id
            ]
            start = present_starts[0] if present_starts else next(
                (candidate for candidate in starts if candidate in BASES), None
            )
        last_movement = items[-1].get("movement", {})
        end = last_movement.get("end")
        is_out = any(bool(item.get("movement", {}).get("isOut")) for item in items)
        normalized.append((runner_id, start, end, is_out))

    for runner_id, start, _end, _is_out in normalized:
        if start in BASES:
            observed = updated.get(start)
            if observed is None:
                anomalies.append(f"missing runner at {start} for runner {runner_id}")
            elif runner_id is not None and observed != runner_id:
                anomalies.append(
                    f"runner mismatch at {start}: expected {runner_id}, observed {observed}"
                )
            updated.pop(start, None)
        elif runner_id is not None:
            for base, observed in list(updated.items()):
                if observed == runner_id:
                    updated.pop(base)
                    if start not in (None, ""):
                        anomalies.append(
                            f"runner {runner_id} found at {base}, movement start was {start}"
                        )
                    break

    for runner_id, _start, end, is_out in normalized:
        if not is_out and end in BASES:
            if end in updated and updated[end] != runner_id:
                anomalies.append(
                    f"occupied destination {end}: {updated[end]} replaced by {runner_id}"
                )
            updated[end] = runner_id

    return updated, anomalies


def extract_events(
    loaded_feeds: list[tuple[pd.Series, dict[str, Any]]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    event_rows: list[dict[str, Any]] = []
    state_rows: list[dict[str, Any]] = []

    for manifest_row, feed in loaded_feeds:
        game_pk = int(feed["gamePk"])
        bases: dict[str, Any] = {}
        current_half: tuple[int, str] | None = None
        current_outs = 0
        away_score = 0
        home_score = 0
        game_sequence = 0

        plays = _value(feed, "liveData", "plays", "allPlays") or []
        for play_order, play in enumerate(plays):
            about = play.get("about", {})
            half_key = (about.get("inning"), about.get("halfInning"))
            if half_key != current_half:
                bases = {}
                current_outs = 0
                current_half = half_key

            pa_start_bases = _base_string(bases)
            pa_start_outs = current_outs
            at_bat_index = about.get("atBatIndex")
            matchup = play.get("matchup", {})
            result = play.get("result", {})
            movements_by_index: dict[Any, list[dict[str, Any]]] = defaultdict(list)
            for movement in play.get("runners", []):
                movements_by_index[_value(movement, "details", "playIndex")].append(movement)

            play_events = play.get("playEvents", [])
            event_indexes = {event.get("index") for event in play_events}
            unresolved = [
                movement
                for index, items in movements_by_index.items()
                if index not in event_indexes
                for movement in items
            ]
            previous_balls = 0
            previous_strikes = 0
            previous_outs = current_outs
            play_anomalies: list[str] = []

            for event_order, event in enumerate(play_events):
                game_sequence += 1
                details = event.get("details", {})
                count = event.get("count", {})
                event_index = event.get("index")
                tied_movements = movements_by_index.get(event_index, [])
                bases_before = bases.copy()
                action_state_anomalies: list[str] = []
                action_base = event.get("base")
                action_base_label = f"{action_base}B" if action_base in (1, 2, 3) else None
                action_player_id = _value(event, "player", "id")
                if details.get("eventType") == "runner_placed" and action_base_label:
                    if action_base_label in bases:
                        action_state_anomalies.append(
                            f"runner_placed replaced occupied {action_base_label}"
                        )
                    bases[action_base_label] = action_player_id
                if _value(event, "position", "code") == "12" and action_base_label:
                    if action_base_label not in bases:
                        action_state_anomalies.append(
                            f"pinch runner assigned to empty {action_base_label}"
                        )
                    bases[action_base_label] = action_player_id
                bases, movement_anomalies = _apply_movements(bases, tied_movements)
                movement_anomalies = action_state_anomalies + movement_anomalies
                play_anomalies.extend(movement_anomalies)

                pre_away_score = away_score
                pre_home_score = home_score
                if details.get("awayScore") is not None:
                    away_score = details["awayScore"]
                if details.get("homeScore") is not None:
                    home_score = details["homeScore"]

                movement_event_types = [
                    _value(item, "details", "eventType") or _value(item, "details", "event")
                    for item in tied_movements
                ]
                event_rows.append(
                    {
                        "selection_order": int(manifest_row["selection_order"]),
                        "period": manifest_row["period"],
                        "game_pk": game_pk,
                        "official_date": manifest_row["official_date"],
                        "away_team": manifest_row["away_team"],
                        "home_team": manifest_row["home_team"],
                        "venue": manifest_row["venue"],
                        "play_order": play_order,
                        "game_sequence": game_sequence,
                        "at_bat_index": at_bat_index,
                        "event_order": event_order,
                        "event_index": event_index,
                        "inning": about.get("inning"),
                        "half_inning": about.get("halfInning"),
                        "pa_is_complete": about.get("isComplete"),
                        "pa_start_time_raw": about.get("startTime"),
                        "pa_end_time_raw": about.get("endTime"),
                        "pitcher_id": _value(matchup, "pitcher", "id"),
                        "pitcher_name": _value(matchup, "pitcher", "fullName"),
                        "batter_id": _value(matchup, "batter", "id"),
                        "batter_name": _value(matchup, "batter", "fullName"),
                        "matchup_men_on_base": _value(matchup, "splits", "menOnBase"),
                        "event_record_type": event.get("type"),
                        "is_pitch": bool(event.get("isPitch")),
                        "pitch_number": event.get("pitchNumber"),
                        "play_id": event.get("playId"),
                        "action_play_id": event.get("actionPlayId"),
                        "action_player_id": _value(event, "player", "id"),
                        "replaced_player_id": _value(event, "replacedPlayer", "id"),
                        "action_position_code": _value(event, "position", "code"),
                        "action_position_name": _value(event, "position", "name"),
                        "is_substitution": bool(event.get("isSubstitution")),
                        "event_type": details.get("eventType"),
                        "event_name": details.get("event"),
                        "description": details.get("description"),
                        "call_code": _value(details, "call", "code") or details.get("code"),
                        "call_description": _value(details, "call", "description"),
                        "start_time_raw": event.get("startTime"),
                        "end_time_raw": event.get("endTime"),
                        "derived_pre_balls": previous_balls,
                        "derived_pre_strikes": previous_strikes,
                        "derived_pre_outs": previous_outs,
                        "feed_count_balls": count.get("balls"),
                        "feed_count_strikes": count.get("strikes"),
                        "feed_count_outs": count.get("outs"),
                        "pre_away_score": pre_away_score,
                        "pre_home_score": pre_home_score,
                        "post_away_score": away_score,
                        "post_home_score": home_score,
                        "bases_before": _base_string(bases_before),
                        "bases_after": _base_string(bases),
                        "movement_count": len(tied_movements),
                        "movement_event_types": _joined(movement_event_types),
                        "movement_summary": _joined(_movement_text(item) for item in tied_movements),
                        "movement_anomaly": _joined(movement_anomalies),
                        "play_result_event": result.get("event"),
                        "play_result_event_type": result.get("eventType"),
                        "play_result_description": result.get("description"),
                    }
                )
                if count.get("balls") is not None:
                    previous_balls = count["balls"]
                if count.get("strikes") is not None:
                    previous_strikes = count["strikes"]
                if count.get("outs") is not None:
                    previous_outs = count["outs"]
                    current_outs = count["outs"]

            if unresolved:
                bases, unresolved_anomalies = _apply_movements(bases, unresolved)
                play_anomalies.extend(unresolved_anomalies)
            half_inning_ended = current_outs >= 3 or any(
                _value(movement, "movement", "outNumber") == 3
                for movement in play.get("runners", [])
            )
            if half_inning_ended:
                bases = {}
            if result.get("awayScore") is not None:
                away_score = result["awayScore"]
            if result.get("homeScore") is not None:
                home_score = result["homeScore"]

            state_rows.append(
                {
                    "game_pk": game_pk,
                    "official_date": manifest_row["official_date"],
                    "at_bat_index": at_bat_index,
                    "inning": about.get("inning"),
                    "half_inning": about.get("halfInning"),
                    "matchup_men_on_base": _value(matchup, "splits", "menOnBase"),
                    "reconstructed_pa_start_bases": pa_start_bases,
                    "pa_start_outs": pa_start_outs,
                    "reconstructed_pa_end_bases": _base_string(bases),
                    "half_inning_ended": half_inning_ended,
                    "unresolved_movement_count": len(unresolved),
                    "movement_anomaly_count": len(play_anomalies),
                    "movement_anomalies": _joined(play_anomalies),
                    "play_result_event_type": result.get("eventType"),
                    "play_result_away_score": result.get("awayScore"),
                    "play_result_home_score": result.get("homeScore"),
                }
            )

    events = pd.DataFrame(event_rows)
    state_audit = pd.DataFrame(state_rows)
    for raw_column, parsed_column in (
        ("start_time_raw", "start_time"),
        ("end_time_raw", "end_time"),
        ("pa_start_time_raw", "pa_start_time"),
        ("pa_end_time_raw", "pa_end_time"),
    ):
        events[parsed_column] = pd.to_datetime(events[raw_column], utc=True, errors="coerce")
    events["start_fractional_digits"] = events["start_time_raw"].map(_fractional_digits)
    events["end_fractional_digits"] = events["end_time_raw"].map(_fractional_digits)
    events["event_key"] = (
        events["game_pk"].astype(str)
        + ":"
        + events["at_bat_index"].astype(str)
        + ":"
        + events["event_index"].astype(str)
    )
    events["action_category"] = events.apply(classify_action, axis=1)
    first_pitch_states = (
        events.loc[events["is_pitch"]]
        .sort_values(["game_pk", "play_order", "event_order"])
        .groupby(["game_pk", "at_bat_index"], as_index=False)
        .first()[["game_pk", "at_bat_index", "bases_before"]]
        .rename(columns={"bases_before": "reconstructed_before_first_pitch"})
    )
    state_audit = state_audit.merge(
        first_pitch_states, on=["game_pk", "at_bat_index"], how="left", validate="one_to_one"
    )
    state_audit["reconstructed_start_bucket"] = state_audit[
        "reconstructed_before_first_pitch"
    ].map(_men_on_bucket)
    state_audit["reconstructed_end_bucket"] = state_audit[
        "reconstructed_pa_end_bases"
    ].map(_men_on_bucket)
    state_audit["matchup_matches_start"] = (
        state_audit["matchup_men_on_base"].eq(state_audit["reconstructed_start_bucket"])
        & state_audit["reconstructed_start_bucket"].notna()
    )
    state_audit["matchup_matches_end"] = (
        state_audit["matchup_men_on_base"].eq(state_audit["reconstructed_end_bucket"])
        & state_audit["reconstructed_end_bucket"].notna()
    )
    return events, state_audit


def classify_action(row: pd.Series) -> str:
    if bool(row.get("is_pitch")):
        return "pitch"
    text = " ".join(
        str(row.get(column) or "").lower()
        for column in ("event_type", "event_name", "description")
    ).replace("-", "_")
    if "pickoff" in text:
        return "pickoff"
    if "step_off" in text or "step off" in text:
        return "step_off"
    if "timeout" in text or "time out" in text:
        return "timeout"
    if "mound_visit" in text or "mound visit" in text:
        return "mound_visit"
    if any(term in text for term in ("substitution", "pitching change", "defensive switch")):
        return "substitution"
    return "other_nonpitch"


def build_intervals(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_columns = ["game_pk", "at_bat_index"]
    for (_game_pk, _at_bat_index), group in events.groupby(group_columns, sort=False):
        ordered = group.sort_values("event_order")
        pitches = ordered.loc[ordered["is_pitch"]].copy()
        if len(pitches) < 2:
            continue
        pitch_positions = list(pitches.index)
        ordered_positions = {index: position for position, index in enumerate(ordered.index)}
        for preceding_index, following_index in zip(pitch_positions, pitch_positions[1:]):
            preceding = events.loc[preceding_index]
            following = events.loc[following_index]
            start_position = ordered_positions[preceding_index]
            end_position = ordered_positions[following_index]
            intervening = ordered.iloc[start_position + 1 : end_position]
            nonpitch = intervening.loc[~intervening["is_pitch"]]
            categories = set(nonpitch["action_category"])
            substitution_text = " ".join(
                nonpitch[["event_type", "description"]]
                .fillna("")
                .astype(str)
                .to_numpy()
                .ravel()
            ).lower()
            pitcher_change_action = (
                "pitching_substitution" in substitution_text
                or "pitching change" in substitution_text
            )
            batter_change_action = bool(
                (
                    nonpitch["event_type"].eq("offensive_substitution")
                    & nonpitch["action_position_code"].eq("11")
                ).any()
            )
            interval_seconds = (following["start_time"] - preceding["start_time"]).total_seconds()
            rows.append(
                {
                    "period": preceding["period"],
                    "game_pk": preceding["game_pk"],
                    "official_date": preceding["official_date"],
                    "at_bat_index": preceding["at_bat_index"],
                    "inning": preceding["inning"],
                    "half_inning": preceding["half_inning"],
                    "pitcher_id": preceding["pitcher_id"],
                    "pitcher_name": preceding["pitcher_name"],
                    "batter_id": preceding["batter_id"],
                    "batter_name": preceding["batter_name"],
                    "preceding_event_index": preceding["event_index"],
                    "following_event_index": following["event_index"],
                    "preceding_play_id": preceding["play_id"],
                    "following_play_id": following["play_id"],
                    "preceding_start_time": preceding["start_time"],
                    "following_start_time": following["start_time"],
                    "event_start_interval_seconds": interval_seconds,
                    "bases_after_preceding_event": preceding["bases_after"],
                    "preceding_call": preceding["call_description"] or preceding["description"],
                    "following_call": following["call_description"] or following["description"],
                    "intervening_action_count": len(nonpitch),
                    "intervening_actions": _joined(
                        f"{row.event_index}:{row.event_type or row.event_name or row.event_record_type}"
                        f" ({row.description or ''})"
                        for row in nonpitch.itertuples()
                    ),
                    "pickoff_flag": "pickoff" in categories,
                    "step_off_flag": "step_off" in categories,
                    "timeout_flag": "timeout" in categories,
                    "mound_visit_flag": "mound_visit" in categories,
                    "substitution_flag": "substitution" in categories,
                    "other_nonpitch_flag": "other_nonpitch" in categories,
                    "pitcher_changed_flag": bool(
                        preceding["pitcher_id"] != following["pitcher_id"]
                        or pitcher_change_action
                    ),
                    "batter_changed_flag": bool(
                        preceding["batter_id"] != following["batter_id"]
                        or batter_change_action
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_opportunities(events: pd.DataFrame) -> pd.DataFrame:
    """Audit response opportunities after pitches that leave first base only.

    A pitch is included if another pitch follows in the same plate appearance, or
    if at least one later nonpitch action exists.  The latter preserves candidate
    opportunities that terminate without another pitch while avoiding terminal
    balls in play that end a plate appearance at the pitch itself.
    """
    rows: list[dict[str, Any]] = []
    for (_game_pk, _at_bat_index), group in events.groupby(
        ["game_pk", "at_bat_index"], sort=False
    ):
        ordered = group.sort_values("event_order")
        for position, (_index, event) in enumerate(ordered.iterrows()):
            if not event["is_pitch"] or event["bases_after"] != "1B":
                continue
            later = ordered.iloc[position + 1 :]
            later_pitches = later.loc[later["is_pitch"]]
            next_pitch = later_pitches.iloc[0] if not later_pitches.empty else None
            if next_pitch is not None:
                next_position = int(np.flatnonzero(later.index == next_pitch.name)[0])
                intervening = later.iloc[:next_position]
                status = "next_pitch"
            else:
                intervening = later.loc[~later["is_pitch"]]
                if intervening.empty:
                    continue
                status = "no_next_pitch_after_later_action"

            action_columns = [
                "event_type",
                "event_name",
                "description",
                "movement_event_types",
            ]
            action_text = " ".join(
                intervening[action_columns]
                .fillna("")
                .astype(str)
                .to_numpy()
                .ravel()
            ).lower()
            next_movement = "" if next_pitch is None else str(next_pitch["movement_event_types"] or "")
            outcome_text = f"{action_text} {next_movement.lower()}"
            categories = set(intervening["action_category"])
            if "caught_stealing" in outcome_text or "caught stealing" in outcome_text:
                opportunity_class = "caught_stealing"
            elif "stolen_base" in outcome_text or "stolen base" in outcome_text:
                opportunity_class = "stolen_base"
            elif "pickoff" in outcome_text or "pickoff" in categories:
                opportunity_class = "pickoff"
            elif status.startswith("no_next_pitch"):
                opportunity_class = "other_no_next_pitch"
            else:
                opportunity_class = "ordinary_nonattempt"

            rows.append(
                {
                    "period": event["period"],
                    "game_pk": event["game_pk"],
                    "official_date": event["official_date"],
                    "at_bat_index": event["at_bat_index"],
                    "inning": event["inning"],
                    "half_inning": event["half_inning"],
                    "pitcher_id": event["pitcher_id"],
                    "pitcher_name": event["pitcher_name"],
                    "batter_id": event["batter_id"],
                    "batter_name": event["batter_name"],
                    "opportunity_event_index": event["event_index"],
                    "opportunity_play_id": event["play_id"],
                    "opportunity_start_time": event["start_time"],
                    "derived_pre_count": (
                        f"{event['derived_pre_balls']}-{event['derived_pre_strikes']}"
                    ),
                    "feed_event_count": (
                        f"{event['feed_count_balls']}-{event['feed_count_strikes']}"
                    ),
                    "feed_event_outs": event["feed_count_outs"],
                    "carried_score_after_event": (
                        f"{event['post_away_score']}-{event['post_home_score']}"
                    ),
                    "status": status,
                    "opportunity_class": opportunity_class,
                    "next_pitch_event_index": None if next_pitch is None else next_pitch["event_index"],
                    "next_pitch_play_id": None if next_pitch is None else next_pitch["play_id"],
                    "next_pitch_movement": "" if next_pitch is None else next_pitch["movement_summary"],
                    "intervening_actions": _joined(
                        f"{row.event_index}:{row.event_type or row.event_name or row.event_record_type}"
                        f" ({row.description or ''})"
                        for row in intervening.itertuples()
                    ),
                    "play_result": event["play_result_description"],
                    "called_ball_or_strike": event["call_code"] in {"B", "C"},
                }
            )
    return pd.DataFrame(rows)


def build_game_quality(
    events: pd.DataFrame,
    intervals: pd.DataFrame,
    state_audit: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    duplicate_mask = events.duplicated(
        ["game_pk", "at_bat_index", "event_index"], keep="first"
    )
    for game_pk, group in events.groupby("game_pk", sort=False):
        ordered = group.sort_values("game_sequence")
        event_index_diffs = group.sort_values(["play_order", "event_order"]).groupby(
            "at_bat_index"
        )["event_index"].diff()
        within_pa_start_diffs = group.sort_values(["play_order", "event_order"]).groupby(
            "at_bat_index"
        )["start_time"].diff().dt.total_seconds()
        global_start_diffs = ordered["start_time"].diff().dt.total_seconds()
        game_intervals = intervals.loc[intervals["game_pk"].eq(game_pk)]
        game_states = state_audit.loc[state_audit["game_pk"].eq(game_pk)]
        first = ordered.iloc[0]
        rows.append(
            {
                "game_pk": game_pk,
                "official_date": first["official_date"],
                "period": first["period"],
                "away_team": first["away_team"],
                "home_team": first["home_team"],
                "venue": first["venue"],
                "plate_appearances": group["at_bat_index"].nunique(),
                "events": len(group),
                "pitches": int(group["is_pitch"].sum()),
                "nonpitch_events": int((~group["is_pitch"]).sum()),
                "missing_start_time": int(group["start_time_raw"].isna().sum()),
                "invalid_start_time": int(
                    (group["start_time_raw"].notna() & group["start_time"].isna()).sum()
                ),
                "missing_end_time": int(group["end_time_raw"].isna().sum()),
                "invalid_end_time": int(
                    (group["end_time_raw"].notna() & group["end_time"].isna()).sum()
                ),
                "duplicate_event_keys": int(duplicate_mask.loc[group.index].sum()),
                "nonincreasing_event_indexes": int(event_index_diffs.le(0).sum()),
                "within_pa_negative_start_deltas": int(within_pa_start_diffs.lt(0).sum()),
                "within_pa_nonpositive_start_deltas": int(within_pa_start_diffs.le(0).sum()),
                "global_negative_start_deltas": int(global_start_diffs.lt(0).sum()),
                "end_before_start": int((group["end_time"] < group["start_time"]).sum()),
                "event_start_intervals": len(game_intervals),
                "nonpositive_event_start_intervals": int(
                    game_intervals["event_start_interval_seconds"].le(0).sum()
                ),
                "missing_event_start_intervals": int(
                    game_intervals["event_start_interval_seconds"].isna().sum()
                ),
                "unresolved_runner_movements": int(
                    game_states["unresolved_movement_count"].sum()
                ),
                "runner_movement_anomalies": int(
                    game_states["movement_anomaly_count"].sum()
                ),
                "missing_first_pitch_state": int(
                    game_states["reconstructed_before_first_pitch"].isna().sum()
                ),
                "matchup_end_state_mismatches": int(
                    (
                        game_states["reconstructed_end_bucket"].notna()
                        & ~game_states["matchup_matches_end"]
                    ).sum()
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(["official_date", "game_pk"]).reset_index(drop=True)


def action_label_inventory(events: pd.DataFrame) -> pd.DataFrame:
    actions = events.loc[~events["is_pitch"]].copy()
    actions["event_type_display"] = actions["event_type"].fillna("(missing)")
    actions["event_name_display"] = actions["event_name"].fillna("(missing)")
    return (
        actions.groupby(
            ["action_category", "event_record_type", "event_type_display", "event_name_display"],
            dropna=False,
        )
        .size()
        .rename("events")
        .reset_index()
        .sort_values(["action_category", "events"], ascending=[True, False])
        .reset_index(drop=True)
    )


def timestamp_format_inventory(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, raw_column, digits_column in (
        ("startTime", "start_time_raw", "start_fractional_digits"),
        ("endTime", "end_time_raw", "end_fractional_digits"),
    ):
        counts = events[digits_column].value_counts(dropna=False).sort_index()
        for digits, count in counts.items():
            rows.append(
                {
                    "field": label,
                    "fractional_second_digits": "missing" if pd.isna(digits) else int(digits),
                    "events": int(count),
                    "example": events.loc[events[digits_column].eq(digits), raw_column].iloc[0]
                    if not pd.isna(digits)
                    else "",
                }
            )
    return pd.DataFrame(rows)


def representative_trace_candidates(opportunities: pd.DataFrame) -> pd.DataFrame:
    desired = [
        ("ordinary_nonattempt", "next_pitch", "ordinary nonattempt"),
        ("pickoff", "next_pitch", "pickoff with later pitch"),
        ("stolen_base", "next_pitch", "recorded stolen base"),
        ("caught_stealing", "next_pitch", "recorded caught stealing"),
        (None, "no_next_pitch_after_later_action", "opportunity ending without another pitch"),
    ]
    selected = []
    for label, status, trace_case in desired:
        mask = opportunities["status"].eq(status)
        if label is not None:
            mask &= opportunities["opportunity_class"].eq(label)
        candidates = opportunities.loc[mask]
        if candidates.empty:
            continue
        candidate = candidates.sort_values(
            ["official_date", "game_pk", "at_bat_index"]
        ).iloc[0].copy()
        candidate["trace_case"] = trace_case
        selected.append(candidate)
    if not selected:
        return opportunities.head(0).copy()
    return pd.DataFrame(selected).reset_index(drop=True)
