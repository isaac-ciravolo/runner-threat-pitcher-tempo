"""Build schedules and resumably collect public MLB historical game feeds.

Examples
--------
python -m scripts.historical_collection schedules
python -m scripts.historical_collection pilot-manifest
python -m scripts.historical_collection collect --pilot
python -m scripts.historical_collection collect

The development collection defaults to 2022-2024.  A 2025 feed request is
rejected unless --allow-test-data is supplied explicitly; schedule metadata can
be prepared without that flag because scores and play outcomes are not retained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw" / "historical"
PROCESSED = DATA / "processed" / "historical"
SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
DEFAULT_DEVELOPMENT_SEASONS = (2022, 2023, 2024)
TEST_SEASON = 2025
PILOT_SEED = 20261115
PILOT_RANDOM_PER_SEASON = 3
PILOT_COMPLETE_BLOCK_DATES = 2
COLLECTION_VERSION = "historical_collection_v1.0"
BOUNDS = {
    2022: ("2022-04-07", "2022-10-05", "history_only"),
    2023: ("2023-03-30", "2023-10-01", "training"),
    2024: ("2024-03-20", "2024-09-30", "validation_development"),
    2025: ("2025-03-18", "2025-09-28", "locked_final_test"),
}
KNOWN_STRUCTURAL_EDGES = {
    747224: "catcher_and_pitcher_substitution|defensive_switch",
    745764: "pinch_runner",
    745682: "multiple_pickoffs|terminal_opportunity",
    745821: "repeated_pickoff_ordinal_review_outcome",
    747220: "pickoff_caught_stealing_continuation",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def file_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_bytes(
        path,
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def atomic_write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    frame.to_csv(temporary, index=False)
    os.replace(temporary, path)


def prepared_url(session: requests.Session, url: str, params: dict[str, Any]) -> str:
    return session.prepare_request(requests.Request("GET", url, params=params)).url


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {"User-Agent": "runner-threat-pitcher-tempo-historical-collection/1.0"}
    )
    return session


def request_with_backoff(
    session: requests.Session,
    url: str,
    *,
    attempts: int = 4,
    timeout: tuple[int, int] = (10, 60),
    base_backoff: float = 1.0,
) -> tuple[bytes | None, int | None, int, str]:
    last_error = ""
    last_status: int | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.get(url, timeout=timeout)
            last_status = response.status_code
            if response.status_code == 200:
                return response.content, response.status_code, attempt, ""
            last_error = f"HTTP {response.status_code}"
            if response.status_code not in {408, 425, 429, 500, 502, 503, 504}:
                break
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < attempts:
            time.sleep(base_backoff * (2 ** (attempt - 1)))
    return None, last_status, attempts, last_error


def schedule_manifest_path(season: int) -> Path:
    return DATA / f"historical_schedule_manifest_{season}.csv"


def feed_manifest_path(season: int) -> Path:
    return DATA / f"historical_feed_manifest_{season}.csv"


def schedule_cache_path(season: int) -> Path:
    return RAW / "schedules" / f"schedule_{season}.json"


def _value(mapping: dict[str, Any] | None, *keys: str) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def classify_schedule_status(game: dict[str, Any]) -> str:
    status = game.get("status") or {}
    abstract = str(status.get("abstractGameState") or "").lower()
    detailed = str(status.get("detailedState") or "").lower()
    reason = str(status.get("reason") or "").lower()
    text = f"{abstract} {detailed} {reason}"
    resumed = any(
        game.get(key) for key in ("resumedFromDate", "resumeDate")
    ) or "resum" in text
    rescheduled = any(
        game.get(key) for key in ("rescheduleDate", "rescheduledFromDate")
    ) or "reschedul" in text
    # StatsAPI can report abstract=Final for a game whose detailed state is
    # Cancelled.  The detailed cancellation wins because no completed game
    # exists to collect.
    if "cancel" in text:
        return "canceled"
    if abstract == "final" or detailed in {"final", "game over", "completed early"}:
        if resumed:
            return "resumed_completed"
        if rescheduled:
            return "rescheduled_completed"
        return "completed"
    if "postpon" in text:
        return "postponed"
    if "suspend" in text:
        return "suspended"
    if abstract in {"live", "in progress"}:
        return "in_progress"
    if abstract in {"preview", "scheduled"}:
        return "scheduled"
    return "other"


def parse_schedule(payload: dict[str, Any], season: int, source_url: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for date_block in payload.get("dates", []):
        schedule_date = date_block.get("date")
        for game in date_block.get("games", []):
            if game.get("gameType") != "R":
                continue
            status = game.get("status") or {}
            teams = game.get("teams") or {}
            venue = game.get("venue") or {}
            rows.append(
                {
                    "season": season,
                    "split_role": BOUNDS[season][2],
                    "game_pk": int(game["gamePk"]),
                    "game_type": game.get("gameType"),
                    "official_date": game.get("officialDate"),
                    "schedule_date": schedule_date,
                    "scheduled_start_utc": game.get("gameDate"),
                    "status_class": classify_schedule_status(game),
                    "abstract_state": status.get("abstractGameState"),
                    "coded_state": status.get("codedGameState"),
                    "detailed_state": status.get("detailedState"),
                    "status_reason": status.get("reason"),
                    "doubleheader_code": game.get("doubleHeader"),
                    "game_number": game.get("gameNumber"),
                    "series_game_number": game.get("seriesGameNumber"),
                    "games_in_series": game.get("gamesInSeries"),
                    "rescheduled_from_date": game.get("rescheduledFromDate"),
                    "rescheduled_date": game.get("rescheduleDate"),
                    "resumed_from_date": game.get("resumedFromDate"),
                    "resume_date": game.get("resumeDate"),
                    "away_team_id": _value(teams, "away", "team", "id"),
                    "away_team": _value(teams, "away", "team", "name"),
                    "home_team_id": _value(teams, "home", "team", "id"),
                    "home_team": _value(teams, "home", "team", "name"),
                    "venue_id": venue.get("id"),
                    "venue": venue.get("name"),
                    "schedule_source_url": source_url,
                }
            )
    if not rows:
        raise ValueError(f"Schedule response for {season} has no regular-season games")
    raw = pd.DataFrame(rows)
    priority = {
        "completed": 7,
        "resumed_completed": 7,
        "rescheduled_completed": 7,
        "suspended": 6,
        "in_progress": 5,
        "postponed": 4,
        "canceled": 3,
        "scheduled": 2,
        "other": 1,
    }
    raw["status_priority"] = raw["status_class"].map(priority).fillna(0)
    raw["schedule_date_sort"] = pd.to_datetime(raw["schedule_date"], errors="coerce")
    chosen = (
        raw.sort_values(
            ["game_pk", "status_priority", "schedule_date_sort"],
            ascending=[True, False, False],
        )
        .drop_duplicates("game_pk", keep="first")
        .copy()
    )
    evidence = (
        raw.sort_values(["game_pk", "schedule_date_sort"])
        .groupby("game_pk", sort=False)
        .agg(
            schedule_occurrence_count=("game_pk", "size"),
            schedule_dates_seen=("schedule_date", lambda values: "|".join(dict.fromkeys(values.dropna().astype(str)))),
            status_classes_seen=("status_class", lambda values: "|".join(dict.fromkeys(values.dropna().astype(str)))),
            detailed_states_seen=("detailed_state", lambda values: "|".join(dict.fromkeys(values.dropna().astype(str)))),
        )
        .reset_index()
    )
    chosen = chosen.merge(evidence, on="game_pk", how="left", validate="one_to_one")
    chosen["feed_eligible"] = chosen["status_class"].isin(
        ["completed", "resumed_completed", "rescheduled_completed"]
    )
    chosen["manifest_version"] = COLLECTION_VERSION
    chosen["selection_order"] = range(1, len(chosen) + 1)
    return chosen.drop(columns=["status_priority", "schedule_date_sort"]).sort_values(
        ["official_date", "scheduled_start_utc", "game_pk"]
    ).reset_index(drop=True)


def build_schedule_manifest(
    season: int,
    *,
    refresh: bool = False,
    session: requests.Session | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if season not in BOUNDS:
        raise ValueError(f"Unsupported season: {season}")
    session = session or make_session()
    params = {
        "sportId": 1,
        "season": season,
        "gameType": "R",
        "hydrate": "team,venue",
    }
    source_url = prepared_url(session, SCHEDULE_URL, params)
    cache = schedule_cache_path(season)
    if cache.exists() and not refresh:
        content = cache.read_bytes()
        retrieval_status = "cache_hit"
        retrieved_utc = datetime.fromtimestamp(
            cache.stat().st_mtime, tz=timezone.utc
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        http_status: int | None = 200
        attempts = 0
    else:
        content, http_status, attempts, error = request_with_backoff(session, source_url)
        if content is None:
            raise RuntimeError(f"Schedule retrieval failed for {season}: {error}")
        atomic_write_bytes(cache, content)
        retrieval_status = "downloaded"
        retrieved_utc = utc_now()
    payload = json.loads(content)
    manifest = parse_schedule(payload, season, source_url)
    atomic_write_frame(schedule_manifest_path(season), manifest)
    provenance = {
        "season": season,
        "source_url": source_url,
        "cache_path": cache.relative_to(ROOT).as_posix(),
        "retrieved_utc": retrieved_utc,
        "sha256": sha256_bytes(content),
        "bytes": len(content),
        "http_status": http_status,
        "attempts": attempts,
        "retrieval_status": retrieval_status,
        "unique_regular_season_games": len(manifest),
        "feed_eligible_games": int(manifest["feed_eligible"].sum()),
        "manifest_version": COLLECTION_VERSION,
    }
    return manifest, provenance


def run_schedules(seasons: Iterable[int], *, refresh: bool = False) -> pd.DataFrame:
    session = make_session()
    records: list[dict[str, Any]] = []
    for season in seasons:
        manifest, record = build_schedule_manifest(
            season, refresh=refresh, session=session
        )
        records.append(record)
        counts = manifest["status_class"].value_counts().to_dict()
        print(f"{season}: {len(manifest)} unique regular-season gamePk values; {counts}")
    provenance_path = DATA / "historical_schedule_provenance.csv"
    existing = (
        pd.read_csv(provenance_path)
        if provenance_path.exists()
        else pd.DataFrame(columns=records[0].keys() if records else [])
    )
    combined = pd.concat([existing, pd.DataFrame(records)], ignore_index=True)
    if not combined.empty:
        combined = combined.sort_values(["season", "retrieved_utc"]).drop_duplicates(
            "season", keep="last"
        )
    atomic_write_frame(provenance_path, combined)
    return combined


def load_schedules(seasons: Iterable[int]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for season in seasons:
        path = schedule_manifest_path(season)
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {path.relative_to(ROOT)}; run the schedules command first"
            )
        frames.append(pd.read_csv(path, low_memory=False))
    return pd.concat(frames, ignore_index=True, sort=False)


def build_pilot_manifest() -> tuple[pd.DataFrame, pd.DataFrame]:
    schedules = load_schedules(DEFAULT_DEVELOPMENT_SEASONS)
    completed = schedules.loc[schedules["feed_eligible"].astype(bool)].copy()
    reasons: dict[int, list[str]] = {}
    groups: dict[int, set[str]] = {}

    def select(game_pk: int, group: str, reason: str) -> None:
        reasons.setdefault(int(game_pk), []).append(reason)
        groups.setdefault(int(game_pk), set()).add(group)

    for season, season_games in completed.groupby("season", sort=True):
        dates = sorted(season_games["official_date"].dropna().astype(str).unique())[
            :PILOT_COMPLETE_BLOCK_DATES
        ]
        for row in season_games.loc[season_games["official_date"].astype(str).isin(dates)].itertuples(index=False):
            select(int(row.game_pk), "chronological_block", f"complete_first_{PILOT_COMPLETE_BLOCK_DATES}_official_dates_{season}")

        random_pool = season_games.copy()
        random_pool["random_key"] = random_pool["game_pk"].map(
            lambda value: hashlib.sha256(
                f"{PILOT_SEED}:{season}:{int(value)}".encode()
            ).hexdigest()
        )
        for row in random_pool.sort_values("random_key").head(PILOT_RANDOM_PER_SEASON).itertuples(index=False):
            select(int(row.game_pk), "random", f"seeded_random_{season}")

        doubleheaders = season_games.loc[
            season_games["doubleheader_code"].fillna("N").astype(str).ne("N")
        ]
        if len(doubleheaders):
            select(
                int(doubleheaders.sort_values(["official_date", "game_pk"]).iloc[0]["game_pk"]),
                "edge_case",
                f"doubleheader_{season}",
            )
        resumed = season_games.loc[
            season_games["status_class"].eq("resumed_completed")
            | season_games["status_classes_seen"].fillna("").str.contains("suspend|resum", case=False)
            | season_games["detailed_states_seen"].fillna("").str.contains("suspend|resum", case=False)
        ]
        if len(resumed):
            select(
                int(resumed.sort_values(["official_date", "game_pk"]).iloc[0]["game_pk"]),
                "edge_case",
                f"suspended_or_resumed_{season}",
            )

    available = set(completed["game_pk"].astype(int))
    for game_pk, reason in KNOWN_STRUCTURAL_EDGES.items():
        if game_pk in available:
            select(game_pk, "edge_case", reason)

    selected = completed.loc[completed["game_pk"].astype(int).isin(reasons)].copy()
    selected["selection_groups"] = selected["game_pk"].map(
        lambda value: "|".join(sorted(groups[int(value)]))
    )
    selected["selection_reasons"] = selected["game_pk"].map(
        lambda value: "|".join(dict.fromkeys(reasons[int(value)]))
    )
    selected["pilot_seed"] = PILOT_SEED
    selected["random_selected"] = selected["game_pk"].map(
        lambda value: "random" in groups[int(value)]
    )
    selected["pilot_history_scope"] = "incomplete_except_within_labeled_chronological_blocks"
    selected = selected.sort_values(
        ["season", "official_date", "scheduled_start_utc", "game_pk"]
    ).reset_index(drop=True)
    selected["pilot_selection_order"] = range(1, len(selected) + 1)
    atomic_write_frame(DATA / "historical_pilot_manifest.csv", selected)

    target_rows: list[dict[str, Any]] = []
    for season in DEFAULT_DEVELOPMENT_SEASONS:
        season_games = completed.loc[completed["season"].eq(season)]
        target_rows.extend(
            [
                {
                    "season": season,
                    "target": "seeded_random_games",
                    "available": True,
                    "selected_games": int(
                        selected.loc[
                            selected["season"].eq(season)
                            & selected["selection_groups"].str.contains("random"),
                            "game_pk",
                        ].nunique()
                    ),
                },
                {
                    "season": season,
                    "target": "doubleheader",
                    "available": bool(
                        season_games["doubleheader_code"].fillna("N").astype(str).ne("N").any()
                    ),
                    "selected_games": int(
                        selected.loc[
                            selected["season"].eq(season)
                            & selected["selection_reasons"].str.contains("doubleheader"),
                            "game_pk",
                        ].nunique()
                    ),
                },
                {
                    "season": season,
                    "target": "suspended_or_resumed",
                    "available": bool(
                        season_games["status_classes_seen"].fillna("").str.contains("suspend|resum", case=False).any()
                        or season_games["detailed_states_seen"].fillna("").str.contains("suspend|resum", case=False).any()
                    ),
                    "selected_games": int(
                        selected.loc[
                            selected["season"].eq(season)
                            & selected["selection_reasons"].str.contains("suspended_or_resumed"),
                            "game_pk",
                        ].nunique()
                    ),
                },
            ]
        )
    target_rows.extend(
        {
            "season": 2024,
            "target": reason,
            "available": game_pk in available,
            "selected_games": int(game_pk in set(selected["game_pk"].astype(int))),
        }
        for game_pk, reason in KNOWN_STRUCTURAL_EDGES.items()
    )
    targets = pd.DataFrame(target_rows)
    atomic_write_frame(DATA / "historical_pilot_targets.csv", targets)
    print(
        f"Pilot manifest: {len(selected)} unique games; "
        f"{int(selected['random_selected'].sum())} random selections."
    )
    return selected, targets


def _read_json_bytes(content: bytes) -> dict[str, Any]:
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("JSON root is not an object")
    return payload


def validate_final_feed(content: bytes, game_pk: int) -> tuple[bool, str, dict[str, Any]]:
    try:
        payload = _read_json_bytes(content)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        return False, f"invalid_json:{type(exc).__name__}:{exc}", {}
    if int(payload.get("gamePk", -1)) != int(game_pk):
        return False, "game_pk_mismatch", {}
    game_data = payload.get("gameData") or {}
    if _value(game_data, "game", "type") != "R":
        return False, "not_regular_season", {}
    status = game_data.get("status") or {}
    if str(status.get("abstractGameState") or "").lower() != "final":
        return False, f"feed_not_final:{status.get('detailedState')}", {}
    plays = _value(payload, "liveData", "plays", "allPlays")
    if not isinstance(plays, list) or not plays:
        return False, "missing_completed_plays", {}
    completed_plays = [
        play for play in plays if bool((play.get("about") or {}).get("isComplete"))
    ]
    if not completed_plays:
        return False, "missing_completed_plays", {}
    if not isinstance(_value(payload, "liveData", "boxscore", "teams"), dict):
        return False, "missing_boxscore_teams", {}
    event_count = sum(len(play.get("playEvents", [])) for play in plays)
    if event_count == 0:
        return False, "no_play_events", {}
    timestamps: list[pd.Timestamp] = []
    for play in plays:
        about = play.get("about") or {}
        for value in (about.get("endTime"),):
            parsed = pd.to_datetime(value, utc=True, errors="coerce")
            if pd.notna(parsed):
                timestamps.append(parsed)
        for event in play.get("playEvents", []):
            parsed = pd.to_datetime(event.get("endTime"), utc=True, errors="coerce")
            if pd.notna(parsed):
                timestamps.append(parsed)
    completion = max(timestamps).isoformat() if timestamps else None
    trailing_incomplete = 0
    trailing_incomplete_pitches = 0
    for play in reversed(plays):
        if bool((play.get("about") or {}).get("isComplete")):
            break
        trailing_incomplete += 1
        trailing_incomplete_pitches += sum(
            bool(event.get("isPitch")) for event in play.get("playEvents", [])
        )
    metadata = {
        "feed_detailed_state": status.get("detailedState"),
        "feed_game_start_utc": _value(game_data, "datetime", "dateTime"),
        "feed_completion_time_utc": completion,
        "feed_play_count": len(plays),
        "feed_event_count": event_count,
        "feed_trailing_incomplete_play_count": trailing_incomplete,
        "feed_trailing_incomplete_pitch_count": trailing_incomplete_pitches,
    }
    return True, "", metadata


def existing_cache_index() -> dict[int, list[dict[str, Any]]]:
    paths = [
        DATA / "audit_sample_manifest.csv",
        DATA / "tempo_benchmark_game_manifest.csv",
    ]
    index: dict[int, list[dict[str, Any]]] = {}
    for path in paths:
        if not path.exists():
            continue
        frame = pd.read_csv(path, low_memory=False)
        for row in frame.itertuples(index=False):
            index.setdefault(int(row.game_pk), []).append(
                {
                    "cache_path": str(row.cache_path),
                    "sha256": str(getattr(row, "sha256", "") or ""),
                    "source_manifest": path.relative_to(ROOT).as_posix(),
                    "retrieved_utc": str(getattr(row, "retrieved_utc", "") or ""),
                }
            )
    return index


def _valid_cache_candidate(
    candidate: dict[str, Any], game_pk: int
) -> tuple[bytes | None, str, dict[str, Any]]:
    path = ROOT / candidate["cache_path"]
    if not path.exists():
        return None, "cache_file_missing", {}
    content = path.read_bytes()
    digest = sha256_bytes(content)
    expected = candidate.get("sha256") or ""
    if expected and expected.lower() != digest.lower():
        return None, "cache_checksum_mismatch", {}
    valid, reason, metadata = validate_final_feed(content, game_pk)
    if not valid:
        return None, reason, {}
    metadata.update(
        {
            "cache_path": candidate["cache_path"],
            "sha256": digest,
            "bytes": len(content),
            "retrieved_utc": candidate.get("retrieved_utc") or "unknown_cached_file",
            "cache_source": candidate.get("source_manifest") or "historical_cache",
        }
    )
    return content, "", metadata


def historical_current_path(season: int, game_pk: int) -> Path:
    return RAW / str(season) / f"game_{game_pk}" / "current.json"


def quarantine_content(
    season: int, game_pk: int, content: bytes, label: str
) -> Path:
    digest = sha256_bytes(content)
    target = (
        RAW
        / str(season)
        / f"game_{game_pk}"
        / "quarantine"
        / f"{file_stamp()}_{label}_{digest[:12]}.json"
    )
    atomic_write_bytes(target, content)
    return target


def preserve_current_version(path: Path) -> Path:
    content = path.read_bytes()
    digest = sha256_bytes(content)
    target = path.parent / "versions" / f"{file_stamp()}_{digest[:12]}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(target))
    return target


def collect_one(
    row: pd.Series,
    session: requests.Session,
    existing_index: dict[int, list[dict[str, Any]]],
    *,
    refresh: bool,
    attempts: int,
) -> dict[str, Any]:
    season = int(row["season"])
    game_pk = int(row["game_pk"])
    source_url = FEED_URL.format(game_pk=game_pk)
    current = historical_current_path(season, game_pk)
    candidates: list[dict[str, Any]] = []
    if current.exists():
        candidates.append(
            {
                "cache_path": current.relative_to(ROOT).as_posix(),
                "sha256": "",
                "source_manifest": "historical_current",
                "retrieved_utc": datetime.fromtimestamp(
                    current.stat().st_mtime, tz=timezone.utc
                ).isoformat(timespec="seconds").replace("+00:00", "Z"),
            }
        )
    candidates.extend(existing_index.get(game_pk, []))
    cache_errors: list[str] = []
    if not refresh:
        for candidate in candidates:
            content, error, metadata = _valid_cache_candidate(candidate, game_pk)
            if content is not None:
                return {
                    **metadata,
                    "game_pk": game_pk,
                    "season": season,
                    "source_url": source_url,
                    "retrieval_status": "reused_verified_cache",
                    "http_status": 200,
                    "attempts": 0,
                    "error": "",
                    "version_selection": "verified_current_or_prior_manifest_cache",
                    "previous_version_path": "",
                    "quarantine_path": "",
                }
            cache_errors.append(
                f"{candidate.get('cache_path')}:{error}"
            )

    content, http_status, used_attempts, error = request_with_backoff(
        session, source_url, attempts=attempts
    )
    if content is None:
        return {
            "game_pk": game_pk,
            "season": season,
            "source_url": source_url,
            "cache_path": current.relative_to(ROOT).as_posix(),
            "retrieved_utc": utc_now(),
            "sha256": "",
            "bytes": "",
            "http_status": http_status,
            "retrieval_status": "failed",
            "attempts": used_attempts,
            "error": error or "download_failed",
            "cache_validation_errors": "|".join(cache_errors),
            "version_selection": "none",
            "previous_version_path": "",
            "quarantine_path": "",
        }
    valid, validation_error, feed_metadata = validate_final_feed(content, game_pk)
    if not valid:
        quarantine = quarantine_content(
            season, game_pk, content, "invalid_response"
        )
        return {
            "game_pk": game_pk,
            "season": season,
            "source_url": source_url,
            "cache_path": current.relative_to(ROOT).as_posix(),
            "retrieved_utc": utc_now(),
            "sha256": sha256_bytes(content),
            "bytes": len(content),
            "http_status": http_status,
            "retrieval_status": "quarantined",
            "attempts": used_attempts,
            "error": validation_error,
            "cache_validation_errors": "|".join(cache_errors),
            "version_selection": "none",
            "previous_version_path": "",
            "quarantine_path": quarantine.relative_to(ROOT).as_posix(),
            **feed_metadata,
        }

    digest = sha256_bytes(content)
    previous = ""
    retrieval_status = "downloaded"
    if current.exists():
        previous_digest = sha256_bytes(current.read_bytes())
        if previous_digest == digest:
            retrieval_status = "refreshed_unchanged"
        else:
            previous = preserve_current_version(current).relative_to(ROOT).as_posix()
            retrieval_status = "refreshed_changed"
    atomic_write_bytes(current, content)
    return {
        "game_pk": game_pk,
        "season": season,
        "source_url": source_url,
        "cache_path": current.relative_to(ROOT).as_posix(),
        "retrieved_utc": utc_now(),
        "sha256": digest,
        "bytes": len(content),
        "http_status": http_status,
        "retrieval_status": retrieval_status,
        "attempts": used_attempts,
        "error": "",
        "cache_validation_errors": "|".join(cache_errors),
        "version_selection": "new_validated_current",
        "previous_version_path": previous,
        "quarantine_path": "",
        **feed_metadata,
    }


def initial_feed_manifest(schedule: pd.DataFrame) -> pd.DataFrame:
    selected = schedule.loc[schedule["feed_eligible"].astype(bool)].copy()
    selected["source_url"] = selected["game_pk"].map(
        lambda value: FEED_URL.format(game_pk=int(value))
    )
    selected["cache_path"] = selected.apply(
        lambda row: historical_current_path(
            int(row["season"]), int(row["game_pk"])
        ).relative_to(ROOT).as_posix(),
        axis=1,
    )
    selected["retrieved_utc"] = ""
    selected["sha256"] = ""
    selected["bytes"] = pd.NA
    selected["http_status"] = pd.NA
    selected["retrieval_status"] = "not_attempted"
    selected["attempts"] = 0
    selected["error"] = ""
    selected["cache_validation_errors"] = ""
    selected["version_selection"] = ""
    selected["previous_version_path"] = ""
    selected["quarantine_path"] = ""
    selected["feed_detailed_state"] = ""
    selected["feed_game_start_utc"] = ""
    selected["feed_completion_time_utc"] = ""
    selected["feed_play_count"] = pd.NA
    selected["feed_event_count"] = pd.NA
    selected["feed_trailing_incomplete_play_count"] = pd.NA
    selected["feed_trailing_incomplete_pitch_count"] = pd.NA
    return selected


def update_manifest_record(
    manifest: pd.DataFrame, game_pk: int, record: dict[str, Any]
) -> None:
    """Update a reloaded manifest without pandas' all-empty dtype trap."""
    for key, value in record.items():
        if key in manifest.columns:
            if isinstance(value, str) and manifest[key].dtype != object:
                manifest[key] = manifest[key].astype(object)
            manifest.at[game_pk, key] = value
        else:
            manifest[key] = pd.Series(pd.NA, index=manifest.index, dtype=object)
            manifest.at[game_pk, key] = value


