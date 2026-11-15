"""Create the fixed blinded video-validation and runner-state pilot files."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_feeds import (
    build_intervals,
    build_opportunities,
    extract_events,
    load_feeds,
)
from scripts.video_validation import (
    ANNOTATION_COLUMNS,
    make_annotation_sheet,
    make_availability_log,
    select_validation_candidates,
)


DATA = ROOT / "data"


def _reconcile_generated_file(
    path: Path,
    fresh: pd.DataFrame,
    *,
    key: str,
    context_columns: list[str],
) -> None:
    """Update generated context while preserving human-entered review fields and rows."""
    if not path.exists():
        fresh.to_csv(path, index=False)
        return
    existing = pd.read_csv(path, keep_default_na=False)
    unknown = set(existing[key]) - set(fresh[key])
    if unknown:
        raise ValueError(f"{path.name} contains identifiers outside the frozen sample: {sorted(unknown)[:3]}")
    for column in fresh.columns:
        if column not in existing:
            existing[column] = ""
    lookup = fresh.drop_duplicates(key).set_index(key)
    for column in context_columns:
        if column == key:
            continue
        existing[column] = existing[key].map(lookup[column])
    missing = fresh.loc[~fresh[key].isin(set(existing[key]))]
    reconciled = pd.concat([existing[fresh.columns], missing], ignore_index=True)
    reconciled.to_csv(path, index=False)


def _seeded_rows(frame: pd.DataFrame, count: int, seed: int) -> pd.DataFrame:
    ordered = frame.sort_values(["official_date", "game_pk", "at_bat_index"]).copy()
    rng = np.random.default_rng(seed)
    ordered["_order"] = rng.random(len(ordered))
    return ordered.sort_values("_order").drop(columns="_order").head(count)


def runner_state_sample(opportunities: pd.DataFrame) -> pd.DataFrame:
    specifications = [
        ("ordinary_nonattempt", opportunities["opportunity_class"].eq("ordinary_nonattempt"), 10),
        (
            "pickoff_then_pitch",
            opportunities["opportunity_class"].eq("pickoff")
            & opportunities["status"].eq("next_pitch"),
            4,
        ),
        ("stolen_base", opportunities["opportunity_class"].eq("stolen_base"), 3),
        ("caught_stealing", opportunities["opportunity_class"].eq("caught_stealing"), 2),
        (
            "ends_without_next_pitch",
            opportunities["status"].eq("no_next_pitch_after_later_action"),
            1,
        ),
    ]
    rows = []
    for index, (label, mask, count) in enumerate(specifications):
        candidates = opportunities.loc[mask]
        if len(candidates) < count:
            raise ValueError(f"runner-state stratum {label} has only {len(candidates)} rows")
        chosen = _seeded_rows(candidates, count, 20241118 + index).copy()
        chosen["sample_case"] = label
        rows.append(chosen)
    sample = pd.concat(rows, ignore_index=True)
    sample["runner_validation_id"] = sample.apply(
        lambda row: (
            f"runner_g{int(row.game_pk)}_pa{int(row.at_bat_index)}_"
            f"e{int(row.opportunity_event_index)}"
        ),
        axis=1,
    )
    keep = [
        "runner_validation_id",
        "sample_case",
        "game_pk",
        "official_date",
        "at_bat_index",
        "inning",
        "half_inning",
        "opportunity_event_index",
        "next_pitch_event_index",
        "opportunity_play_id",
        "next_pitch_play_id",
        "pitcher_name",
        "batter_name",
        "status",
        "opportunity_class",
        "intervening_actions",
        "next_pitch_movement",
        "play_result",
    ]
    sample = sample[keep]
    sample["independent_source_url"] = ""
    sample["observed_pre_action_bases"] = ""
    sample["observed_outcome"] = ""
    sample["reviewer"] = ""
    sample["review_date_utc"] = ""
    sample["review_status"] = "pending"
    sample["unresolved_state_flag"] = False
    sample["notes"] = ""

    conflict = {column: "" for column in sample.columns}
    conflict.update(
        {
            "runner_validation_id": "runner_g746690_pa38_terminal_conflict",
            "sample_case": "terminal_state_conflict",
            "game_pk": 746690,
            "official_date": "2024-07-09",
            "at_bat_index": 38,
            "inning": 4,
            "half_inning": "bottom",
            "review_status": "pending",
            "unresolved_state_flag": True,
            "notes": (
                "Feed omits the terminal 1B-to-2B advance and places the batter at occupied "
                "first after the force out at third; subsequent state resets with the half-inning."
            ),
        }
    )
    return pd.concat([sample, pd.DataFrame([conflict])], ignore_index=True)


def main() -> None:
    manifest, loaded = load_feeds(ROOT)
    print(f"Loaded {len(loaded)} cached feeds.", flush=True)
    events, _states = extract_events(loaded)
    print(f"Extracted {len(events)} feed events.", flush=True)
    intervals = build_intervals(events)
    print(f"Built {len(intervals)} event-start intervals.", flush=True)
    opportunities = build_opportunities(events)
    print(f"Built {len(opportunities)} opportunities.", flush=True)

    candidates = select_validation_candidates(intervals, manifest)
    annotations = make_annotation_sheet(candidates)
    availability = make_availability_log(candidates)
    state_sample = runner_state_sample(opportunities)
    print(f"Selected {len(candidates)} timing candidates.", flush=True)

    candidates.to_csv(DATA / "video_validation_candidates.csv", index=False)
    annotation_path = DATA / "video_validation_annotations.csv"
    availability_path = DATA / "video_availability_log.csv"
    state_path = DATA / "runner_state_validation_sample.csv"
    annotation_context = [
        "validation_id", "sample_role", "second_annotation_requested", "game_pk",
        "official_date", "venue", "at_bat_index", "preceding_event_index",
        "following_event_index", "preceding_play_id", "following_play_id",
        "pitcher_name", "batter_name",
    ]
    availability_context = [
        "validation_id", "candidate_order", "sample_role", "validation_stratum",
        "stratum_order", "replacement_order", "game_pk", "official_date", "venue",
        "at_bat_index", "preceding_event_index", "following_event_index",
    ]
    _reconcile_generated_file(
        annotation_path, annotations, key="validation_id", context_columns=annotation_context
    )
    _reconcile_generated_file(
        availability_path, availability, key="validation_id", context_columns=availability_context
    )
    print(f"Reconciled and preserved annotations: {annotation_path.relative_to(ROOT)}")
    print(f"Reconciled and preserved availability log: {availability_path.relative_to(ROOT)}")
    if not state_path.exists():
        state_sample.to_csv(state_path, index=False)
    else:
        print(f"Preserved existing runner-state reviews: {state_path.relative_to(ROOT)}")
    pd.DataFrame(columns=ANNOTATION_COLUMNS).to_csv(
        DATA / "video_validation_template.csv", index=False
    )

    queue_rows = []
    used_ids: set[str] = set()
    used_games: set[int] = set()
    primary = candidates.loc[candidates["sample_role"].eq("primary")]
    for _stratum, group in primary.groupby("validation_stratum", sort=False):
        row = group.sort_values("candidate_order").iloc[0]
        queue_rows.append(row)
        used_ids.add(row["validation_id"])
        used_games.add(int(row["game_pk"]))
    for _, row in primary.sort_values("candidate_order").iterrows():
        if len(queue_rows) >= 12:
            break
        if row["validation_id"] in used_ids or int(row["game_pk"]) in used_games:
            continue
        queue_rows.append(row)
        used_ids.add(row["validation_id"])
        used_games.add(int(row["game_pk"]))
    queue = pd.DataFrame(queue_rows)[
        [
            "validation_id",
            "candidate_order",
            "validation_stratum",
            "game_pk",
            "official_date",
            "venue",
            "inning",
            "half_inning",
            "at_bat_index",
            "preceding_event_index",
            "following_event_index",
            "preceding_play_id",
            "following_play_id",
            "pitcher_name",
            "batter_name",
            "preceding_call",
            "following_call",
            "intervening_actions",
        ]
    ].copy()
    queue["manual_search_url"] = queue["game_pk"].map(
        lambda game_pk: f"https://www.mlb.com/tv/g{int(game_pk)}"
    )
    queue["manual_action"] = (
        "Locate one continuous source spanning both releases; record clip offsets and continuity "
        "in data/video_availability_log.csv before annotating."
    )
    queue.to_csv(ROOT / "results" / "manual_video_review_queue.csv", index=False)

    print(
        f"Created {len(primary)} primary and "
        f"{candidates['sample_role'].eq('reserve').sum()} reserve timing candidates."
    )
    print(
        f"Primary coverage: {primary['game_pk'].nunique()} games, "
        f"{primary['venue'].nunique()} venues."
    )
    print(f"Runner-state checks: {len(state_sample)} cases including the terminal conflict.")


if __name__ == "__main__":
    main()
