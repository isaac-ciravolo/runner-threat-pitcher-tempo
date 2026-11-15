"""Audit runner-control actions and first-base-only opportunities in cached feeds."""

from __future__ import annotations

import hashlib
import json
import platform
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from scripts.audit_feeds import extract_events
from scripts.tempo_benchmark import build_tempo_pairs, load_benchmark_feeds


CONFLICT_GAME = 746690
CONFLICT_PA = 38
REVIEW_SEED = 20241117
TAKE_CALLS = {"Ball", "Called Strike"}
RUNNER_TERMS = re.compile(
    r"pick.?off|step.?off|caught.?steal|stolen.?base|\bbalk\b|"
    r"pitch timer violation|disengagement",
    flags=re.IGNORECASE,
)
ACTION_COLUMNS = [
    "action_id", "game_pk", "official_date", "at_bat_index", "event_index",
    "event_order", "inning", "half_inning", "action_type", "initiator_role",
    "throwing_role", "target_base", "outcome_type", "runner_out", "safe_return",
    "runner_advance", "error_flag", "no_recorded_movement", "pitcher_id",
    "pitcher_name", "catcher_id", "catcher_name", "runner_id", "runner_name",
    "batter_id", "batter_name", "bases_before", "bases_after", "pre_balls",
    "pre_strikes", "pre_outs", "movement_event_types", "movement_summary",
    "credit_position_codes",
    "preceding_pitch_event_index", "preceding_pitch_play_id",
    "following_pitch_event_index", "following_pitch_play_id", "event_record_type",
    "raw_event_type", "raw_event_name", "raw_code", "raw_description",
    "raw_from_catcher", "raw_disengagement_num", "mapping_rule",
    "classification_confidence", "identity_confidence", "source_population",
    "source_cache_path", "source_url", "source_retrieved_utc", "source_sha256",
    "duplicate_game_source_count", "event_key", "known_state_conflict",
]


def _joined(values: Iterable[Any]) -> str:
    return "|".join(str(value) for value in values if value not in (None, "", np.nan))


def _value(mapping: dict[str, Any] | None, *keys: str) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _base_from_suffix(value: Any) -> str | None:
    match = re.search(r"_(1b|2b|3b|home)$", str(value or ""), flags=re.IGNORECASE)
    if not match:
        return None
    suffix = match.group(1).upper()
    return "HOME" if suffix == "HOME" else suffix


def _person_lookup(feed: dict[str, Any]) -> dict[int, str]:
    result: dict[int, str] = {}
    for person in (_value(feed, "gameData", "players") or {}).values():
        if person.get("id") is not None:
            result[int(person["id"])] = person.get("fullName") or str(person["id"])
    return result


def load_union_feeds(
    root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, list[tuple[pd.Series, dict[str, Any]]]]:
    """Load the audit + benchmark feed union, preferring audit copies on overlap."""
    specifications = [
        ("feasibility_audit", 0, root / "data" / "audit_sample_manifest.csv"),
        ("tempo_benchmark", 1, root / "data" / "tempo_benchmark_game_manifest.csv"),
    ]
    source_frames: list[pd.DataFrame] = []
    for source, priority, path in specifications:
        frame = pd.read_csv(path)
        frame["source_population"] = source
        frame["source_priority"] = priority
        frame["source_manifest"] = str(path.relative_to(root)).replace("\\", "/")
        source_frames.append(frame)
    sources = pd.concat(source_frames, ignore_index=True, sort=False)
    sources["game_pk"] = sources["game_pk"].astype(int)
    sources["source_cache_path"] = sources["cache_path"].astype(str)
    sources["source_count_for_game"] = sources.groupby("game_pk")["game_pk"].transform("size")
    sources["duplicate_game"] = sources["source_count_for_game"].gt(1)
    sha_agreement = sources.groupby("game_pk")["sha256"].transform(
        lambda values: values.dropna().astype(str).nunique() <= 1
    )
    sources["duplicate_sha_agreement"] = np.where(sources["duplicate_game"], sha_agreement, True)
    sources = sources.sort_values(["game_pk", "source_priority", "selection_order"])
    sources["selected_for_parse"] = ~sources.duplicated("game_pk", keep="first")
    selected = sources.loc[sources["selected_for_parse"]].copy()
    selected = selected.sort_values(["official_date", "game_pk"]).reset_index(drop=True)
    selected["union_selection_order"] = np.arange(1, len(selected) + 1)

    loaded: list[tuple[pd.Series, dict[str, Any]]] = []
    for row in selected.itertuples(index=False):
        path = root / str(row.cache_path)
        if not path.exists():
            raise FileNotFoundError(path)
        feed = json.loads(path.read_text(encoding="utf-8"))
        if int(feed.get("gamePk", -1)) != int(row.game_pk):
            raise ValueError(f"{path}: gamePk does not match manifest")
        manifest_row = pd.Series(row._asdict())
        manifest_row["selection_order"] = int(row.union_selection_order)
        loaded.append((manifest_row, feed))
    return sources.reset_index(drop=True), selected, loaded


