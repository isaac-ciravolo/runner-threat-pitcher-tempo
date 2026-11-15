"""Construct and summarize the aggregate Baseball Savant tempo benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts.audit_feeds import extract_events


PAIR_KEYS = ["game_pk", "at_bat_index", "preceding_event_index", "following_event_index"]
TAKE_CALLS = {"Ball", "Called Strike"}


def load_benchmark_feeds(
    root: Path,
) -> tuple[pd.DataFrame, list[tuple[pd.Series, dict[str, Any]]]]:
    manifest = pd.read_csv(root / "data" / "tempo_benchmark_game_manifest.csv")
    loaded: list[tuple[pd.Series, dict[str, Any]]] = []
    for _, row in manifest.sort_values("selection_order").iterrows():
        path = root / str(row["cache_path"])
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload.get("gamePk", -1)) != int(row["game_pk"]):
            raise ValueError(f"{path}: gamePk does not match manifest")
        loaded.append((row, payload))
    return manifest, loaded


def _base_group(value: Any) -> str:
    return "bases_empty" if value == "empty" else "runners_on"


def build_tempo_pairs(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (_game_pk, _at_bat_index), group in events.groupby(
        ["game_pk", "at_bat_index"], sort=False
    ):
        ordered = group.sort_values("event_order")
        actual = ordered.loc[ordered["is_pitch"] & ordered["play_id"].notna()]
        if len(actual) < 2:
            continue
        positions = {index: position for position, index in enumerate(ordered.index)}
        for preceding_index, following_index in zip(actual.index, actual.index[1:]):
            preceding = ordered.loc[preceding_index]
            following = ordered.loc[following_index]
            between = ordered.iloc[
                positions[preceding_index] + 1 : positions[following_index]
            ]
            nonpitch = between.loc[~between["is_pitch"]]
            action_categories = sorted(set(nonpitch["action_category"].dropna().astype(str)))
            start_interval = (
                (following["start_time"] - preceding["start_time"]).total_seconds()
                if pd.notna(preceding["start_time"]) and pd.notna(following["start_time"])
                else np.nan
            )
            end_interval = (
                (following["end_time"] - preceding["end_time"]).total_seconds()
                if pd.notna(preceding["end_time"]) and pd.notna(following["end_time"])
                else np.nan
            )
            same_pitcher = preceding["pitcher_id"] == following["pitcher_id"]
            same_batter = preceding["batter_id"] == following["batter_id"]
            preceding_call = preceding["call_description"] or preceding["description"]
            documented_rule = bool(
                preceding_call in TAKE_CALLS and same_pitcher and same_batter
            )
            rows.append(
                {
                    "game_pk": int(preceding["game_pk"]),
                    "official_date": preceding["official_date"],
                    "at_bat_index": int(preceding["at_bat_index"]),
                    "preceding_event_index": int(preceding["event_index"]),
                    "following_event_index": int(following["event_index"]),
                    "preceding_play_id": preceding["play_id"],
                    "following_play_id": following["play_id"],
                    "pitcher_id": int(following["pitcher_id"]),
                    "pitcher_name": following["pitcher_name"],
                    "batter_id": int(following["batter_id"]),
                    "batter_name": following["batter_name"],
                    "preceding_call": preceding_call,
                    "same_pitcher": same_pitcher,
                    "same_batter": same_batter,
                    "documented_rule_eligible": documented_rule,
                    "base_state": _base_group(following["bases_before"]),
                    "preceding_state": _base_group(preceding["bases_after"]),
                    "following_bases_before": following["bases_before"],
                    "preceding_bases_after": preceding["bases_after"],
                    "start_to_start_seconds": start_interval,
                    "end_to_end_seconds": end_interval,
                    "intervening_action_count": len(nonpitch),
                    "intervening_action_categories": "|".join(action_categories),
                    "intervening_actions": " | ".join(
                        f"{row.event_index}:{row.event_type or row.event_name or row.event_record_type}"
                        f" ({row.description or ''})"
                        for row in nonpitch.itertuples()
                    ),
                    "pitcher_changed_flag": not same_pitcher,
                    "batter_changed_flag": not same_batter,
                }
            )
    pairs = pd.DataFrame(rows)
    if not pairs.empty and pairs.duplicated(PAIR_KEYS).any():
        raise ValueError("Duplicate tempo pair key")
    return pairs


def interval_eligibility(pairs: pd.DataFrame, value_column: str) -> pd.Series:
    values = pd.to_numeric(pairs[value_column], errors="coerce")
    return pairs["documented_rule_eligible"] & values.notna() & values.gt(0)


def summarize_measure(
    pairs: pd.DataFrame,
    pitchers: pd.DataFrame,
    *,
    value_column: str,
    scenario: str = "documented_rules",
    state_column: str = "base_state",
) -> pd.DataFrame:
    mask = interval_eligibility(pairs, value_column)
    if scenario == "no_intervening_actions":
        mask &= pairs["intervening_action_count"].eq(0)
    elif scenario == "at_most_30_seconds":
        mask &= pairs[value_column].le(30)
    elif scenario != "documented_rules":
        raise ValueError(f"Unknown scenario: {scenario}")
    selected_ids = set(pitchers["entity_id"].astype(int))
    eligible = pairs.loc[mask & pairs["pitcher_id"].isin(selected_ids)].copy()
    eligible["base_state_for_summary"] = eligible[state_column]
    summary = (
        eligible.groupby(["pitcher_id", "base_state_for_summary"], dropna=False)
        .agg(
            feed_eligible_intervals=(value_column, "size"),
            feed_median_seconds=(value_column, "median"),
            games=("game_pk", "nunique"),
            action_interrupted=("intervening_action_count", lambda values: int((values > 0).sum())),
            over_30_seconds=(value_column, lambda values: int((values > 30).sum())),
        )
        .reset_index()
        .rename(columns={"base_state_for_summary": "base_state"})
    )
    complete = pd.MultiIndex.from_product(
        [sorted(selected_ids), ["bases_empty", "runners_on"]],
        names=["pitcher_id", "base_state"],
    ).to_frame(index=False)
    summary = complete.merge(summary, on=["pitcher_id", "base_state"], how="left")
    name_lookup = pitchers.set_index("entity_id")["entity_name"]
    summary["pitcher_name"] = summary["pitcher_id"].map(name_lookup)
    summary["timestamp_measure"] = value_column.replace("_seconds", "")
    summary["scenario"] = scenario
    summary["state_definition"] = state_column
    return summary[
        [
            "pitcher_id", "pitcher_name", "base_state", "timestamp_measure", "scenario",
            "state_definition", "feed_eligible_intervals", "feed_median_seconds", "games",
            "action_interrupted", "over_30_seconds",
        ]
    ]


def published_long(pitchers: pd.DataFrame) -> pd.DataFrame:
    empty = pitchers[
        ["entity_id", "savant_empty_count", "savant_empty_median_seconds"]
    ].rename(
        columns={
            "entity_id": "pitcher_id",
            "savant_empty_count": "savant_eligible_intervals",
            "savant_empty_median_seconds": "savant_median_seconds",
        }
    )
    empty["base_state"] = "bases_empty"
    onbase = pitchers[
        ["entity_id", "savant_onbase_count", "savant_onbase_median_seconds"]
    ].rename(
        columns={
            "entity_id": "pitcher_id",
            "savant_onbase_count": "savant_eligible_intervals",
            "savant_onbase_median_seconds": "savant_median_seconds",
        }
    )
    onbase["base_state"] = "runners_on"
    return pd.concat([empty, onbase], ignore_index=True)


def add_benchmark_differences(
    summary: pd.DataFrame, pitchers: pd.DataFrame
) -> pd.DataFrame:
    compared = summary.merge(
        published_long(pitchers), on=["pitcher_id", "base_state"], how="left", validate="many_to_one"
    )
    compared["difference_seconds"] = (
        compared["feed_median_seconds"] - compared["savant_median_seconds"]
    )
    compared["absolute_difference_seconds"] = compared["difference_seconds"].abs()
    compared["count_difference"] = (
        compared["feed_eligible_intervals"] - compared["savant_eligible_intervals"]
    )
    compared["savant_display_seconds"] = compared["savant_median_seconds"].round(1)
    compared["feed_display_seconds"] = compared["feed_median_seconds"].round(1)
    compared["display_difference_seconds"] = (
        compared["feed_display_seconds"] - compared["savant_display_seconds"]
    )
    return compared


def coverage_summary(
    events: pd.DataFrame, pairs: pd.DataFrame, pitchers: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for pitcher in pitchers.itertuples(index=False):
        pitcher_events = events.loc[events["pitcher_id"].eq(int(pitcher.entity_id))]
        pitcher_pairs = pairs.loc[pairs["pitcher_id"].eq(int(pitcher.entity_id))]
        documented = pitcher_pairs["documented_rule_eligible"]
        rows.append(
            {
                "pitcher_id": int(pitcher.entity_id),
                "pitcher_name": pitcher.entity_name,
                "games": pitcher_events["game_pk"].nunique(),
                "feed_pitch_events": int(pitcher_events["is_pitch"].sum()),
                "actual_pitch_events": int(
                    (pitcher_events["is_pitch"] & pitcher_events["play_id"].notna()).sum()
                ),
                "adjacent_actual_pitch_pairs": len(pitcher_pairs),
                "documented_rule_pairs": int(documented.sum()),
                "interrupted_documented_pairs": int(
                    (documented & pitcher_pairs["intervening_action_count"].gt(0)).sum()
                ),
                "missing_start_intervals": int(
                    (documented & pitcher_pairs["start_to_start_seconds"].isna()).sum()
                ),
                "nonpositive_start_intervals": int(
                    (documented & pitcher_pairs["start_to_start_seconds"].le(0)).sum()
                ),
                "missing_end_intervals": int(
                    (documented & pitcher_pairs["end_to_end_seconds"].isna()).sum()
                ),
                "nonpositive_end_intervals": int(
                    (documented & pitcher_pairs["end_to_end_seconds"].le(0)).sum()
                ),
                "start_intervals_over_30": int(
                    (documented & pitcher_pairs["start_to_start_seconds"].gt(30)).sum()
                ),
                "end_intervals_over_30": int(
                    (documented & pitcher_pairs["end_to_end_seconds"].gt(30)).sum()
                ),
            }
        )
    return pd.DataFrame(rows)


def action_inventory(pairs: pd.DataFrame, pitchers: pd.DataFrame) -> pd.DataFrame:
    selected_ids = set(pitchers["entity_id"].astype(int))
    eligible = pairs.loc[
        pairs["documented_rule_eligible"]
        & pairs["pitcher_id"].isin(selected_ids)
        & pairs["intervening_action_count"].gt(0)
    ].copy()
    if eligible.empty:
        return pd.DataFrame(columns=["base_state", "action_category", "pairs"])
    expanded = eligible.assign(
        action_category=eligible["intervening_action_categories"].str.split("|")
    ).explode("action_category")
    return (
        expanded.groupby(["base_state", "action_category"], dropna=False)
        .size()
        .rename("pairs")
        .reset_index()
        .sort_values(["base_state", "pairs", "action_category"], ascending=[True, False, True])
    )


def load_and_build(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pitchers = pd.read_csv(root / "data" / "tempo_benchmark_pitchers.csv")
    manifest, loaded = load_benchmark_feeds(root)
    events, state_audit = extract_events(loaded)
    pairs = build_tempo_pairs(events)
    return pitchers, manifest, events, pairs
