"""Incrementally process historical feeds into leakage-safe opportunity tables.

The module reuses the frozen runner-control parser and window builder.  Raw
feeds and large derived tables remain below ignored data directories; compact
quality summaries are written to results/.
"""

from __future__ import annotations

import argparse
import gzip
import heapq
import json
import os
import platform
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from scripts.audit_feeds import extract_events
from scripts.historical_collection import (
    BOUNDS,
    DATA,
    DEFAULT_DEVELOPMENT_SEASONS,
    PROCESSED,
    ROOT,
    TEST_SEASON,
    atomic_write_frame,
    atomic_write_json,
    feed_manifest_path,
    sha256_bytes,
    validate_final_feed,
)
from scripts.prepare_opportunity_dataset import build_disengagement_history
from scripts.runner_control_audit import build_action_audit, build_opportunity_windows


PARSER_VERSION = "historical_processing_v1.1"
GOOD_FEED_STATUSES = {
    "reused_verified_cache",
    "downloaded",
    "refreshed_changed",
    "refreshed_unchanged",
}
SUCCESS_OUTCOMES = {"advance", "error_advance", "advance_then_out"}
UNSUCCESSFUL_OUTCOMES = {"caught_stealing", "picked_off"}


def _value(mapping: dict[str, Any] | None, *keys: str) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _ids(value: Any) -> list[str]:
    if value is None or pd.isna(value) or str(value) == "":
        return []
    return [item for item in str(value).split("|") if item]


def parse_utc_mixed(values: pd.Series) -> pd.Series:
    """Parse mixed fractional/nonfractional ISO timestamps element by element."""
    return values.map(lambda value: pd.to_datetime(value, utc=True, errors="coerce"))


def rule_regime(season: int) -> str:
    return (
        "pre_2023_no_disengagement_limit"
        if int(season) < 2023
        else "post_2023_two_disengagement_limit_with_advance_reset"
    )


def validate_requested_seasons(
    seasons: Iterable[int], *, allow_test_data: bool = False
) -> tuple[int, ...]:
    result = tuple(sorted(set(int(value) for value in seasons)))
    if TEST_SEASON in result and not allow_test_data:
        raise ValueError(
            "2025 outcomes are locked. Use --allow-test-data only after the final-test opening decision."
        )
    if any(season not in BOUNDS for season in result):
        raise ValueError(f"Unsupported seasons: {result}")
    return result


def _starter_batting_order(value: Any) -> bool:
    try:
        return int(value) % 100 == 0
    except (TypeError, ValueError):
        return False


def _player_name_lookup(feed: dict[str, Any]) -> dict[int, str]:
    result: dict[int, str] = {}
    for person in (_value(feed, "gameData", "players") or {}).values():
        if person.get("id") is not None:
            result[int(person["id"])] = person.get("fullName") or str(person["id"])
    for side in ("away", "home"):
        for player in (
            _value(feed, "liveData", "boxscore", "teams", side, "players") or {}
        ).values():
            person = player.get("person") or {}
            if person.get("id") is not None:
                result[int(person["id"])] = person.get("fullName") or str(person["id"])
    return result


def starting_catcher(
    feed: dict[str, Any], side: str, events: pd.DataFrame
) -> tuple[int | None, str | None, str, str]:
    """Return the starting catcher without treating final position as initial."""
    players = (
        _value(feed, "liveData", "boxscore", "teams", side, "players") or {}
    )
    names = _player_name_lookup(feed)
    starters: list[dict[str, Any]] = [
        player
        for player in players.values()
        if _starter_batting_order(player.get("battingOrder"))
    ]
    candidates = [
        player
        for player in starters
        if any(
            str(position.get("code") or "") == "2"
            for position in player.get("allPositions", [])
        )
    ]
    method = "unique_starting_batting_order_catcher_position_history"
    confidence = "high"
    if len(candidates) > 1:
        fielding_half = "top" if side == "home" else "bottom"
        later_entries = set(
            pd.to_numeric(
                events.loc[
                    events["half_inning"].astype(str).str.lower().eq(fielding_half)
                    & events["action_position_code"].astype(str).eq("2")
                    & (
                        events["is_substitution"].fillna(False)
                        | events["event_type"].isin(
                            ["defensive_substitution", "defensive_switch"]
                        )
                    ),
                    "action_player_id",
                ],
                errors="coerce",
            ).dropna().astype(int)
        )
        remaining = [
            player
            for player in candidates
            if int(_value(player, "person", "id") or -1) not in later_entries
        ]
        if len(remaining) == 1:
            candidates = remaining
            method = "starting_catcher_excluding_ordered_later_entries"
            confidence = "medium"
    if len(candidates) != 1:
        return None, None, "unresolved_starting_catcher", "unknown"
    person_id = _value(candidates[0], "person", "id")
    if person_id is None:
        return None, None, "unresolved_starting_catcher", "unknown"
    person_id = int(person_id)
    return person_id, names.get(person_id), method, confidence