def mapping_table() -> pd.DataFrame:
    rows = [
        ("event", "type == pickoff", "pickoff_throw", "fromCatcher true=>catcher; false=>pitcher; missing=>unknown", "linked movement attaches; no duplicate"),
        ("event", "type == stepoff or code == PSO", "step_off", "pitcher", "not a throw"),
        ("event/movement", "eventType starts pickoff_", "pickoff_throw", "position-1/2 credit when fromCatcher absent", "linked event and movement are one action"),
        ("event/movement", "eventType starts stolen_base_", "steal_attempt", "runner", "one row per distinct runner path"),
        ("event/movement", "eventType starts caught_stealing_", "steal_attempt", "runner", "caught outcome; fielding throw is evidence, not another action"),
        ("event/movement", "eventType == balk", "balk", "pitcher", "all tied advances attach to one event"),
        ("event/movement", "eventType == forced_balk and violation.type == pitcher_disengagement", "disengagement_violation", "pitcher", "forced advance is the outcome"),
        ("event", "no-pitch code VP / VC / AC", "timer_violation", "pitcher / catcher / batter", "not a pitch"),
        ("text candidate", "runner-control term without mapped field", "unknown_candidate", "unknown", "review; never coerced"),
    ]
    return pd.DataFrame(
        rows,
        columns=["evidence_level", "raw_condition", "action_type", "role_rule", "double_count_rule"],
    ).assign(protocol_version="1.1", frozen_date="2026-11-15")