def collect_feeds(
    seasons: Iterable[int],
    *,
    pilot: bool = False,
    allow_test_data: bool = False,
    refresh: bool = False,
    pace_seconds: float = 0.25,
    attempts: int = 4,
    checkpoint_every: int = 20,
    retry_problems: bool = False,
) -> pd.DataFrame:
    run_started_utc = utc_now()
    run_started_clock = time.monotonic()
    seasons = tuple(sorted(set(int(value) for value in seasons)))
    if TEST_SEASON in seasons and not allow_test_data:
        raise ValueError(
            "2025 is the locked final test. Re-run with --allow-test-data only when the test-opening policy authorizes feed collection."
        )
    if any(season not in BOUNDS for season in seasons):
        raise ValueError(f"Unsupported seasons: {seasons}")
    schedules = load_schedules(seasons)
    eligible = schedules.loc[schedules["feed_eligible"].astype(bool)].copy()
    if pilot:
        pilot_path = DATA / "historical_pilot_manifest.csv"
        if not pilot_path.exists():
            raise FileNotFoundError("Run pilot-manifest before --pilot collection")
        pilot_games = set(pd.read_csv(pilot_path)["game_pk"].astype(int))
        eligible = eligible.loc[eligible["game_pk"].astype(int).isin(pilot_games)]
    existing_index = existing_cache_index()
    session = make_session()
    all_frames: list[pd.DataFrame] = []
    run_records: list[dict[str, Any]] = []
    ledger_path = PROCESSED / "download_attempts.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    for season in seasons:
        season_schedule = schedules.loc[schedules["season"].eq(season)]
        manifest_path = feed_manifest_path(season)
        if manifest_path.exists():
            manifest = pd.read_csv(manifest_path, low_memory=False)
        else:
            manifest = initial_feed_manifest(season_schedule)
        manifest = manifest.drop_duplicates("game_pk", keep="last").set_index("game_pk", drop=False)
        schedule_by_game = season_schedule.set_index("game_pk", drop=False)
        for column in season_schedule.columns:
            manifest[column] = manifest["game_pk"].map(schedule_by_game[column])
        targets = eligible.loc[eligible["season"].eq(season)].sort_values(
            ["official_date", "scheduled_start_utc", "game_pk"]
        )
        if retry_problems:
            problem_ids = set(
                manifest.loc[
                    ~manifest["retrieval_status"].isin(
                        {
                            "reused_verified_cache",
                            "downloaded",
                            "refreshed_changed",
                            "refreshed_unchanged",
                        }
                    ),
                    "game_pk",
                ].astype(int)
            )
            targets = targets.loc[targets["game_pk"].astype(int).isin(problem_ids)]
        print(f"{season}: processing {len(targets)} {'pilot ' if pilot else ''}feeds", flush=True)
        for position, row in enumerate(targets.itertuples(index=False), start=1):
            row_series = pd.Series(row._asdict())
            record = collect_one(
                row_series,
                session,
                existing_index,
                refresh=refresh,
                attempts=attempts,
            )
            run_records.append(record)
            game_pk = int(row.game_pk)
            update_manifest_record(manifest, game_pk, record)
            with ledger_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
            if position % checkpoint_every == 0 or position == len(targets):
                atomic_write_frame(
                    manifest_path,
                    manifest.reset_index(drop=True).sort_values(
                        ["official_date", "scheduled_start_utc", "game_pk"]
                    ),
                )
                counts = manifest.loc[
                    manifest["game_pk"].isin(targets["game_pk"]),
                    "retrieval_status",
                ].value_counts().to_dict()
                print(f"{season}: {position}/{len(targets)}; {counts}", flush=True)
            if record["retrieval_status"] in {
                "downloaded",
                "refreshed_changed",
                "refreshed_unchanged",
                "failed",
                "quarantined",
            }:
                time.sleep(max(0.0, pace_seconds))
        atomic_write_frame(
            manifest_path,
            manifest.reset_index(drop=True).sort_values(
                ["official_date", "scheduled_start_utc", "game_pk"]
            ),
        )
        all_frames.append(manifest.reset_index(drop=True))
    combined_frames = pd.concat(all_frames, ignore_index=True, sort=False)
    run_frame = pd.DataFrame(
        run_records,
        columns=(
            list(run_records[0])
            if run_records
            else ["retrieval_status", "bytes"]
        ),
    )
    run_summary = pd.DataFrame(
        [
            {
                "run_started_utc": run_started_utc,
                "run_finished_utc": utc_now(),
                "wall_seconds": round(time.monotonic() - run_started_clock, 3),
                "seasons": "|".join(str(value) for value in seasons),
                "pilot": pilot,
                "refresh": refresh,
                "retry_problems": retry_problems,
                "pace_seconds": pace_seconds,
                "targets": len(run_frame),
                "network_responses": int(
                    run_frame["retrieval_status"].isin(
                        [
                            "downloaded",
                            "refreshed_changed",
                            "refreshed_unchanged",
                            "quarantined",
                        ]
                    ).sum()
                ),
                "verified_cache_reuses": int(
                    run_frame["retrieval_status"].eq(
                        "reused_verified_cache"
                    ).sum()
                ),
                "failed": int(run_frame["retrieval_status"].eq("failed").sum()),
                "quarantined": int(
                    run_frame["retrieval_status"].eq("quarantined").sum()
                ),
                "bytes_available": int(
                    pd.to_numeric(run_frame["bytes"], errors="coerce")
                    .fillna(0)
                    .sum()
                ),
            }
        ]
    )
    runs_path = ROOT / "results" / "historical_collection_runs.csv"
    existing_runs = (
        pd.read_csv(runs_path, low_memory=False)
        if runs_path.exists()
        else pd.DataFrame(columns=run_summary.columns)
    )
    atomic_write_frame(
        runs_path,
        pd.concat([existing_runs, run_summary], ignore_index=True),
    )
    return combined_frames