def build_catcher_timeline(
    feed: dict[str, Any], events: pd.DataFrame
) -> pd.DataFrame:
    names = _player_name_lookup(feed)
    rows: list[dict[str, Any]] = []
    for side in ("away", "home"):
        catcher_id, catcher_name, method, confidence = starting_catcher(
            feed, side, events
        )
        rows.append(
            {
                "fielding_side": side,
                "effective_game_sequence": 0,
                "catcher_id": catcher_id,
                "catcher_name": catcher_name,
                "assignment_method": method,
                "assignment_confidence": confidence,
                "source_event_key": pd.NA,
            }
        )
    substitutions = events.loc[
        events["action_position_code"].astype(str).eq("2")
        & (
            events["is_substitution"].fillna(False)
            | events["event_type"].isin(
                ["defensive_substitution", "defensive_switch"]
            )
        )
    ].sort_values("game_sequence")
    for event in substitutions.itertuples(index=False):
        incoming = event.action_player_id
        side = "home" if str(event.half_inning).lower() == "top" else "away"
        rows.append(
            {
                "fielding_side": side,
                "effective_game_sequence": int(event.game_sequence),
                "catcher_id": int(incoming) if pd.notna(incoming) else None,
                "catcher_name": names.get(int(incoming)) if pd.notna(incoming) else None,
                "assignment_method": "ordered_defensive_substitution_or_switch",
                "assignment_confidence": "high" if pd.notna(incoming) else "unknown",
                "source_event_key": event.event_key,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["fielding_side", "effective_game_sequence"]
    ).reset_index(drop=True)


def catcher_at_open(
    timeline: pd.DataFrame, half_inning: str, cutoff_sequence: int
) -> dict[str, Any]:
    side = "home" if str(half_inning).lower() == "top" else "away"
    candidates = timeline.loc[
        timeline["fielding_side"].eq(side)
        & timeline["effective_game_sequence"].le(int(cutoff_sequence))
    ].sort_values("effective_game_sequence")
    if candidates.empty:
        return {
            "opening_catcher_id": pd.NA,
            "opening_catcher_name": pd.NA,
            "opening_catcher_assignment_method": "no_assignment_before_cutoff",
            "opening_catcher_assignment_confidence": "unknown",
            "opening_catcher_source_event_key": pd.NA,
        }
    row = candidates.iloc[-1]
    return {
        "opening_catcher_id": row["catcher_id"],
        "opening_catcher_name": row["catcher_name"],
        "opening_catcher_assignment_method": row["assignment_method"],
        "opening_catcher_assignment_confidence": row["assignment_confidence"],
        "opening_catcher_source_event_key": row["source_event_key"],
    }


def source_frame(manifest_row: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_pk": int(manifest_row["game_pk"]),
                "selected_for_parse": True,
                "source_population": f"historical_{int(manifest_row['season'])}",
                "cache_path": manifest_row["cache_path"],
                "feed_url": manifest_row["source_url"],
                "retrieved_utc": manifest_row["retrieved_utc"],
                "sha256": manifest_row["sha256"],
            }
        ]
    )


def parser_manifest_row(manifest_row: pd.Series) -> pd.Series:
    return pd.Series(
        {
            "selection_order": int(manifest_row.get("selection_order", 1)),
            "period": f"historical_{int(manifest_row['season'])}",
            "game_pk": int(manifest_row["game_pk"]),
            "official_date": manifest_row["official_date"],
            "away_team": manifest_row["away_team"],
            "home_team": manifest_row["home_team"],
            "venue": manifest_row["venue"],
        }
    )


def opportunity_file(season: int, game_pk: int) -> Path:
    return PROCESSED / "games" / str(season) / f"game_{game_pk}_opportunities.csv.gz"


def metadata_file(season: int, game_pk: int) -> Path:
    return PROCESSED / "games" / str(season) / f"game_{game_pk}_metadata.json"


def atomic_write_gzip_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    frame.to_csv(temporary, index=False, compression="gzip")
    os.replace(temporary, path)


def checkpoint_valid(
    season: int, game_pk: int, feed_sha256: str
) -> bool:
    data_path = opportunity_file(season, game_pk)
    meta_path = metadata_file(season, game_pk)
    if not data_path.exists() or not meta_path.exists():
        return False
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return (
        metadata.get("parser_version") == PARSER_VERSION
        and str(metadata.get("feed_sha256")) == str(feed_sha256)
        and int(metadata.get("game_pk", -1)) == int(game_pk)
    )


def _response_identity_changes(
    group: pd.DataFrame,
    open_order: int,
    close_order: int,
    opening_runner: Any,
    opening_pitcher: Any,
    opening_batter: Any,
) -> tuple[bool, bool, bool]:
    response = group.loc[
        group["event_order"].gt(open_order)
        & group["event_order"].le(close_order)
    ]
    runner_change = False
    if pd.notna(opening_runner):
        observed = response.loc[
            response["bases_after"].eq("1B")
            & response["runner_1b_after"].notna(),
            "runner_1b_after",
        ]
        runner_change = bool(
            observed.map(lambda value: int(value) != int(opening_runner)).any()
        )
    pitcher_change = bool(
        response["pitcher_id"].dropna().map(
            lambda value: int(value) != int(opening_pitcher)
            if pd.notna(opening_pitcher)
            else False
        ).any()
    )
    batter_change = bool(
        response["batter_id"].dropna().map(
            lambda value: int(value) != int(opening_batter)
            if pd.notna(opening_batter)
            else False
        ).any()
    )
    return runner_change, pitcher_change, batter_change


def _steal_outcome(detail: pd.DataFrame) -> tuple[str, int, int, int, int]:
    steals = detail.loc[detail["action_type"].eq("steal_attempt")]
    attempts = len(steals)
    successes = int(steals["outcome_type"].isin(SUCCESS_OUTCOMES).sum())
    unsuccessful = int(steals["outcome_type"].isin(UNSUCCESSFUL_OUTCOMES).sum())
    ambiguous = attempts - successes - unsuccessful
    if attempts == 0:
        classification = "none"
    elif attempts == 1 and successes == 1:
        classification = "recorded_success"
    elif attempts == 1 and unsuccessful == 1:
        classification = "recorded_unsuccessful"
    else:
        classification = "ambiguous_or_multiple"
    return classification, attempts, successes, unsuccessful, ambiguous


def _pre2023_disengagement_count(
    actions: pd.DataFrame, game_pk: int, pa: int, open_order: int
) -> int:
    prior = actions.loc[
        actions["game_pk"].eq(game_pk)
        & actions["at_bat_index"].eq(pa)
        & actions["event_order"].le(open_order)
        & (
            (
                actions["action_type"].eq("pickoff_throw")
                & actions["initiator_role"].eq("pitcher")
            )
            | actions["action_type"].isin(["step_off", "disengagement_violation"])
        )
    ]
    return len(prior)


