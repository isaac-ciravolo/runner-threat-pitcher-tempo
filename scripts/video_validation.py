"""Sampling, joining, and error summaries for blinded video timing validation."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


SAMPLE_SEED = 20241116
SECOND_REVIEW_SEED = 20241117
BOOTSTRAP_SEED = 20241119
STRATA = (
    "unusually_long",
    "pickoff",
    "step_off",
    "timeout",
    "other_interruption",
    "after_foul",
    "ordinary_runner_first_only",
    "ordinary_bases_empty",
)
PRIMARY_PER_STRATUM = {
    stratum: 15 if stratum.startswith("ordinary_") else 10 for stratum in STRATA
}
RESERVE_PER_STRATUM = 3

KEY_COLUMNS = [
    "game_pk",
    "at_bat_index",
    "preceding_event_index",
    "following_event_index",
]

ANNOTATION_COLUMNS = [
    "validation_id",
    "sample_role",
    "second_annotation_requested",
    "game_pk",
    "official_date",
    "venue",
    "at_bat_index",
    "preceding_event_index",
    "following_event_index",
    "preceding_play_id",
    "following_play_id",
    "pitcher_name",
    "batter_name",
    "video_source",
    "video_url",
    "clip_start_offset",
    "clip_end_offset",
    "video_access_date_utc",
    "continuity_status",
    "continuity_evidence",
    "timebase_type",
    "video_timebase_fps",
    "release_1_video_seconds",
    "release_2_video_seconds",
    "release_1_frame",
    "release_2_frame",
    "video_interval_seconds",
    "timing_uncertainty_seconds",
    "observed_interruption_type",
    "selected_for_timing",
    "usable_for_timing",
    "exclusion_reason",
    "annotator",
    "annotation_round",
    "annotation_date_utc",
    "notes",
]


def validation_id(row: pd.Series | dict[str, Any]) -> str:
    return (
        f"g{int(row['game_pk'])}_pa{int(row['at_bat_index'])}_"
        f"e{int(row['preceding_event_index'])}_{int(row['following_event_index'])}"
    )


def assign_validation_strata(intervals: pd.DataFrame) -> pd.Series:
    """Assign one prespecified stratum by priority without dropping intervals."""
    stratum = pd.Series("not_sampled", index=intervals.index, dtype="object")
    remaining = stratum.eq("not_sampled")

    rules = [
        ("unusually_long", intervals["event_start_interval_seconds"].gt(60)),
        ("pickoff", intervals["pickoff_flag"].fillna(False)),
        ("step_off", intervals["step_off_flag"].fillna(False)),
        ("timeout", intervals["timeout_flag"].fillna(False)),
        (
            "other_interruption",
            intervals[
                [
                    "mound_visit_flag",
                    "substitution_flag",
                    "other_nonpitch_flag",
                    "pitcher_changed_flag",
                    "batter_changed_flag",
                ]
            ]
            .fillna(False)
            .any(axis=1),
        ),
        ("after_foul", intervals["preceding_call"].fillna("").str.contains("Foul", case=False)),
        (
            "ordinary_runner_first_only",
            intervals["intervening_action_count"].eq(0)
            & intervals["bases_after_preceding_event"].eq("1B"),
        ),
        (
            "ordinary_bases_empty",
            intervals["intervening_action_count"].eq(0)
            & intervals["bases_after_preceding_event"].eq("empty"),
        ),
    ]
    for label, mask in rules:
        take = remaining & mask.fillna(False)
        stratum.loc[take] = label
        remaining = stratum.eq("not_sampled")
    return stratum


def _seeded_order(frame: pd.DataFrame, seed: int) -> pd.DataFrame:
    ordered = frame.sort_values(KEY_COLUMNS).copy()
    rng = random.Random(seed)
    ordered["_random_order"] = [rng.random() for _ in range(len(ordered))]
    return ordered.sort_values(["_random_order", *KEY_COLUMNS]).drop(columns="_random_order")


def select_validation_candidates(
    intervals: pd.DataFrame,
    manifest: pd.DataFrame,
    *,
    seed: int = SAMPLE_SEED,
    primary_per_stratum: int | dict[str, int] = PRIMARY_PER_STRATUM,
    reserve_per_stratum: int = RESERVE_PER_STRATUM,
) -> pd.DataFrame:
    candidates = intervals.copy()
    candidates["validation_stratum"] = assign_validation_strata(candidates)
    venue_lookup = manifest[["game_pk", "venue"]].drop_duplicates("game_pk")
    candidates = candidates.merge(venue_lookup, on="game_pk", how="left", validate="many_to_one")
    candidates["base_state"] = np.select(
        [
            candidates["bases_after_preceding_event"].eq("1B"),
            candidates["bases_after_preceding_event"].eq("empty"),
        ],
        ["runner_first_only", "bases_empty"],
        default="other",
    )
    candidates["recorded_interruption_group"] = np.where(
        candidates["validation_stratum"].isin(
            {"pickoff", "step_off", "timeout", "other_interruption"}
        ),
        "recorded_interruption",
        np.where(
            candidates["validation_stratum"].isin({"after_foul", "unusually_long"}),
            "challenge_other",
            "ordinary",
        ),
    )

    chosen: list[pd.DataFrame] = []
    for stratum_index, stratum in enumerate(STRATA):
        pool = candidates.loc[candidates["validation_stratum"].eq(stratum)]
        ordered = _seeded_order(pool, seed + stratum_index)
        primary_quota = (
            int(primary_per_stratum[stratum])
            if isinstance(primary_per_stratum, dict)
            else int(primary_per_stratum)
        )
        needed = primary_quota + reserve_per_stratum
        if len(ordered) < needed:
            raise ValueError(f"{stratum}: only {len(ordered)} candidates; need {needed}")
        selected = ordered.head(needed).copy()
        selected["sample_role"] = [
            "primary" if position < primary_quota else "reserve"
            for position in range(needed)
        ]
        selected["stratum_order"] = range(1, needed + 1)
        selected["replacement_order"] = [
            np.nan if position < primary_quota else position - primary_quota + 1
            for position in range(needed)
        ]
        chosen.append(selected)

    sample = pd.concat(chosen, ignore_index=True)
    sample["validation_id"] = sample.apply(validation_id, axis=1)
    if sample["validation_id"].duplicated().any():
        raise ValueError("duplicate validation_id after stratified selection")
    sample = sample.sort_values(
        ["sample_role", "validation_stratum", "stratum_order"],
        key=lambda series: series.map({"primary": 0, "reserve": 1}).fillna(series)
        if series.name == "sample_role"
        else series,
    ).reset_index(drop=True)
    sample["candidate_order"] = range(1, len(sample) + 1)
    sample["second_annotation_requested"] = False
    primary_indexes = sample.index[sample["sample_role"].eq("primary")].tolist()
    second_rng = random.Random(SECOND_REVIEW_SEED)
    second_indexes = second_rng.sample(primary_indexes, 12)
    sample.loc[second_indexes, "second_annotation_requested"] = True

    primaries = sample.loc[sample["sample_role"].eq("primary")]
    if primaries["game_pk"].nunique() < 10:
        raise ValueError("primary sample did not cover at least 10 games")
    if primaries["venue"].nunique() < 5:
        raise ValueError("primary sample did not cover at least 5 venues")

    keep = [
        "validation_id",
        "candidate_order",
        "sample_role",
        "validation_stratum",
        "stratum_order",
        "replacement_order",
        "second_annotation_requested",
        "game_pk",
        "official_date",
        "venue",
        "at_bat_index",
        "inning",
        "half_inning",
        "preceding_event_index",
        "following_event_index",
        "preceding_play_id",
        "following_play_id",
        "pitcher_name",
        "batter_name",
        "base_state",
        "recorded_interruption_group",
        "preceding_call",
        "following_call",
        "intervening_actions",
        "intervening_action_count",
        "pickoff_flag",
        "step_off_flag",
        "timeout_flag",
        "mound_visit_flag",
        "substitution_flag",
        "other_nonpitch_flag",
        "pitcher_changed_flag",
        "batter_changed_flag",
    ]
    return sample[keep]


def make_annotation_sheet(candidates: pd.DataFrame) -> pd.DataFrame:
    """Return a pre-populated annotator sheet with no feed timing values."""
    source_columns = [
        "validation_id",
        "sample_role",
        "second_annotation_requested",
        "game_pk",
        "official_date",
        "venue",
        "at_bat_index",
        "preceding_event_index",
        "following_event_index",
        "preceding_play_id",
        "following_play_id",
        "pitcher_name",
        "batter_name",
    ]
    sheet = candidates[source_columns].copy()
    for column in ANNOTATION_COLUMNS:
        if column not in sheet:
            sheet[column] = ""
    sheet["annotation_round"] = "primary"
    return sheet[ANNOTATION_COLUMNS]


def make_availability_log(candidates: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "validation_id",
        "candidate_order",
        "sample_role",
        "validation_stratum",
        "stratum_order",
        "replacement_order",
        "game_pk",
        "official_date",
        "venue",
        "at_bat_index",
        "preceding_event_index",
        "following_event_index",
    ]
    log = candidates[columns].copy()
    log["search_status"] = "not_searched"
    log["video_source"] = ""
    log["video_url"] = ""
    log["access_date_utc"] = ""
    log["continuity_status"] = ""
    log["clip_start_offset"] = ""
    log["clip_end_offset"] = ""
    log["search_method"] = ""
    log["search_reviewer"] = ""
    log["search_notes"] = ""
    return log


def _to_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def derive_video_intervals(annotations: pd.DataFrame) -> pd.DataFrame:
    frame = annotations.copy()
    numeric_columns = [
        "video_timebase_fps",
        "release_1_video_seconds",
        "release_2_video_seconds",
        "release_1_frame",
        "release_2_frame",
        "video_interval_seconds",
        "timing_uncertainty_seconds",
    ]
    for column in numeric_columns:
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    seconds_interval = frame["release_2_video_seconds"] - frame["release_1_video_seconds"]
    frame_interval = (
        (frame["release_2_frame"] - frame["release_1_frame"])
        / frame["video_timebase_fps"]
    )
    supplied = frame["video_interval_seconds"]
    frame["derived_video_interval_seconds"] = seconds_interval
    frame.loc[frame["derived_video_interval_seconds"].isna(), "derived_video_interval_seconds"] = (
        frame_interval
    )
    frame.loc[frame["derived_video_interval_seconds"].isna(), "derived_video_interval_seconds"] = (
        supplied
    )
    frame["release_route"] = np.select(
        [
            seconds_interval.notna(),
            seconds_interval.isna() & frame_interval.notna(),
            seconds_interval.isna() & frame_interval.isna() & supplied.notna(),
        ],
        ["seconds", "frames", "supplied_interval_only"],
        default="missing",
    )
    route_values = pd.concat(
        [seconds_interval, frame_interval, supplied], axis=1, keys=["seconds", "frames", "supplied"]
    ).replace([np.inf, -np.inf], np.nan)
    route_count = route_values.notna().sum(axis=1)
    frame["interval_consistency_difference"] = (
        route_values.max(axis=1) - route_values.min(axis=1)
    ).where(route_count.ge(2))
    return frame


def join_annotations_to_feed(
    annotations: pd.DataFrame,
    candidates: pd.DataFrame,
    intervals: pd.DataFrame,
) -> pd.DataFrame:
    if candidates["validation_id"].duplicated().any():
        raise ValueError("candidate validation_id values are not unique")
    if intervals.duplicated(KEY_COLUMNS).any():
        raise ValueError("feed interval keys are not unique")
    unknown = set(annotations["validation_id"].dropna()) - set(candidates["validation_id"])
    if unknown:
        raise ValueError(f"annotations contain unknown validation_id values: {sorted(unknown)[:3]}")

    candidate_context = candidates[
        ["validation_id", "validation_stratum", "base_state", "recorded_interruption_group", *KEY_COLUMNS]
    ]
    joined = annotations.merge(
        candidate_context,
        on=["validation_id", *KEY_COLUMNS],
        how="left",
        validate="many_to_one",
    )
    if joined["validation_stratum"].isna().any():
        bad = joined.loc[joined["validation_stratum"].isna(), "validation_id"].iloc[0]
        raise ValueError(f"annotation identifiers do not match candidate key: {bad}")
    feed_values = intervals[[*KEY_COLUMNS, "event_start_interval_seconds"]]
    joined = joined.merge(feed_values, on=KEY_COLUMNS, how="left", validate="many_to_one")
    if joined["event_start_interval_seconds"].isna().any():
        missing = joined.loc[joined["event_start_interval_seconds"].isna(), "validation_id"]
        raise ValueError(f"candidate interval key did not match feed: {missing.iloc[0]}")
    return derive_video_intervals(joined)


def eligible_annotations(
    joined: pd.DataFrame,
    *,
    annotation_rounds: Iterable[str] = ("primary",),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = joined.copy()
    selected = _to_bool(frame.get("selected_for_timing", pd.Series(False, index=frame.index)))
    usable = _to_bool(frame.get("usable_for_timing", pd.Series(False, index=frame.index)))
    continuous = frame.get("continuity_status", "").astype(str).eq("continuous_verified")
    positive = frame["derived_video_interval_seconds"].gt(0) & np.isfinite(
        frame["derived_video_interval_seconds"]
    )
    release_markers = frame["release_route"].isin({"seconds", "frames"})
    uncertainty_recorded = frame["timing_uncertainty_seconds"].ge(0)
    consistent_routes = frame["interval_consistency_difference"].isna() | frame[
        "interval_consistency_difference"
    ].le(frame["timing_uncertainty_seconds"])
    timebase_recorded = frame.get("timebase_type", "").fillna("").astype(str).str.strip().ne("")
    source_recorded = frame.get("video_source", "").fillna("").astype(str).str.strip().ne("")
    url_recorded = frame.get("video_url", "").fillna("").astype(str).str.strip().ne("")
    clip_start_recorded = frame.get("clip_start_offset", "").fillna("").astype(str).str.strip().ne("")
    clip_end_recorded = frame.get("clip_end_offset", "").fillna("").astype(str).str.strip().ne("")
    access_date_recorded = (
        frame.get("video_access_date_utc", "").fillna("").astype(str).str.strip().ne("")
    )
    continuity_evidence_recorded = (
        frame.get("continuity_evidence", "").fillna("").astype(str).str.strip().ne("")
    )
    interruption_recorded = (
        frame.get("observed_interruption_type", "").fillna("").astype(str).str.strip().ne("")
    )
    annotator_recorded = frame.get("annotator", "").fillna("").astype(str).str.strip().ne("")
    date_recorded = frame.get("annotation_date_utc", "").fillna("").astype(str).str.strip().ne("")
    no_exclusion = frame.get("exclusion_reason", "").fillna("").astype(str).str.strip().eq("")
    allowed_round = (
        frame.get("annotation_round", "primary")
        .fillna("primary")
        .astype(str)
        .isin(set(annotation_rounds))
    )
    eligible_mask = (
        selected
        & usable
        & continuous
        & positive
        & release_markers
        & uncertainty_recorded
        & consistent_routes
        & timebase_recorded
        & source_recorded
        & url_recorded
        & clip_start_recorded
        & clip_end_recorded
        & access_date_recorded
        & continuity_evidence_recorded
        & interruption_recorded
        & annotator_recorded
        & date_recorded
        & no_exclusion
        & allowed_round
    )
    frame["analysis_eligible"] = eligible_mask
    eligible = frame.loc[eligible_mask].copy()
    eligible["signed_error_seconds"] = (
        eligible["event_start_interval_seconds"] - eligible["derived_video_interval_seconds"]
    )
    eligible["absolute_error_seconds"] = eligible["signed_error_seconds"].abs()
    excluded = frame.loc[~eligible_mask].copy()
    return eligible, excluded


def error_summary(frame: pd.DataFrame, group_columns: Iterable[str] = ()) -> pd.DataFrame:
    columns = list(group_columns)

    def summarize(group: pd.DataFrame) -> pd.Series:
        signed = group["signed_error_seconds"]
        absolute = group["absolute_error_seconds"]
        return pd.Series(
            {
                "intervals": len(group),
                "games": group["game_pk"].nunique(),
                "mean_signed_error": signed.mean(),
                "median_signed_error": signed.median(),
                "mean_absolute_error": absolute.mean(),
                "median_absolute_error": absolute.median(),
                "p95_absolute_error": absolute.quantile(0.95),
            }
        )

    if frame.empty:
        return pd.DataFrame(
            columns=[
                *columns,
                "intervals",
                "games",
                "mean_signed_error",
                "median_signed_error",
                "mean_absolute_error",
                "median_absolute_error",
                "p95_absolute_error",
            ]
        )
    if not columns:
        return summarize(frame).to_frame().T
    return frame.groupby(columns, dropna=False).apply(summarize, include_groups=False).reset_index()


def cluster_bootstrap(
    frame: pd.DataFrame,
    *,
    replicates: int = 2000,
    seed: int = BOOTSTRAP_SEED,
) -> pd.DataFrame:
    metrics = [
        "mean_signed_error",
        "median_signed_error",
        "mean_absolute_error",
        "median_absolute_error",
        "p95_absolute_error",
    ]
    games = sorted(frame["game_pk"].unique()) if not frame.empty else []
    if len(games) < 10:
        return pd.DataFrame(columns=["metric", "lower_95", "upper_95", "replicates"])
    groups = {game: frame.loc[frame["game_pk"].eq(game)] for game in games}
    rng = np.random.default_rng(seed)
    rows: list[dict[str, float]] = []
    for _ in range(replicates):
        drawn = rng.choice(games, size=len(games), replace=True)
        bootstrap_frame = pd.concat([groups[game] for game in drawn], ignore_index=True)
        summary = error_summary(bootstrap_frame).iloc[0]
        rows.append({metric: float(summary[metric]) for metric in metrics})
    samples = pd.DataFrame(rows)
    return pd.DataFrame(
        {
            "metric": metrics,
            "lower_95": [samples[metric].quantile(0.025) for metric in metrics],
            "upper_95": [samples[metric].quantile(0.975) for metric in metrics],
            "replicates": replicates,
        }
    )


@dataclass(frozen=True)
class GateResult:
    outcome: str
    reasons: tuple[str, ...]
    validated_scope: str


def _error_criteria_pass(summary: pd.Series) -> bool:
    return bool(
        abs(summary["mean_signed_error"]) <= 0.10
        and abs(summary["median_signed_error"]) <= 0.10
        and summary["mean_absolute_error"] <= 0.15
        and summary["median_absolute_error"] <= 0.10
        and summary["p95_absolute_error"] <= 0.25
    )


def evaluate_gate(eligible: pd.DataFrame) -> GateResult:
    if eligible.empty:
        return GateResult(
            "validation_pending",
            ("No usable primary annotations are available.",),
            "none",
        )

    reasons: list[str] = []
    ordinary_first = eligible["validation_stratum"].eq("ordinary_runner_first_only").sum()
    ordinary_empty = eligible["validation_stratum"].eq("ordinary_bases_empty").sum()
    challenge = (~eligible["validation_stratum"].str.startswith("ordinary_")).sum()
    per_stratum = eligible.groupby("validation_stratum").size()
    coverage_ok = True
    coverage_checks = {
        "at least 60 usable intervals": len(eligible) >= 60,
        "at least 10 games": eligible["game_pk"].nunique() >= 10,
        "at least 5 venues": eligible["venue"].nunique() >= 5,
        "at least 15 ordinary runner-first-only intervals": ordinary_first >= 15,
        "at least 15 ordinary bases-empty intervals": ordinary_empty >= 15,
        "at least 20 challenge intervals": challenge >= 20,
    }
    for stratum in ("pickoff", "step_off", "timeout", "after_foul", "unusually_long"):
        coverage_checks[f"at least 3 {stratum} intervals"] = per_stratum.get(stratum, 0) >= 3
    for label, passed in coverage_checks.items():
        if not passed:
            reasons.append(f"Coverage shortfall: {label}.")
            coverage_ok = False

    overall = error_summary(eligible).iloc[0]
    error_ok = _error_criteria_pass(overall)
    if not error_ok:
        reasons.append("One or more aggregate error criteria failed.")

    subgroup_ok = True
    required_subgroups = {
        "ordinary_runner_first_only": eligible["validation_stratum"].eq(
            "ordinary_runner_first_only"
        ),
        "ordinary_bases_empty": eligible["validation_stratum"].eq(
            "ordinary_bases_empty"
        ),
        "combined_challenge": ~eligible["validation_stratum"].str.startswith("ordinary_"),
    }
    for label, mask in required_subgroups.items():
        group = eligible.loc[mask]
        if len(group) >= 5 and group["absolute_error_seconds"].median() > 0.25:
            subgroup_ok = False
            reasons.append(f"Subgroup median absolute error exceeded 0.25 s: {label}.")
    for stratum, group in eligible.loc[
        ~eligible["validation_stratum"].str.startswith("ordinary_")
    ].groupby("validation_stratum"):
        if len(group) >= 5 and group["absolute_error_seconds"].median() > 0.25:
            subgroup_ok = False
            reasons.append(f"Subgroup median absolute error exceeded 0.25 s: {stratum}.")

    if coverage_ok and error_ok and subgroup_ok:
        return GateResult("proceed_validated_scope", tuple(), "all prespecified pilot strata")

    ordinary = eligible.loc[eligible["validation_stratum"].str.startswith("ordinary_")]
    restricted_ok = (
        len(ordinary) >= 30
        and ordinary["game_pk"].nunique() >= 10
        and _error_criteria_pass(error_summary(ordinary).iloc[0])
    )
    if restricted_ok and (not error_ok or not subgroup_ok):
        return GateResult(
            "proceed_restricted_scope",
            tuple(reasons),
            "ordinary within-plate-appearance intervals only",
        )
    if not coverage_ok:
        return GateResult("collect_more_evidence", tuple(reasons), "none")
    return GateResult("reject_timing_measure", tuple(reasons), "none")