def _mapping_for_event(event: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    details = event.get("details") or {}
    record_type = event.get("type")
    event_type = str(details.get("eventType") or "").lower()
    code = details.get("code")
    if record_type == "pickoff":
        from_catcher = details.get("fromCatcher")
        role = "catcher" if from_catcher is True else "pitcher" if from_catcher is False else "unknown"
        return "pickoff_throw", role, "playEvent.type=pickoff + details.fromCatcher", "high" if role != "unknown" else "medium"
    if record_type == "stepoff" or code == "PSO":
        return "step_off", "pitcher", "playEvent.type=stepoff/code=PSO", "high"
    if event_type.startswith("pickoff_"):
        return "pickoff_throw", None, "details.eventType starts pickoff_", "high"
    if event_type.startswith(("stolen_base_", "caught_stealing_")):
        return "steal_attempt", "runner", "details.eventType is steal/caught-stealing", "high"
    if event_type == "balk":
        return "balk", "pitcher", "details.eventType=balk", "high"
    if event_type == "forced_balk" and _value(details, "violation", "type") == "pitcher_disengagement":
        return "disengagement_violation", "pitcher", "forced_balk + pitcher_disengagement violation", "high"
    if record_type == "no_pitch" and code in {"VP", "VC", "AC"}:
        role = {"VP": "pitcher", "VC": "catcher", "AC": "batter"}[code]
        return "timer_violation", role, f"no_pitch code={code}", "high"
    text = " ".join(
        str(details.get(key) or "") for key in ("eventType", "event", "description", "code")
    )
    if RUNNER_TERMS.search(text):
        return "unknown_candidate", "unknown", "text candidate without mapped field", "low"
    return None, None, None, None


def _movement_groups(movements: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for position, movement in enumerate(movements):
        runner_id = _value(movement, "details", "runner", "id")
        groups[runner_id if runner_id is not None else ("unknown", position)].append(movement)
    return list(groups.values())


def _credit_details(
    movements: list[dict[str, Any]], people: dict[int, str]
) -> tuple[str | None, int | None, str | None, str]:
    credit_rows = [credit for item in movements for credit in item.get("credits", [])]
    positions = [str(_value(credit, "position", "code") or "") for credit in credit_rows]
    throwing_role = "pitcher" if "1" in positions else "catcher" if "2" in positions else None
    catcher = next(
        (credit for credit in credit_rows if str(_value(credit, "position", "code")) == "2"),
        None,
    )
    catcher_id = _value(catcher, "player", "id")
    catcher_name = people.get(int(catcher_id)) if catcher_id is not None else None
    return throwing_role, catcher_id, catcher_name, _joined(positions)


def _outcome(
    action_type: str, movements: list[dict[str, Any]]
) -> tuple[str, bool, bool, bool, bool, bool]:
    base_movements = [
        item for item in movements
        if (_value(item, "movement", "start") or _value(item, "movement", "originBase"))
        in {"1B", "2B", "3B"}
    ]
    event_types = [str(_value(item, "details", "eventType") or "").lower() for item in base_movements]
    movement_values = [item.get("movement") or {} for item in base_movements]
    runner_out = any(bool(value.get("isOut")) for value in movement_values)
    error_flag = any("error" in value for value in event_types)
    advance = any(
        not bool(value.get("isOut"))
        and value.get("end") not in (None, value.get("start"), value.get("originBase"))
        for value in movement_values
    )
    no_movement = not base_movements
    safe_return = action_type == "pickoff_throw" and not runner_out and not advance
    if runner_out and any("caught_stealing" in value for value in event_types):
        outcome_type = "caught_stealing"
    elif runner_out and action_type == "steal_attempt" and advance:
        outcome_type = "advance_then_out"
    elif runner_out:
        outcome_type = "picked_off"
    elif error_flag and advance:
        outcome_type = "error_advance"
    elif advance:
        outcome_type = "advance"
    elif safe_return:
        outcome_type = "safe_return"
    else:
        outcome_type = "no_runner_outcome"
    return outcome_type, runner_out, safe_return, advance, error_flag, no_movement


def _target_base(event: dict[str, Any], movements: list[dict[str, Any]]) -> str | None:
    details = event.get("details") or {}
    if event.get("type") == "pickoff" and str(details.get("code")) in {"1", "2", "3"}:
        return f"{details['code']}B"
    target = _base_from_suffix(details.get("eventType"))
    if target:
        return target
    for item in movements:
        movement = item.get("movement") or {}
        if movement.get("outBase"):
            return movement["outBase"]
        if movement.get("end"):
            return movement["end"]
    return None


def _event_key(game_pk: int, at_bat_index: int, event_index: Any) -> str:
    return f"{int(game_pk)}:{int(at_bat_index)}:{int(event_index)}"


def build_action_audit(
    loaded: list[tuple[pd.Series, dict[str, Any]]],
    events: pd.DataFrame,
    sources: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return tidy action rows plus candidate vocabulary and event-type inventories."""
    event_lookup = events.set_index("event_key", drop=False)
    source_lookup = sources.loc[sources["selected_for_parse"]].set_index("game_pk")
    source_counts = sources.groupby("game_pk").size().to_dict()
    action_rows: list[dict[str, Any]] = []
    vocabulary_rows: list[dict[str, Any]] = []
    inventory_rows: list[dict[str, Any]] = []

    for manifest_row, feed in loaded:
        game_pk = int(feed["gamePk"])
        people = _person_lookup(feed)
        for play in _value(feed, "liveData", "plays", "allPlays") or []:
            pa = int(_value(play, "about", "atBatIndex"))
            movements_by_index: dict[Any, list[dict[str, Any]]] = defaultdict(list)
            for movement in play.get("runners", []):
                movements_by_index[_value(movement, "details", "playIndex")].append(movement)
            classified_indexes: set[Any] = set()
            event_indexes = {event.get("index") for event in play.get("playEvents", [])}

            for event in play.get("playEvents", []):
                details = event.get("details") or {}
                index = event.get("index")
                tied = movements_by_index.get(index, [])
                action_type, initiator, mapping_rule, confidence = _mapping_for_event(event)
                inventory_rows.append(
                    {
                        "game_pk": game_pk,
                        "event_record_type": event.get("type"),
                        "event_type": details.get("eventType"),
                        "event_name": details.get("event"),
                        "code": details.get("code") or _value(details, "call", "code"),
                        "is_pitch": bool(event.get("isPitch")),
                        "description": details.get("description"),
                    }
                )
                text = " ".join(str(value or "") for value in (
                    event.get("type"), details.get("eventType"), details.get("event"),
                    details.get("code"), details.get("description"),
                ))
                if action_type is not None or RUNNER_TERMS.search(text):
                    linked = tied or [None]
                    for movement in linked:
                        movement_details = (movement or {}).get("details") or {}
                        movement_values = (movement or {}).get("movement") or {}
                        vocabulary_rows.append(
                            {
                                "record_source": "play_event",
                                "game_pk": game_pk,
                                "at_bat_index": pa,
                                "event_index": index,
                                "event_record_type": event.get("type"),
                                "event_type": details.get("eventType"),
                                "event_name": details.get("event"),
                                "code": details.get("code") or _value(details, "call", "code"),
                                "description": details.get("description"),
                                "is_pitch": bool(event.get("isPitch")),
                                "from_catcher": details.get("fromCatcher"),
                                "disengagement_num": details.get("disengagementNum"),
                                "movement_event_type": movement_details.get("eventType"),
                                "movement_origin": movement_values.get("originBase"),
                                "movement_start": movement_values.get("start"),
                                "movement_end": movement_values.get("end"),
                                "movement_out_base": movement_values.get("outBase"),
                                "movement_is_out": movement_values.get("isOut"),
                            }
                        )
                if action_type is None:
                    continue
                classified_indexes.add(index)
                if action_type == "steal_attempt" and tied:
                    movement_sets = _movement_groups(tied)
                else:
                    movement_sets = [tied]
                for subindex, movement_set in enumerate(movement_sets, start=1):
                    key = _event_key(game_pk, pa, index)
                    context = event_lookup.loc[key]
                    if isinstance(context, pd.DataFrame):
                        raise ValueError(f"Duplicate event key: {key}")
                    throwing_role, catcher_id, catcher_name, credit_positions = _credit_details(
                        movement_set, people
                    )
                    observed_initiator = initiator
                    if action_type == "pickoff_throw" and observed_initiator is None:
                        observed_initiator = throwing_role or "unknown"
                    movement_details = [item.get("details") or {} for item in movement_set]
                    runner_id = next(
                        (_value(item, "runner", "id") for item in movement_details if _value(item, "runner", "id") is not None),
                        None,
                    )
                    runner_name = next(
                        (_value(item, "runner", "fullName") for item in movement_details if _value(item, "runner", "fullName")),
                        None,
                    )
                    target = _target_base(event, movement_set)
                    if runner_id is None and action_type == "steal_attempt":
                        runner_id = _value(event, "player", "id")
                    if runner_id is None and action_type == "pickoff_throw" and target in {"1B", "2B", "3B"}:
                        runner_id = context.get(f"runner_{target.lower()}_before")
                    if runner_name is None and pd.notna(runner_id):
                        runner_name = people.get(int(runner_id))
                    outcome_type, runner_out, safe_return, advance, error_flag, no_movement = _outcome(
                        action_type, movement_set
                    )
                    suffix = f"r{subindex}" if len(movement_sets) > 1 else "e"
                    source = source_lookup.loc[game_pk]
                    action_rows.append(
                        {
                            "action_id": f"A-{game_pk}-{pa}-{int(index)}-{suffix}",
                            "game_pk": game_pk,
                            "official_date": context["official_date"],
                            "at_bat_index": pa,
                            "event_index": int(index),
                            "event_order": int(context["event_order"]),
                            "inning": context["inning"],
                            "half_inning": context["half_inning"],
                            "action_type": action_type,
                            "initiator_role": observed_initiator or "unknown",
                            "throwing_role": throwing_role,
                            "target_base": target,
                            "outcome_type": outcome_type,
                            "runner_out": runner_out,
                            "safe_return": safe_return,
                            "runner_advance": advance,
                            "error_flag": error_flag,
                            "no_recorded_movement": no_movement,
                            "pitcher_id": context["pitcher_id"],
                            "pitcher_name": context["pitcher_name"],
                            "catcher_id": catcher_id,
                            "catcher_name": catcher_name,
                            "runner_id": runner_id,
                            "runner_name": runner_name,
                            "batter_id": context["batter_id"],
                            "batter_name": context["batter_name"],
                            "bases_before": context["bases_before"],
                            "bases_after": context["bases_after"],
                            "pre_balls": context["derived_pre_balls"],
                            "pre_strikes": context["derived_pre_strikes"],
                            "pre_outs": context["derived_pre_outs"],
                            "movement_event_types": _joined(
                                _value(item, "details", "eventType") for item in movement_set
                            ),
                            "movement_summary": context["movement_summary"],
                            "credit_position_codes": credit_positions,
                            "event_record_type": event.get("type"),
                            "raw_event_type": details.get("eventType"),
                            "raw_event_name": details.get("event"),
                            "raw_code": details.get("code"),
                            "raw_description": details.get("description"),
                            "raw_from_catcher": details.get("fromCatcher"),
                            "raw_disengagement_num": details.get("disengagementNum"),
                            "mapping_rule": mapping_rule,
                            "classification_confidence": confidence,
                            "identity_confidence": "high" if movement_set else "medium" if runner_id is not None else "low",
                            "source_population": source["source_population"],
                            "source_cache_path": source["cache_path"],
                            "source_url": source.get("feed_url"),
                            "source_retrieved_utc": source.get("retrieved_utc"),
                            "source_sha256": source.get("sha256"),
                            "duplicate_game_source_count": int(source_counts[game_pk]),
                            "event_key": key,
                            "known_state_conflict": game_pk == CONFLICT_GAME and pa == CONFLICT_PA,
                        }
                    )

            # Runner movements with no classified play event remain explicit candidates.
            for index, movements in movements_by_index.items():
                relevant = [
                    item for item in movements
                    if str(_value(item, "details", "eventType") or "").lower().startswith(
                        ("pickoff_", "stolen_base_", "caught_stealing_", "balk")
                    )
                ]
                if not relevant or index in classified_indexes:
                    continue
                if index in event_indexes:
                    continue
                for subindex, movement_set in enumerate(_movement_groups(relevant), start=1):
                    movement_type = str(_value(movement_set[0], "details", "eventType") or "").lower()
                    action_type = "pickoff_throw" if movement_type.startswith("pickoff_") else "steal_attempt" if movement_type.startswith(("stolen_base_", "caught_stealing_")) else "balk"
                    vocabulary_rows.append(
                        {
                            "record_source": "unresolved_movement",
                            "game_pk": game_pk,
                            "at_bat_index": pa,
                            "event_index": index,
                            "event_record_type": None,
                            "event_type": None,
                            "event_name": None,
                            "code": None,
                            "description": None,
                            "is_pitch": False,
                            "from_catcher": None,
                            "disengagement_num": None,
                            "movement_event_type": movement_type,
                            "movement_origin": _value(movement_set[0], "movement", "originBase"),
                            "movement_start": _value(movement_set[0], "movement", "start"),
                            "movement_end": _value(movement_set[-1], "movement", "end"),
                            "movement_out_base": _value(movement_set[-1], "movement", "outBase"),
                            "movement_is_out": any(bool(_value(item, "movement", "isOut")) for item in movement_set),
                        }
                    )
                    # An unresolved record cannot be placed reliably in event chronology.
                    # Keep it visible in vocabulary and review rather than fabricate context.

    actions = pd.DataFrame(action_rows)
    if actions.empty:
        actions = pd.DataFrame(columns=ACTION_COLUMNS)
    else:
        # Attach nearest actual pitches within the plate appearance.
        for (_game, _pa), group in events.groupby(["game_pk", "at_bat_index"], sort=False):
            actual = group.loc[group["is_pitch"] & group["play_id"].notna()].sort_values("event_order")
            action_index = actions.index[
                actions["game_pk"].eq(_game) & actions["at_bat_index"].eq(_pa)
            ]
            for index in action_index:
                order = actions.at[index, "event_order"]
                previous = actual.loc[actual["event_order"].lt(order)].tail(1)
                following = actual.loc[actual["event_order"].gt(order)].head(1)
                actions.at[index, "preceding_pitch_event_index"] = previous["event_index"].iloc[0] if len(previous) else np.nan
                actions.at[index, "preceding_pitch_play_id"] = previous["play_id"].iloc[0] if len(previous) else None
                actions.at[index, "following_pitch_event_index"] = following["event_index"].iloc[0] if len(following) else np.nan
                actions.at[index, "following_pitch_play_id"] = following["play_id"].iloc[0] if len(following) else None
        for column in ACTION_COLUMNS:
            if column not in actions:
                actions[column] = np.nan
        actions = actions[ACTION_COLUMNS].sort_values(
            ["game_pk", "at_bat_index", "event_order", "action_id"]
        ).reset_index(drop=True)
        if actions["action_id"].duplicated().any():
            raise ValueError("Duplicate action_id")

    vocabulary = pd.DataFrame(vocabulary_rows)
    vocab_keys = [column for column in vocabulary.columns if column not in {"game_pk", "at_bat_index", "event_index"}]
    if not vocabulary.empty:
        examples = (
            vocabulary.assign(example_key=lambda frame: frame["game_pk"].astype(str) + ":" + frame["at_bat_index"].astype(str) + ":" + frame["event_index"].astype(str))
            .groupby(vocab_keys, dropna=False)
            .agg(record_count=("game_pk", "size"), game_count=("game_pk", "nunique"), representative_example=("example_key", "first"))
            .reset_index()
            .sort_values(["record_count", "event_record_type", "event_type"], ascending=[False, True, True])
        )
    else:
        examples = vocabulary

    inventory = pd.DataFrame(inventory_rows)
    inventory_keys = ["event_record_type", "event_type", "event_name", "code", "is_pitch"]
    inventory = (
        inventory.assign(description=inventory["description"].fillna(""))
        .groupby(inventory_keys, dropna=False)
        .agg(record_count=("game_pk", "size"), game_count=("game_pk", "nunique"), representative_description=("description", "first"))
        .reset_index()
        .sort_values(["record_count", "event_record_type", "event_type"], ascending=[False, True, True])
    )
    return actions, examples, inventory


def build_opportunity_windows(
    events: pd.DataFrame, actions: pd.DataFrame, state_audit: pd.DataFrame
) -> pd.DataFrame:
    action_groups = {
        key: frame.sort_values("action_id")
        for key, frame in actions.groupby("event_key", sort=False)
    }
    state_lookup = state_audit.set_index(["game_pk", "at_bat_index"])
    rows: list[dict[str, Any]] = []

    def open_window(first: pd.Series, anchor: str, order: int, runner_id: Any, timing: str) -> dict[str, Any]:
        return {
            "opportunity_id": f"W-{int(first.game_pk)}-{int(first.at_bat_index)}-{anchor}",
            "game_pk": int(first.game_pk),
            "official_date": first.official_date,
            "at_bat_index": int(first.at_bat_index),
            "inning": first.inning,
            "half_inning": first.half_inning,
            "pitcher_id": first.pitcher_id,
            "pitcher_name": first.pitcher_name,
            "batter_id": first.batter_id,
            "batter_name": first.batter_name,
            "runner_id": runner_id,
            "open_timing": timing,
            "open_anchor": anchor,
            "open_event_order": order,
            "open_balls": first.derived_pre_balls if timing == "before_first_event" else first.feed_count_balls,
            "open_strikes": first.derived_pre_strikes if timing == "before_first_event" else first.feed_count_strikes,
            "open_outs": first.derived_pre_outs if timing == "before_first_event" else first.feed_count_outs,
            "action_ids": [],
            "action_types": [],
            "initiator_roles": [],
        }

    for (game_pk, pa), group in events.groupby(["game_pk", "at_bat_index"], sort=False):
        ordered = group.sort_values("event_order").reset_index(drop=True)
        if ordered.empty:
            continue
        first = ordered.iloc[0]
        window: dict[str, Any] | None = None
        if first["bases_before"] == "1B":
            window = open_window(first, "pre", -1, first.get("runner_1b_before"), "before_first_event")

        for position, event in ordered.iterrows():
            is_actual_pitch = bool(event["is_pitch"] and pd.notna(event["play_id"]))
            key = event["event_key"]
            if window is not None and key in action_groups:
                action_frame = action_groups[key]
                window["action_ids"].extend(action_frame["action_id"].tolist())
                window["action_types"].extend(action_frame["action_type"].tolist())
                window["initiator_roles"].extend(action_frame["initiator_role"].tolist())

            close_reason: str | None = None
            following_pitch = False
            if window is not None:
                if is_actual_pitch:
                    close_reason = "next_pitch"
                    following_pitch = True
                elif event["bases_after"] != "1B":
                    close_reason = "state_exit"
                if close_reason:
                    actions_in_window = window.pop("action_ids")
                    types = window.pop("action_types")
                    roles = window.pop("initiator_roles")
                    window.update(
                        {
                            "close_event_index": event["event_index"],
                            "close_event_order": int(event["event_order"]),
                            "close_reason": close_reason,
                            "following_pitch_exists": following_pitch,
                            "following_pitch_play_id": event["play_id"] if following_pitch else None,
                            "action_ids": _joined(actions_in_window),
                            "action_types": _joined(sorted(set(types))),
                            "initiator_roles": _joined(sorted(set(roles))),
                            "action_count": len(actions_in_window),
                            "pickoff_throw_count": sum(value == "pickoff_throw" for value in types),
                            "steal_attempt_count": sum(value == "steal_attempt" for value in types),
                            "step_off_count": sum(value == "step_off" for value in types),
                            "any_attempt": any(value in {"pickoff_throw", "steal_attempt"} for value in types),
                            "terminal_without_pitch": not following_pitch,
                            "known_state_conflict": game_pk == CONFLICT_GAME and pa == CONFLICT_PA,
                        }
                    )
                    rows.append(window)
                    window = None

            later_event_exists = position < len(ordered) - 1
            if window is None and later_event_exists and event["bases_after"] == "1B":
                timing = "after_pitch" if is_actual_pitch else "after_state_entry"
                window = open_window(
                    event,
                    f"e{int(event.event_index)}",
                    int(event.event_order),
                    event.get("runner_1b_after"),
                    timing,
                )

        if window is not None:
            state = state_lookup.loc[(game_pk, pa)]
            actions_in_window = window.pop("action_ids")
            types = window.pop("action_types")
            roles = window.pop("initiator_roles")
            last = ordered.iloc[-1]
            window.update(
                {
                    "close_event_index": last["event_index"],
                    "close_event_order": int(last["event_order"]),
                    "close_reason": "half_inning_end" if bool(state["half_inning_ended"]) else "plate_appearance_end",
                    "following_pitch_exists": False,
                    "following_pitch_play_id": None,
                    "action_ids": _joined(actions_in_window),
                    "action_types": _joined(sorted(set(types))),
                    "initiator_roles": _joined(sorted(set(roles))),
                    "action_count": len(actions_in_window),
                    "pickoff_throw_count": sum(value == "pickoff_throw" for value in types),
                    "steal_attempt_count": sum(value == "steal_attempt" for value in types),
                    "step_off_count": sum(value == "step_off" for value in types),
                    "any_attempt": any(value in {"pickoff_throw", "steal_attempt"} for value in types),
                    "terminal_without_pitch": True,
                    "known_state_conflict": game_pk == CONFLICT_GAME and pa == CONFLICT_PA,
                }
            )
            rows.append(window)

    opportunities = pd.DataFrame(rows).sort_values(
        ["game_pk", "at_bat_index", "open_event_order"]
    ).reset_index(drop=True)
    if opportunities["opportunity_id"].duplicated().any():
        raise ValueError("Duplicate opportunity_id")
    return opportunities


def build_review_queue(actions: pd.DataFrame, opportunities: pd.DataFrame) -> pd.DataFrame:
    positives = actions.copy()
    positives["stratum"] = (
        positives["action_type"].fillna("unknown") + ":" +
        positives["initiator_role"].fillna("unknown") + ":" +
        positives["outcome_type"].fillna("unknown")
    )
    positives["random_order"] = positives["action_id"].map(
        lambda value: hashlib.sha256(f"{REVIEW_SEED}:{value}".encode()).hexdigest()
    )
    selected_positive = (
        positives.sort_values(["stratum", "random_order"])
        .groupby("stratum", group_keys=False)
        .head(5)
    )
    selected_positive = selected_positive.assign(
        review_record_type="positive_action",
        record_id=selected_positive["action_id"],
        expected_label=selected_positive["action_type"],
        expected_detail=selected_positive["initiator_role"] + ":" + selected_positive["outcome_type"],
        feed_description=selected_positive["raw_description"],
    )
    negatives = opportunities.loc[~opportunities["any_attempt"]].copy()
    negatives["random_order"] = negatives["opportunity_id"].map(
        lambda value: hashlib.sha256(f"{REVIEW_SEED}:{value}".encode()).hexdigest()
    )
    negatives = negatives.sort_values("random_order").head(20).assign(
        review_record_type="negative_control",
        record_id=lambda frame: frame["opportunity_id"],
        expected_label="no_recorded_attempt",
        expected_detail=lambda frame: frame["close_reason"],
        feed_description="",
    )
    columns = [
        "review_record_type", "record_id", "game_pk", "official_date", "at_bat_index",
        "inning", "half_inning", "expected_label", "expected_detail", "feed_description",
    ]
    queue = pd.concat([selected_positive[columns], negatives[columns]], ignore_index=True)
    queue["sample_seed"] = REVIEW_SEED
    queue["public_source_url"] = ""
    queue["public_source_type"] = ""
    queue["public_source_retrieved_date"] = ""
    queue["public_source_observation"] = ""
    queue["review_status"] = "pending_public_review"
    queue["agreement"] = ""
    queue["review_notes"] = ""
    return queue.sort_values(["review_record_type", "record_id"]).reset_index(drop=True)


def _pair_category(
    between: pd.DataFrame, detailed: pd.DataFrame
) -> list[str]:
    categories: set[str] = set()
    detailed_orders = set(detailed["event_order"].astype(int)) if not detailed.empty else set()
    for row in detailed.itertuples(index=False):
        if row.action_type == "pickoff_throw":
            categories.add(f"pickoff_throw_{row.initiator_role}")
        else:
            categories.add(str(row.action_type))
    for row in between.loc[~between["is_pitch"]].itertuples(index=False):
        if int(row.event_order) in detailed_orders:
            continue
        categories.add(str(row.action_category or "other_nonpitch"))
    return sorted(categories)


def build_tempo_action_join(
    root: Path, actions: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pitchers = pd.read_csv(root / "data" / "tempo_benchmark_pitchers.csv")
    _manifest, loaded = load_benchmark_feeds(root)
    benchmark_events, _states = extract_events(loaded)
    pairs = build_tempo_pairs(benchmark_events)
    selected_ids = set(pitchers["entity_id"].astype(int))
    primary_mask = (
        pairs["documented_rule_eligible"]
        & pairs["pitcher_id"].isin(selected_ids)
        & pairs["start_to_start_seconds"].notna()
        & pairs["start_to_start_seconds"].gt(0)
    )
    primary = pairs.loc[primary_mask].copy()
    benchmark_event_groups = {
        key: frame.sort_values("event_order")
        for key, frame in benchmark_events.groupby(["game_pk", "at_bat_index"], sort=False)
    }
    action_groups = {
        key: frame.sort_values(["event_order", "action_id"])
        for key, frame in actions.groupby(["game_pk", "at_bat_index"], sort=False)
    }
    category_map: dict[tuple[int, int, int, int], list[str]] = {}
    join_rows: list[dict[str, Any]] = []
    for row in primary.itertuples(index=False):
        key = (int(row.game_pk), int(row.at_bat_index))
        group = benchmark_event_groups[key]
        preceding_order = int(group.loc[group["event_index"].eq(row.preceding_event_index), "event_order"].iloc[0])
        following_order = int(group.loc[group["event_index"].eq(row.following_event_index), "event_order"].iloc[0])
        between = group.loc[group["event_order"].gt(preceding_order) & group["event_order"].lt(following_order)]
        detailed = action_groups.get(key, pd.DataFrame(columns=actions.columns))
        detailed = detailed.loc[
            detailed["event_order"].gt(preceding_order) & detailed["event_order"].lt(following_order)
        ]
        categories = _pair_category(between, detailed)
        pair_key = (int(row.game_pk), int(row.at_bat_index), int(row.preceding_event_index), int(row.following_event_index))
        category_map[pair_key] = categories
        if int(row.intervening_action_count) > 0:
            join_rows.append(
                {
                    "game_pk": int(row.game_pk),
                    "official_date": row.official_date,
                    "at_bat_index": int(row.at_bat_index),
                    "preceding_event_index": int(row.preceding_event_index),
                    "following_event_index": int(row.following_event_index),
                    "pitcher_id": int(row.pitcher_id),
                    "pitcher_name": row.pitcher_name,
                    "base_state": row.base_state,
                    "start_to_start_seconds": row.start_to_start_seconds,
                    "end_to_end_seconds": row.end_to_end_seconds,
                    "intervening_event_count": int(row.intervening_action_count),
                    "joined_action_categories": _joined(categories),
                    "detailed_action_ids": _joined(detailed["action_id"].tolist()),
                    "detailed_action_count": len(detailed),
                    "has_runner_control_detail": not detailed.empty,
                    "raw_intervening_actions": row.intervening_actions,
                }
            )
    joined = pd.DataFrame(join_rows)
    if len(joined) != 485:
        raise ValueError(f"Expected 485 action-interrupted documented pairs, observed {len(joined)}")

    contribution_rows: list[dict[str, Any]] = []
    for base_state in ["bases_empty", "runners_on"]:
        subset = joined.loc[joined["base_state"].eq(base_state)]
        categories = sorted({value for text in subset["joined_action_categories"] for value in str(text).split("|") if value})
        for category in categories:
            mask = subset["joined_action_categories"].map(lambda text: category in str(text).split("|"))
            selected = subset.loc[mask]
            contribution_rows.append(
                {
                    "base_state": base_state,
                    "action_category": category,
                    "intervals_nonexclusive": len(selected),
                    "median_start_to_start_seconds": selected["start_to_start_seconds"].median(),
                    "median_end_to_end_seconds": selected["end_to_end_seconds"].median(),
                }
            )
    contributions = pd.DataFrame(contribution_rows)

    published = pd.concat(
        [
            pitchers[["entity_id", "savant_empty_count", "savant_empty_median_seconds"]]
            .rename(columns={"entity_id": "pitcher_id", "savant_empty_count": "savant_count", "savant_empty_median_seconds": "savant_median_seconds"})
            .assign(base_state="bases_empty"),
            pitchers[["entity_id", "savant_onbase_count", "savant_onbase_median_seconds"]]
            .rename(columns={"entity_id": "pitcher_id", "savant_onbase_count": "savant_count", "savant_onbase_median_seconds": "savant_median_seconds"})
            .assign(base_state="runners_on"),
        ],
        ignore_index=True,
    )
    primary["pair_key"] = primary.apply(
        lambda row: (int(row.game_pk), int(row.at_bat_index), int(row.preceding_event_index), int(row.following_event_index)), axis=1
    )
    primary["category_list"] = primary["pair_key"].map(category_map)
    category_values = sorted({value for values in primary["category_list"] for value in values})
    sensitivity_rows: list[dict[str, Any]] = []
    scenarios = [("documented_rules", None), ("exclude_any_nonpitch_action", "__any__")]
    scenarios += [(f"exclude_{value}", value) for value in category_values]
    for scenario, excluded in scenarios:
        keep = pd.Series(True, index=primary.index)
        if excluded == "__any__":
            keep &= primary["intervening_action_count"].eq(0)
        elif excluded is not None:
            keep &= ~primary["category_list"].map(lambda values: excluded in values)
        selected = primary.loc[keep]
        summary = (
            selected.groupby(["pitcher_id", "pitcher_name", "base_state"], as_index=False)
            .agg(feed_count=("start_to_start_seconds", "size"), feed_median_seconds=("start_to_start_seconds", "median"))
        )
        summary = published.merge(summary, on=["pitcher_id", "base_state"], how="left")
        summary["pitcher_name"] = summary["pitcher_id"].map(pitchers.set_index("entity_id")["entity_name"])
        summary["scenario"] = scenario
        summary["excluded_category"] = excluded
        summary["feed_minus_savant_seconds"] = summary["feed_median_seconds"] - summary["savant_median_seconds"]
        sensitivity_rows.extend(summary.to_dict("records"))
    sensitivity = pd.DataFrame(sensitivity_rows)
    baseline = sensitivity.loc[sensitivity["scenario"].eq("documented_rules"), ["pitcher_id", "base_state", "feed_count", "feed_median_seconds"]].rename(
        columns={"feed_count": "baseline_count", "feed_median_seconds": "baseline_median_seconds"}
    )
    sensitivity = sensitivity.merge(baseline, on=["pitcher_id", "base_state"], how="left")
    sensitivity["count_change"] = sensitivity["feed_count"] - sensitivity["baseline_count"]
    sensitivity["median_change_seconds"] = sensitivity["feed_median_seconds"] - sensitivity["baseline_median_seconds"]

    gallen = sensitivity.loc[
        sensitivity["pitcher_id"].eq(668678)
        & sensitivity["base_state"].eq("runners_on")
        & sensitivity["scenario"].isin(["documented_rules", "exclude_any_nonpitch_action"])
    ].copy()
    gallen["event_identity_status"] = "not_identifiable_from_pitcher-level Savant summary"
    gallen["interpretation"] = np.where(
        gallen["scenario"].eq("exclude_any_nonpitch_action"),
        "feed action-free count is two below Savant; no published pitch IDs exist",
        "documented-rule feed population includes action-interrupted intervals",
    )
    return joined, contributions, sensitivity, gallen


def summary_tables(
    sources: pd.DataFrame, actions: pd.DataFrame, opportunities: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary = pd.DataFrame(
        [
            ("source_manifest_rows", len(sources)),
            ("unique_games", sources["game_pk"].nunique()),
            ("duplicate_games", int(sources["duplicate_game"].groupby(sources["game_pk"]).max().sum())),
            ("action_rows", len(actions)),
            ("pickoff_throws", int(actions["action_type"].eq("pickoff_throw").sum())),
            ("pitcher_pickoff_throws", int((actions["action_type"].eq("pickoff_throw") & actions["initiator_role"].eq("pitcher")).sum())),
            ("catcher_pickoff_throws", int((actions["action_type"].eq("pickoff_throw") & actions["initiator_role"].eq("catcher")).sum())),
            ("step_offs", int(actions["action_type"].eq("step_off").sum())),
            ("steal_attempts", int(actions["action_type"].eq("steal_attempt").sum())),
            ("opportunity_windows", len(opportunities)),
            ("windows_with_attempt", int(opportunities["any_attempt"].sum())),
            ("windows_without_attempt", int((~opportunities["any_attempt"]).sum())),
            ("terminal_windows_without_pitch", int(opportunities["terminal_without_pitch"].sum())),
            ("known_conflict_windows", int(opportunities["known_state_conflict"].sum())),
        ],
        columns=["metric", "value"],
    )
    conflict = pd.DataFrame(
        [
            {
                "scenario": "primary_include_known_conflict",
                "opportunity_windows": len(opportunities),
                "windows_with_attempt": int(opportunities["any_attempt"].sum()),
                "action_rows": len(actions),
            },
            {
                "scenario": "sensitivity_exclude_game_746690_pa_38",
                "opportunity_windows": int((~opportunities["known_state_conflict"]).sum()),
                "windows_with_attempt": int((~opportunities["known_state_conflict"] & opportunities["any_attempt"]).sum()),
                "action_rows": int((~actions["known_state_conflict"]).sum()),
            },
        ]
    )
    return summary, conflict


def run_audit(root: Path, *, write: bool = True) -> dict[str, pd.DataFrame]:
    sources, selected, loaded = load_union_feeds(root)
    events, state_audit = extract_events(loaded)
    actions, vocabulary, event_inventory = build_action_audit(loaded, events, sources)
    opportunities = build_opportunity_windows(events, actions, state_audit)
    review_queue = build_review_queue(actions, opportunities)
    joined, contributions, sensitivity, gallen = build_tempo_action_join(root, actions)
    summary, conflict = summary_tables(sources, actions, opportunities)
    environment = pd.DataFrame(
        [
            ("python", platform.python_version()),
            ("pandas", pd.__version__),
            ("numpy", np.__version__),
            ("protocol", "runner_control_action_audit_v1.1"),
            ("review_seed", str(REVIEW_SEED)),
            ("generated_date", "2026-11-15"),
        ],
        columns=["item", "value"],
    )
    selected_output = selected[
        ["game_pk", "official_date", "away_team", "home_team", "source_population", "cache_path", "feed_url", "retrieved_utc", "sha256", "source_count_for_game", "duplicate_sha_agreement"]
    ].copy()
    outputs = {
        "game_inventory": selected_output,
        "mapping": mapping_table(),
        "vocabulary": vocabulary,
        "event_type_inventory": event_inventory,
        "actions": actions,
        "opportunities": opportunities,
        "review_queue": review_queue,
        "tempo_interval_join": joined,
        "tempo_contributions": contributions,
        "tempo_sensitivity": sensitivity,
        "gallen_gap": gallen,
        "summary": summary,
        "conflict_sensitivity": conflict,
        "environment": environment,
    }
    if write:
        result_dir = root / "results"
        result_dir.mkdir(exist_ok=True)
        filenames = {
            "game_inventory": "runner_control_game_inventory.csv",
            "mapping": "runner_control_mapping.csv",
            "vocabulary": "runner_control_vocabulary_inventory.csv",
            "event_type_inventory": "runner_control_event_type_inventory.csv",
            "actions": "runner_control_actions.csv",
            "opportunities": "runner_control_opportunities.csv",
            "review_queue": "runner_control_review_queue.csv",
            "tempo_interval_join": "runner_control_tempo_interval_join.csv",
            "tempo_contributions": "runner_control_tempo_contributions.csv",
            "tempo_sensitivity": "runner_control_tempo_sensitivity.csv",
            "gallen_gap": "runner_control_gallen_gap.csv",
            "summary": "runner_control_summary.csv",
            "conflict_sensitivity": "runner_control_conflict_sensitivity.csv",
            "environment": "runner_control_environment.csv",
        }
        for key, filename in filenames.items():
            outputs[key].to_csv(result_dir / filename, index=False)
    return outputs


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    generated = run_audit(project_root, write=True)
    print(generated["summary"].to_string(index=False))