def build_game_opportunities(
    manifest_row: pd.Series, feed: dict[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    game_pk = int(manifest_row["game_pk"])
    season = int(manifest_row["season"])
    loaded = [(parser_manifest_row(manifest_row), feed)]
    events, states = extract_events(loaded)
    sources = source_frame(manifest_row)
    actions, _vocabulary, _inventory = build_action_audit(loaded, events, sources)
    windows = build_opportunity_windows(events, actions, states)
    catcher_timeline = build_catcher_timeline(feed, events)
    event_groups = {
        key: frame.sort_values("event_order").reset_index(drop=True)
        for key, frame in events.groupby(["game_pk", "at_bat_index"], sort=False)
    }
    action_by_id = actions.set_index("action_id", drop=False)
    post_history = None
    disengagement_checks = pd.DataFrame()
    if season >= 2023:
        post_history, disengagement_checks = build_disengagement_history(
            events, actions, loaded
        )
        post_history = post_history.set_index("event_key")

    rows: list[dict[str, Any]] = []
    for window in windows.itertuples(index=False):
        pa = int(window.at_bat_index)
        group = event_groups[(game_pk, pa)]
        open_order = int(window.open_event_order)
        close_order = int(window.close_event_order)
        pre_first = open_order == -1
        if pre_first:
            anchor = None
            cutoff_sequence = int(group.iloc[0]["game_sequence"]) - 1
            recorded_prior = 0
            resets_prior: Any = 0 if season >= 2023 else pd.NA
        else:
            anchor = group.loc[group["event_order"].eq(open_order)].iloc[0]
            cutoff_sequence = int(anchor["game_sequence"])
            if season >= 2023:
                history = post_history.loc[anchor["event_key"]]
                recorded_prior = int(
                    history["recorded_disengagements_since_reset_after_event"]
                )
                resets_prior = int(
                    history["recorded_disengagement_reset_count_after_event"]
                )
            else:
                recorded_prior = _pre2023_disengagement_count(
                    actions, game_pk, pa, open_order
                )
                resets_prior = pd.NA

        assigned_ids = _ids(window.action_ids)
        detail = (
            action_by_id.loc[assigned_ids].copy()
            if assigned_ids
            else pd.DataFrame(columns=actions.columns)
        )
        if isinstance(detail, pd.Series):
            detail = detail.to_frame().T
        outcome_class, attempt_records, successes, unsuccessful, ambiguous = _steal_outcome(detail)
        runner_change, pitcher_change, batter_change = _response_identity_changes(
            group,
            open_order,
            close_order,
            window.runner_id,
            window.pitcher_id,
            window.batter_id,
        )
        catcher = catcher_at_open(
            catcher_timeline, window.half_inning, cutoff_sequence
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
        unknown_actions = int(detail["action_type"].eq("unknown_candidate").sum())
        attempt_history_eligible = bool(
            pd.notna(window.runner_id)
            and not runner_change
            and not pitcher_change
            and not batter_change
            and unknown_actions == 0
        )
        success_history_eligible = bool(
            attempt_history_eligible
            and attempt_records == 1
            and outcome_class in {"recorded_success", "recorded_unsuccessful"}
        )
        row = {
            "opportunity_id": window.opportunity_id,
            "season": season,
            "split_role": manifest_row["split_role"],
            "game_pk": game_pk,
            "official_date": manifest_row["official_date"],
            "scheduled_start_utc": manifest_row["scheduled_start_utc"],
            "feed_game_start_utc": manifest_row.get("feed_game_start_utc"),
            "feed_completion_time_utc": manifest_row.get("feed_completion_time_utc"),
            "game_chronology_available": bool(
                pd.notna(manifest_row.get("feed_game_start_utc"))
                and str(manifest_row.get("feed_game_start_utc")) != ""
                and pd.notna(manifest_row.get("feed_completion_time_utc"))
                and str(manifest_row.get("feed_completion_time_utc")) != ""
            ),
            "away_team_id": manifest_row["away_team_id"],
            "away_team": manifest_row["away_team"],
            "home_team_id": manifest_row["home_team_id"],
            "home_team": manifest_row["home_team"],
            "venue_id": manifest_row["venue_id"],
            "venue": manifest_row["venue"],
            "at_bat_index": pa,
            "inning": window.inning,
            "half_inning": window.half_inning,
            "pitcher_id": window.pitcher_id,
            "pitcher_name": window.pitcher_name,
            "batter_id": window.batter_id,
            "batter_name": window.batter_name,
            "runner_id": window.runner_id,
            "open_timing": window.open_timing,
            "open_anchor": window.open_anchor,
            "feature_cutoff_game_sequence": cutoff_sequence,
            "feature_cutoff_event_order": open_order,
            "open_balls": window.open_balls,
            "open_strikes": window.open_strikes,
            "open_outs": window.open_outs,
            **catcher,
            "disengagement_rule_regime": rule_regime(season),
            "recorded_disengagements_at_open": recorded_prior,
            "recorded_disengagement_resets_at_open": resets_prior,
            "disengagement_limit_without_penalty": 2 if season >= 2023 else pd.NA,
            "disengagements_remaining_without_penalty": max(0, 2 - recorded_prior)
            if season >= 2023
            else pd.NA,
            "disengagement_limit_reached_at_open": recorded_prior >= 2
            if season >= 2023
            else pd.NA,
            "response_action_ids": "|".join(assigned_ids),
            "recorded_action_record_count": len(detail),
            "recorded_pitcher_pickoff_count": len(pitcher_pickoffs),
            "recorded_pitcher_pickoff_indicator": len(pitcher_pickoffs) > 0,
            "recorded_catcher_pickoff_count": len(catcher_pickoffs),
            "recorded_catcher_pickoff_indicator": len(catcher_pickoffs) > 0,
            "recorded_unknown_pickoff_count": len(unknown_pickoffs),
            "recorded_unknown_pickoff_indicator": len(unknown_pickoffs) > 0,
            "recorded_steal_attempt_record_count": attempt_records,
            "recorded_steal_attempt_indicator": attempt_records > 0,
            "recorded_steal_success_count": successes,
            "recorded_steal_unsuccessful_count": unsuccessful,
            "recorded_steal_ambiguous_count": ambiguous,
            "recorded_steal_outcome_class": outcome_class,
            "recorded_stepoff_count": int(detail["action_type"].eq("step_off").sum()),
            "unknown_action_classification_count": unknown_actions,
            "close_event_index": window.close_event_index,
            "close_event_order": close_order,
            "close_reason": window.close_reason,
            "following_pitch_exists": bool(window.following_pitch_exists),
            "terminal_window": bool(window.terminal_without_pitch),
            "runner_identity_changed_within_window": runner_change,
            "pitcher_identity_changed_within_window": pitcher_change,
            "batter_identity_changed_within_window": batter_change,
            "attempt_history_eligible": attempt_history_eligible,
            "conditional_success_history_eligible": success_history_eligible,
            "history_count_exclusion_reason": "|".join(
                reason
                for condition, reason in [
                    (pd.isna(window.runner_id), "missing_opening_runner"),
                    (runner_change, "runner_changed"),
                    (pitcher_change, "pitcher_changed"),
                    (batter_change, "batter_changed"),
                    (unknown_actions > 0, "unknown_action_classification"),
                ]
                if condition
            ),
            "known_state_conflict": bool(window.known_state_conflict),
            "source_cache_path": manifest_row["cache_path"],
            "source_url": manifest_row["source_url"],
            "source_retrieved_utc": manifest_row["retrieved_utc"],
            "source_sha256": manifest_row["sha256"],
            "parser_version": PARSER_VERSION,
        }
        rows.append(row)
    table = pd.DataFrame(rows)
    metadata = {
        "parser_version": PARSER_VERSION,
        "game_pk": game_pk,
        "season": season,
        "feed_sha256": str(manifest_row["sha256"]),
        "feed_cache_path": str(manifest_row["cache_path"]),
        "feed_game_start_utc": manifest_row.get("feed_game_start_utc"),
        "feed_completion_time_utc": manifest_row.get("feed_completion_time_utc"),
        "events": len(events),
        "pitches": int(events["is_pitch"].sum()),
        "actions": len(actions),
        "opportunities": len(table),
        "terminal_windows": int(table["terminal_window"].sum()) if len(table) else 0,
        "catcher_assigned_windows": int(table["opening_catcher_id"].notna().sum()) if len(table) else 0,
        "unknown_action_windows": int(table["unknown_action_classification_count"].gt(0).sum()) if len(table) else 0,
        "known_state_conflict_windows": int(table["known_state_conflict"].sum()) if len(table) else 0,
        "raw_disengagement_checks": len(disengagement_checks),
        "raw_disengagement_comparable": int(disengagement_checks["raw_number_available"].sum())
        if len(disengagement_checks)
        else 0,
        "raw_disengagement_mismatches": int(
            disengagement_checks.loc[
                disengagement_checks["raw_number_available"], "raw_number_matches"
            ].eq(False).sum()
        )
        if len(disengagement_checks)
        else 0,
    }
    return table, metadata


def process_one_game(manifest_row: pd.Series) -> tuple[str, dict[str, Any]]:
    season = int(manifest_row["season"])
    game_pk = int(manifest_row["game_pk"])
    feed_path = ROOT / str(manifest_row["cache_path"])
    if not feed_path.exists():
        raise FileNotFoundError(feed_path)
    content = feed_path.read_bytes()
    digest = sha256_bytes(content)
    if str(manifest_row["sha256"]) and digest != str(manifest_row["sha256"]):
        raise ValueError("feed checksum does not match manifest")
    valid, reason, observed = validate_final_feed(content, game_pk)
    if not valid:
        raise ValueError(f"feed validation failed: {reason}")
    for key, value in observed.items():
        if pd.isna(manifest_row.get(key)) or str(manifest_row.get(key)) == "":
            manifest_row[key] = value
    feed = json.loads(content)
    table, metadata = build_game_opportunities(manifest_row, feed)
    atomic_write_gzip_frame(opportunity_file(season, game_pk), table)
    atomic_write_json(metadata_file(season, game_pk), metadata)
    return "processed", metadata


def process_games(
    seasons: Iterable[int],
    *,
    pilot: bool = False,
    allow_test_data: bool = False,
    checkpoint_every: int = 50,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    seasons = validate_requested_seasons(seasons, allow_test_data=allow_test_data)
    pilot_games: set[int] | None = None
    if pilot:
        pilot_games = set(
            pd.read_csv(DATA / "historical_pilot_manifest.csv")["game_pk"].astype(int)
        )
    metadata_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    suffix = "pilot" if pilot else "development"
    for season in seasons:
        feeds = pd.read_csv(feed_manifest_path(season), low_memory=False)
        feeds = feeds.loc[
            feeds["feed_eligible"].astype(bool)
            & feeds["retrieval_status"].isin(GOOD_FEED_STATUSES)
        ].copy()
        if pilot_games is not None:
            feeds = feeds.loc[feeds["game_pk"].astype(int).isin(pilot_games)]
        feeds = feeds.sort_values(["official_date", "scheduled_start_utc", "game_pk"])
        print(f"{season}: processing {len(feeds)} {'pilot ' if pilot else ''}games", flush=True)
        for position, row in enumerate(feeds.itertuples(index=False), start=1):
            series = pd.Series(row._asdict())
            game_pk = int(row.game_pk)
            try:
                if checkpoint_valid(season, game_pk, str(row.sha256)):
                    status = "checkpoint_hit"
                    metadata = json.loads(
                        metadata_file(season, game_pk).read_text(encoding="utf-8")
                    )
                else:
                    status, metadata = process_one_game(series)
                metadata_rows.append({**metadata, "processing_status": status})
            except Exception as exc:  # preserve failure and continue bulk processing
                failure_rows.append(
                    {
                        "season": season,
                        "game_pk": game_pk,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
            if position % checkpoint_every == 0 or position == len(feeds):
                print(
                    f"{season}: {position}/{len(feeds)}; failures={sum(row['season'] == season for row in failure_rows)}",
                    flush=True,
                )
        season_metadata = pd.DataFrame(
            [row for row in metadata_rows if int(row["season"]) == season]
        )
        season_failures = pd.DataFrame(
            [row for row in failure_rows if int(row["season"]) == season],
            columns=["season", "game_pk", "error_type", "error"],
        )
        atomic_write_frame(
            ROOT
            / "results"
            / f"historical_{suffix}_game_processing_{season}.csv",
            season_metadata,
        )
        atomic_write_frame(
            ROOT
            / "results"
            / f"historical_{suffix}_processing_failures_{season}.csv",
            season_failures,
        )
    metadata_frame = pd.DataFrame(metadata_rows)
    failures = pd.DataFrame(
        failure_rows, columns=["season", "game_pk", "error_type", "error"]
    )
    if len(seasons) > 1:
        atomic_write_frame(
            ROOT / "results" / f"historical_{suffix}_game_processing.csv",
            metadata_frame,
        )
        atomic_write_frame(
            ROOT / "results" / f"historical_{suffix}_processing_failures.csv",
            failures,
        )
    return metadata_frame, failures


def load_processing_metadata(
    seasons: Iterable[int], *, suffix: str
) -> pd.DataFrame:
    """Load season checkpoints, falling back to the legacy combined file."""
    seasons = list(seasons)
    paths = [
        ROOT
        / "results"
        / f"historical_{suffix}_game_processing_{season}.csv"
        for season in seasons
    ]
    if all(path.exists() for path in paths):
        frames = [pd.read_csv(path, low_memory=False) for path in paths]
        return pd.concat(frames, ignore_index=True, sort=False)
    combined = ROOT / "results" / f"historical_{suffix}_game_processing.csv"
    return pd.read_csv(combined, low_memory=False)


@dataclass
class RunnerCounts:
    opportunities: int = 0
    attempted_opportunities: int = 0
    attempt_records: int = 0
    successes: int = 0
    unsuccessful: int = 0
    ambiguous: int = 0

    def add(self, row: pd.Series) -> None:
        self.opportunities += 1
        if bool(row["recorded_steal_attempt_indicator"]):
            self.attempted_opportunities += 1
        self.attempt_records += int(row["recorded_steal_attempt_record_count"])
        self.successes += int(row["recorded_steal_success_count"])
        self.unsuccessful += int(row["recorded_steal_unsuccessful_count"])
        self.ambiguous += int(row["recorded_steal_ambiguous_count"])

    def as_dict(self, prefix: str) -> dict[str, int]:
        return {
            f"{prefix}_eligible_opportunities": self.opportunities,
            f"{prefix}_attempted_opportunities": self.attempted_opportunities,
            f"{prefix}_attempt_records": self.attempt_records,
            f"{prefix}_successes": self.successes,
            f"{prefix}_unsuccessful": self.unsuccessful,
            f"{prefix}_ambiguous_outcomes": self.ambiguous,
        }


@dataclass
class ForwardHistoryState:
    counts: dict[str, dict[int, RunnerCounts]] = field(
        default_factory=lambda: {
            "pre_2023": defaultdict(RunnerCounts),
            "post_2023": defaultdict(RunnerCounts),
        }
    )
    pending: list[tuple[pd.Timestamp, int, int, list[dict[str, Any]]]] = field(
        default_factory=list
    )
    sequence: int = 0

    def release_completed_before(self, game_start: pd.Timestamp) -> None:
        while self.pending and self.pending[0][0] < game_start:
            _completion, _sequence, season, records = heapq.heappop(self.pending)
            regime = "pre_2023" if season < 2023 else "post_2023"
            for record in records:
                runner_id = int(record["runner_id"])
                self.counts[regime][runner_id].add(pd.Series(record))

    def snapshot(self, runner_id: Any, *, coverage_complete: bool) -> dict[str, Any]:
        if pd.isna(runner_id):
            pre = RunnerCounts()
            post = RunnerCounts()
        else:
            runner_id = int(runner_id)
            pre = self.counts["pre_2023"][runner_id]
            post = self.counts["post_2023"][runner_id]
        total = RunnerCounts(
            opportunities=pre.opportunities + post.opportunities,
            attempted_opportunities=pre.attempted_opportunities
            + post.attempted_opportunities,
            attempt_records=pre.attempt_records + post.attempt_records,
            successes=pre.successes + post.successes,
            unsuccessful=pre.unsuccessful + post.unsuccessful,
            ambiguous=pre.ambiguous + post.ambiguous,
        )
        if not coverage_complete:
            status = "missing_or_incomplete_historical_coverage"
        elif total.opportunities == 0:
            status = "no_prior_eligible_exposure"
        elif total.attempted_opportunities == 0:
            status = "observed_zero_attempts_with_positive_exposure"
        else:
            status = "observed_prior_attempts"
        return {
            **total.as_dict("runner_prior_all_regimes"),
            **pre.as_dict("runner_prior_pre_2023"),
            **post.as_dict("runner_prior_post_2023"),
            "runner_history_status": status,
            "runner_history_coverage_complete_since_2022_start": coverage_complete,
            "runner_history_left_truncated_at_2022": True,
            "runner_history_coverage_start": BOUNDS[2022][0],
        }

    def queue_game(
        self,
        *,
        season: int,
        completion_time: pd.Timestamp,
        frame: pd.DataFrame,
    ) -> None:
        eligible = frame.loc[
            frame["attempt_history_eligible"].fillna(False)
            & frame["runner_id"].notna()
        ]
        records = eligible[
            [
                "runner_id",
                "recorded_steal_attempt_indicator",
                "recorded_steal_attempt_record_count",
                "recorded_steal_success_count",
                "recorded_steal_unsuccessful_count",
                "recorded_steal_ambiguous_count",
            ]
        ].to_dict("records")
        self.sequence += 1
        heapq.heappush(
            self.pending,
            (completion_time, self.sequence, int(season), records),
        )


def _coverage_complete_for_start(
    start: pd.Timestamp,
    missing_starts: list[pd.Timestamp],
    chronology_issue_starts: list[pd.Timestamp],
    *,
    pilot: bool,
) -> tuple[bool, str]:
    if pilot:
        return False, "pilot_subset_not_complete"
    if any(value < start for value in missing_starts):
        return False, "prior_completed_feed_missing_or_quarantined"
    if any(value < start for value in chronology_issue_starts):
        return False, "prior_game_chronology_unresolved"
    return True, "complete_collected_window_since_2022_start"


def write_historical_feature_dictionary(columns: Iterable[str]) -> pd.DataFrame:
    """Write a compact leakage-oriented dictionary for the historical table."""
    exact_definitions = {
        "feed_game_start_utc": "Public-feed game start used to order games chronologically.",
        "feed_completion_time_utc": "Latest public-feed play/event end time; history is released only after this time.",
        "game_chronology_available": "Whether both game-start and completion timestamps are available.",
        "opening_catcher_id": "Catcher assigned at the opportunity cutoff from the starting defense plus ordered substitutions.",
        "opening_catcher_assignment_method": "Chronological source used for the catcher assignment.",
        "disengagement_rule_regime": "Season-specific pre-2023 or post-2023 disengagement rule label.",
        "attempt_history_eligible": "Window eligible to increment the runner opportunity/attempt history after game completion.",
        "conditional_success_history_eligible": "Recorded-attempt window eligible for later conditional-success history use.",
        "runner_history_status": "Distinguishes incomplete history, no prior exposure, observed zero attempts, and observed prior attempts.",
        "runner_history_coverage_complete_since_2022_start": "Whether every earlier eligible game in the collected window was processed with resolved chronology.",
        "runner_history_left_truncated_at_2022": "True because public history begins at the 2022 regular-season boundary.",
        "runner_history_coverage_reason": "Reason the pre-game history is complete or incomplete.",
        "history_frozen_before_game": "True when history was snapshotted before any current-game opportunity was added.",
    }
    rows: list[dict[str, str]] = []
    for field_name in columns:
        if field_name.startswith("runner_prior_"):
            group = "pre_game_runner_history"
            availability = "strictly_before_game_start"
            role = "candidate_predictor_or_history_depth"
            leakage = "Current game and games completing at/after this game start are excluded."
        elif field_name.startswith("opening_catcher"):
            group = "chronological_catcher_identity"
            availability = "at_opportunity_cutoff"
            role = "context_or_quality"
            leakage = "Never infer the opening catcher backward from the final defense."
        elif field_name in {
            "recorded_disengagements_at_open",
            "recorded_disengagement_resets_at_open",
            "disengagement_limit_without_penalty",
            "disengagements_remaining_without_penalty",
            "disengagement_limit_reached_at_open",
            "disengagement_rule_regime",
        }:
            group = "season_rule_and_opening_context"
            availability = "at_opportunity_cutoff"
            role = "candidate_context_predictor"
            leakage = "Contains only actions recorded before the opportunity cutoff and uses the season-appropriate rule."
        elif field_name.startswith("recorded_") or field_name in {
            "response_action_ids",
            "close_event_index",
            "close_event_order",
            "close_reason",
            "following_pitch_exists",
            "terminal_window",
        }:
            group = "response_or_outcome"
            availability = "during_or_after_response_window"
            role = "response_or_audit_only"
            leakage = "Prohibited as a predictor for the same opportunity."
        elif field_name.startswith("source_") or field_name in {
            "game_pk",
            "opportunity_id",
            "parser_version",
        }:
            group = "identifier_provenance"
            availability = "collection_time"
            role = "identifier_or_provenance"
            leakage = "Not a response predictor unless separately justified and frozen."
        elif field_name.startswith("runner_history") or field_name == "history_frozen_before_game":
            group = "history_quality"
            availability = "strictly_before_game_start"
            role = "quality_or_missingness_indicator"
            leakage = "Derived without current-game outcomes."
        else:
            group = "opening_context_or_quality"
            availability = "at_opportunity_cutoff"
            role = "context_quality_or_identifier"
            leakage = "Use as a predictor only if present by the frozen opportunity cutoff."
        rows.append(
            {
                "field": field_name,
                "group": group,
                "definition": exact_definitions.get(
                    field_name,
                    field_name.replace("_", " ") + ".",
                ),
                "availability_time": availability,
                "analysis_role": role,
                "leakage_rule": leakage,
            }
        )
    dictionary = pd.DataFrame(rows)
    atomic_write_frame(
        ROOT / "results" / "historical_feature_dictionary.csv", dictionary
    )
    return dictionary


def assemble_forward_histories(
    seasons: Iterable[int],
    *,
    pilot: bool = False,
    allow_test_data: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    seasons = validate_requested_seasons(seasons, allow_test_data=allow_test_data)
    suffix = "pilot" if pilot else "development"
    metadata = load_processing_metadata(seasons, suffix=suffix)
    if metadata.empty:
        raise ValueError("No processed games available for history assembly")
    feed_frames = [
        pd.read_csv(feed_manifest_path(season), low_memory=False)
        for season in seasons
    ]
    feeds = pd.concat(feed_frames, ignore_index=True, sort=False)
    if pilot:
        pilot_ids = set(
            pd.read_csv(DATA / "historical_pilot_manifest.csv")["game_pk"].astype(int)
        )
        feeds = feeds.loc[feeds["game_pk"].astype(int).isin(pilot_ids)]
    successful = set(metadata["game_pk"].astype(int))
    eligible = feeds.loc[feeds["feed_eligible"].astype(bool)].copy()
    eligible["start"] = parse_utc_mixed(
        eligible["feed_game_start_utc"].fillna(eligible["scheduled_start_utc"])
    )
    missing_starts = eligible.loc[
        ~eligible["game_pk"].astype(int).isin(successful), "start"
    ].dropna().tolist()
    meta = metadata.copy()
    meta["start"] = parse_utc_mixed(meta["feed_game_start_utc"])
    meta["completion"] = parse_utc_mixed(meta["feed_completion_time_utc"])
    chronology_issue_starts = meta.loc[
        meta["start"].isna() | meta["completion"].isna(), "start"
    ].dropna().tolist()
    ordered = meta.sort_values(["start", "game_pk"], na_position="last")
    state = ForwardHistoryState()
    output_dir = PROCESSED / suffix
    output_dir.mkdir(parents=True, exist_ok=True)
    handles: dict[int, Any] = {}
    temporary_paths: dict[int, Path] = {}
    headers_written: dict[int, bool] = defaultdict(bool)
    season_stats: dict[int, defaultdict[str, int]] = {
        season: defaultdict(int) for season in seasons
    }
    exclusion_counts: dict[int, defaultdict[str, int]] = {
        season: defaultdict(int) for season in seasons
    }
    try:
        for season in seasons:
            target = output_dir / f"opportunities_{season}.csv.gz"
            temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
            temporary_paths[season] = temporary
            handles[season] = gzip.open(temporary, "wt", encoding="utf-8", newline="")

        for game in ordered.itertuples(index=False):
            season = int(game.season)
            game_pk = int(game.game_pk)
            start = game.start
            completion = game.completion
            frame = pd.read_csv(
                opportunity_file(season, game_pk), low_memory=False
            )
            if pd.isna(start):
                coverage_complete = False
                coverage_reason = "current_game_start_unresolved"
            else:
                state.release_completed_before(start)
                coverage_complete, coverage_reason = _coverage_complete_for_start(
                    start,
                    missing_starts,
                    chronology_issue_starts,
                    pilot=pilot,
                )
            history_rows = [
                state.snapshot(
                    runner_id,
                    coverage_complete=coverage_complete,
                )
                for runner_id in frame["runner_id"]
            ]
            histories = pd.DataFrame(history_rows, index=frame.index)
            frame = pd.concat([frame, histories], axis=1)
            frame["runner_history_coverage_reason"] = coverage_reason
            frame["history_frozen_before_game"] = True
            frame.to_csv(
                handles[season],
                index=False,
                header=not headers_written[season],
            )
            headers_written[season] = True
            stats = season_stats[season]
            stats["opportunities"] += len(frame)
            stats["terminal_windows"] += int(frame["terminal_window"].sum())
            stats["catcher_assigned_windows"] += int(
                frame["opening_catcher_id"].notna().sum()
            )
            stats["unknown_action_windows"] += int(
                frame["unknown_action_classification_count"].gt(0).sum()
            )
            stats["known_state_conflict_windows"] += int(
                frame["known_state_conflict"].sum()
            )
            stats["attempt_history_eligible_windows"] += int(
                frame["attempt_history_eligible"].sum()
            )
            stats["conditional_success_history_eligible_windows"] += int(
                frame["conditional_success_history_eligible"].sum()
            )
            stats["pitcher_pickoff_windows"] += int(
                frame["recorded_pitcher_pickoff_indicator"].sum()
            )
            stats["steal_attempt_windows"] += int(
                frame["recorded_steal_attempt_indicator"].sum()
            )
            stats["catcher_changed_assignment_windows"] += int(
                frame["opening_catcher_assignment_method"]
                .fillna("")
                .eq("ordered_defensive_substitution_or_switch")
                .sum()
            )
            stats["cold_start_windows"] += int(
                frame["runner_history_status"].eq(
                    "no_prior_eligible_exposure"
                ).sum()
            )
            stats["incomplete_history_windows"] += int(
                frame["runner_history_status"].eq(
                    "missing_or_incomplete_historical_coverage"
                ).sum()
            )
            stats["observed_zero_attempt_windows"] += int(
                frame["runner_history_status"].eq(
                    "observed_zero_attempts_with_positive_exposure"
                ).sum()
            )
            stats["observed_prior_attempt_windows"] += int(
                frame["runner_history_status"].eq("observed_prior_attempts").sum()
            )
            reasons = frame["history_count_exclusion_reason"].fillna("").astype(str)
            exclusion_counts[season]["eligible_no_exclusion"] += int(reasons.eq("").sum())
            for value in reasons.loc[reasons.ne("")]:
                for reason in dict.fromkeys(value.split("|")):
                    exclusion_counts[season][reason] += 1
            if pd.notna(completion):
                state.queue_game(
                    season=season,
                    completion_time=completion,
                    frame=frame,
                )
    finally:
        for handle in handles.values():
            handle.close()
    for season, temporary in temporary_paths.items():
        target = output_dir / f"opportunities_{season}.csv.gz"
        os.replace(temporary, target)

    first_output = output_dir / f"opportunities_{seasons[0]}.csv.gz"
    write_historical_feature_dictionary(pd.read_csv(first_output, nrows=0).columns)

    summary_rows: list[dict[str, Any]] = []
    for season in seasons:
        season_feeds = feeds.loc[feeds["season"].eq(season)]
        season_meta = metadata.loc[metadata["season"].eq(season)]
        stats = season_stats[season]
        summary_rows.append(
            {
                "season": season,
                "split_role": BOUNDS[season][2],
                "scheduled_eligible_games": int(
                    season_feeds["feed_eligible"].astype(bool).sum()
                ),
                "processed_games": season_meta["game_pk"].nunique(),
                "missing_games": int(
                    season_feeds["feed_eligible"].astype(bool).sum()
                    - season_meta["game_pk"].nunique()
                ),
                "quarantined_games": int(
                    season_feeds["retrieval_status"].eq("quarantined").sum()
                ),
                "chronology_unavailable_games": int(
                    (
                        parse_utc_mixed(
                            season_meta["feed_game_start_utc"]
                        ).isna()
                        | parse_utc_mixed(
                            season_meta["feed_completion_time_utc"]
                        ).isna()
                    ).sum()
                ),
                "final_games_with_trailing_incomplete_play": int(
                    pd.to_numeric(
                        season_feeds.get(
                            "feed_trailing_incomplete_play_count",
                            pd.Series(0, index=season_feeds.index),
                        ),
                        errors="coerce",
                    )
                    .fillna(0)
                    .gt(0)
                    .sum()
                ),
                "events": int(season_meta["events"].sum()),
                "pitches": int(season_meta["pitches"].sum()),
                **dict(stats),
                "catcher_assignment_rate": stats["catcher_assigned_windows"]
                / stats["opportunities"]
                if stats["opportunities"]
                else np.nan,
                "cold_start_rate": stats["cold_start_windows"]
                / stats["opportunities"]
                if stats["opportunities"]
                else np.nan,
                "incomplete_history_rate": stats["incomplete_history_windows"]
                / stats["opportunities"]
                if stats["opportunities"]
                else np.nan,
                "dataset_scope": suffix,
            }
        )
    summary = pd.DataFrame(summary_rows)
    atomic_write_frame(
        ROOT / "results" / f"historical_{suffix}_coverage.csv", summary
    )
    exclusion_summary = pd.DataFrame(
        [
            {
                "season": season,
                "reason": reason,
                "windows": count,
                "dataset_scope": suffix,
            }
            for season in seasons
            for reason, count in sorted(exclusion_counts[season].items())
        ]
    )
    atomic_write_frame(
        ROOT / "results" / f"historical_{suffix}_exclusion_summary.csv",
        exclusion_summary,
    )
    history_status_summary = summary[
        [
            "season",
            "cold_start_windows",
            "observed_zero_attempt_windows",
            "observed_prior_attempt_windows",
            "incomplete_history_windows",
            "opportunities",
            "dataset_scope",
        ]
    ].copy()
    atomic_write_frame(
        ROOT / "results" / f"historical_{suffix}_history_status.csv",
        history_status_summary,
    )
    environment = pd.DataFrame(
        [
            ("python", platform.python_version()),
            ("pandas", pd.__version__),
            ("numpy", np.__version__),
            ("parser_version", PARSER_VERSION),
            ("dataset_scope", suffix),
            ("video_gate", "validation_pending"),
        ],
        columns=["item", "value"],
    )
    atomic_write_frame(
        ROOT / "results" / f"historical_{suffix}_environment.csv",
        environment,
    )
    return summary, environment


def validate_historical_outputs(
    seasons: Iterable[int], *, pilot: bool = False
) -> pd.DataFrame:
    """Run chunked invariants over the large ignored opportunity tables."""
    seasons = tuple(sorted(set(int(value) for value in seasons)))
    suffix = "pilot" if pilot else "development"
    coverage = pd.read_csv(
        ROOT / "results" / f"historical_{suffix}_coverage.csv"
    ).set_index("season")
    count_suffixes = [
        "eligible_opportunities",
        "attempted_opportunities",
        "attempt_records",
        "successes",
        "unsuccessful",
        "ambiguous_outcomes",
    ]
    check_rows: list[dict[str, Any]] = []

    def add(season: int, check: str, passed: bool, observed: Any, expected: Any) -> None:
        check_rows.append(
            {
                "season": season,
                "check": check,
                "passed": bool(passed),
                "observed": observed,
                "expected": expected,
                "dataset_scope": suffix,
            }
        )

    for season in seasons:
        path = PROCESSED / suffix / f"opportunities_{season}.csv.gz"
        seen_ids: set[str] = set()
        duplicate_ids = 0
        rows = 0
        negative_counts = 0
        decomposition_mismatches = 0
        status_mismatches = 0
        unfrozen_rows = 0
        missing_catchers = 0
        post_2023_counts_in_2022 = 0
        for chunk in pd.read_csv(path, chunksize=50_000, low_memory=False):
            rows += len(chunk)
            ids = chunk["opportunity_id"].astype(str)
            duplicate_ids += int(ids.duplicated().sum())
            duplicate_ids += sum(value in seen_ids for value in ids.unique())
            seen_ids.update(ids)
            all_count_columns: list[str] = []
            for count_name in count_suffixes:
                total_name = f"runner_prior_all_regimes_{count_name}"
                pre_name = f"runner_prior_pre_2023_{count_name}"
                post_name = f"runner_prior_post_2023_{count_name}"
                all_count_columns.extend([total_name, pre_name, post_name])
                total = pd.to_numeric(chunk[total_name], errors="coerce")
                pre = pd.to_numeric(chunk[pre_name], errors="coerce")
                post = pd.to_numeric(chunk[post_name], errors="coerce")
                decomposition_mismatches += int((total.ne(pre + post)).sum())
                if season == 2022:
                    post_2023_counts_in_2022 += int(post.ne(0).sum())
            numeric_counts = chunk[all_count_columns].apply(
                pd.to_numeric, errors="coerce"
            )
            negative_counts += int(numeric_counts.lt(0).sum().sum())
            opportunities = pd.to_numeric(
                chunk["runner_prior_all_regimes_eligible_opportunities"],
                errors="coerce",
            )
            attempts = pd.to_numeric(
                chunk["runner_prior_all_regimes_attempted_opportunities"],
                errors="coerce",
            )
            complete = chunk[
                "runner_history_coverage_complete_since_2022_start"
            ].astype(str).str.lower().eq("true")
            status = chunk["runner_history_status"].astype(str)
            expected_status = pd.Series("observed_prior_attempts", index=chunk.index)
            expected_status.loc[~complete] = "missing_or_incomplete_historical_coverage"
            expected_status.loc[complete & opportunities.eq(0)] = "no_prior_eligible_exposure"
            expected_status.loc[
                complete & opportunities.gt(0) & attempts.eq(0)
            ] = "observed_zero_attempts_with_positive_exposure"
            status_mismatches += int(status.ne(expected_status).sum())
            frozen = chunk["history_frozen_before_game"].astype(str).str.lower().eq("true")
            unfrozen_rows += int((~frozen).sum())
            missing_catchers += int(chunk["opening_catcher_id"].isna().sum())

        add(
            season,
            "row_count_matches_coverage",
            rows == int(coverage.at[season, "opportunities"]),
            rows,
            int(coverage.at[season, "opportunities"]),
        )
        add(season, "unique_opportunity_id", duplicate_ids == 0, duplicate_ids, 0)
        add(season, "nonnegative_history_counts", negative_counts == 0, negative_counts, 0)
        add(
            season,
            "all_regimes_equals_pre_plus_post",
            decomposition_mismatches == 0,
            decomposition_mismatches,
            0,
        )
        add(season, "history_status_logic", status_mismatches == 0, status_mismatches, 0)
        add(season, "history_frozen_before_game", unfrozen_rows == 0, unfrozen_rows, 0)
        add(season, "opening_catcher_assigned", missing_catchers == 0, missing_catchers, 0)
        if season == 2022:
            add(
                season,
                "no_post_2023_history_in_2022",
                post_2023_counts_in_2022 == 0,
                post_2023_counts_in_2022,
                0,
            )
    checks = pd.DataFrame(check_rows)
    atomic_write_frame(
        ROOT / "results" / f"historical_{suffix}_validation_checks.csv", checks
    )
    return checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["process", "histories", "validate", "all"]
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        default=list(DEFAULT_DEVELOPMENT_SEASONS),
    )
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--allow-test-data", action="store_true")
    parser.add_argument("--checkpoint-every", type=int, default=50)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command in {"process", "all"}:
        process_games(
            args.seasons,
            pilot=args.pilot,
            allow_test_data=args.allow_test_data,
            checkpoint_every=args.checkpoint_every,
        )
    if args.command in {"histories", "all"}:
        summary, _environment = assemble_forward_histories(
            args.seasons,
            pilot=args.pilot,
            allow_test_data=args.allow_test_data,
        )
        print(summary.to_string(index=False))
    if args.command in {"validate", "all"}:
        checks = validate_historical_outputs(args.seasons, pilot=args.pilot)
        print(checks.to_string(index=False))
        if not checks["passed"].all():
            raise SystemExit("Historical output validation failed")


if __name__ == "__main__":
    main()