def status_summary(seasons: Iterable[int]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for season in seasons:
        schedule = pd.read_csv(schedule_manifest_path(season), low_memory=False)
        manifest_path = feed_manifest_path(season)
        feeds = (
            pd.read_csv(manifest_path, low_memory=False)
            if manifest_path.exists()
            else initial_feed_manifest(schedule)
        )
        feed_eligible = feeds["feed_eligible"].astype(bool)
        validated = feeds["retrieval_status"].isin(
            [
                "reused_verified_cache",
                "downloaded",
                "refreshed_changed",
                "refreshed_unchanged",
            ]
        )
        rows.append(
            {
                "season": season,
                "split_role": BOUNDS[season][2],
                "scheduled_regular_season_game_pks": schedule["game_pk"].nunique(),
                "feed_eligible_completed_games": int(schedule["feed_eligible"].astype(bool).sum()),
                "completed_or_reused_feeds": int((feed_eligible & validated).sum()),
                "eligible_missing_or_not_attempted": int(
                    (
                        feed_eligible
                        & feeds["retrieval_status"].isin(["not_attempted", "failed"])
                    ).sum()
                ),
                "eligible_quarantined": int(
                    (feed_eligible & feeds["retrieval_status"].eq("quarantined")).sum()
                ),
                "excluded_schedule_games": int((~feed_eligible).sum()),
                "excluded_quarantined_responses": int(
                    ((~feed_eligible) & feeds["retrieval_status"].eq("quarantined")).sum()
                ),
                "bytes": int(pd.to_numeric(feeds["bytes"], errors="coerce").fillna(0).sum()),
            }
        )
    return pd.DataFrame(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    schedule_parser = subparsers.add_parser("schedules", help="Build schedule-only manifests")
    schedule_parser.add_argument(
        "--seasons", nargs="+", type=int, default=list(BOUNDS)
    )
    schedule_parser.add_argument("--refresh", action="store_true")

    subparsers.add_parser("pilot-manifest", help="Freeze the reproducible pilot selection")

    collect_parser = subparsers.add_parser("collect", help="Collect validated final feeds")
    collect_parser.add_argument(
        "--seasons", nargs="+", type=int, default=list(DEFAULT_DEVELOPMENT_SEASONS)
    )
    collect_parser.add_argument("--pilot", action="store_true")
    collect_parser.add_argument("--allow-test-data", action="store_true")
    collect_parser.add_argument("--refresh", action="store_true")
    collect_parser.add_argument("--pace-seconds", type=float, default=0.25)
    collect_parser.add_argument("--attempts", type=int, default=4)
    collect_parser.add_argument("--checkpoint-every", type=int, default=20)
    collect_parser.add_argument(
        "--retry-problems",
        action="store_true",
        help="Restrict collection to manifest rows not already in a validated status",
    )

    status_parser = subparsers.add_parser("status", help="Report collection status")
    status_parser.add_argument(
        "--seasons", nargs="+", type=int, default=list(DEFAULT_DEVELOPMENT_SEASONS)
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "schedules":
        run_schedules(args.seasons, refresh=args.refresh)
    elif args.command == "pilot-manifest":
        build_pilot_manifest()
    elif args.command == "collect":
        collect_feeds(
            args.seasons,
            pilot=args.pilot,
            allow_test_data=args.allow_test_data,
            refresh=args.refresh,
            pace_seconds=args.pace_seconds,
            attempts=args.attempts,
            checkpoint_every=args.checkpoint_every,
            retry_problems=args.retry_problems,
        )
    elif args.command == "status":
        summary = status_summary(args.seasons)
        atomic_write_frame(ROOT / "results" / "historical_collection_status.csv", summary)
        print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
