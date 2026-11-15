"""Fetch the frozen aggregate-tempo benchmark from public MLB sources."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw" / "tempo_benchmark"
PITCHERS_PATH = DATA / "tempo_benchmark_pitchers.csv"
MANIFEST_PATH = DATA / "tempo_benchmark_game_manifest.csv"
LEDGER_PATH = DATA / "tempo_benchmark_download_ledger.csv"
SOURCE_CHECKS_PATH = DATA / "tempo_benchmark_source_checks.csv"

SAVANT_URL = (
    "https://baseballsavant.mlb.com/leaderboard/pitch-tempo?"
    "game_type=Regular&n=1&season_end=2024&season_start=2024&"
    "sortColumn=median_seconds_empty&sortDirection=asc&split=no&team=&"
    "type=Pit&with_team_only=0"
)
SAVANT_CSV_URL = f"{SAVANT_URL}&csv=true"
GAME_LOG_URL = (
    "https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats?"
    "stats=gameLog&group=pitching&season=2024&gameType=R"
)
FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
DATA_RE = re.compile(r"data:\s*(\[.*?\]),\s*leagueAverageData:", re.DOTALL)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def make_session() -> requests.Session:
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=0.75,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers.update({"User-Agent": "runner-threat-tempo-benchmark/1.0"})
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def fetch_cached(
    session: requests.Session,
    url: str,
    destination: Path,
) -> tuple[bytes, dict[str, Any]]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        content = destination.read_bytes()
        status = "cache_hit"
        retrieved = datetime.fromtimestamp(
            destination.stat().st_mtime, tz=timezone.utc
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        http_status: int | str = 200
    else:
        response = session.get(url, timeout=(10, 60))
        response.raise_for_status()
        content = response.content
        destination.write_bytes(content)
        status = "downloaded"
        retrieved = utc_now()
        http_status = response.status_code
    return content, {
        "source_url": url,
        "cache_path": destination.relative_to(ROOT).as_posix(),
        "retrieved_utc": retrieved,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "http_status": http_status,
        "download_status": status,
        "error": "",
    }


def parse_savant_data(html: bytes) -> list[dict[str, Any]]:
    text = html.decode("utf-8-sig")
    match = DATA_RE.search(text)
    if not match:
        raise ValueError("Could not locate tempoServerVals.data in Savant HTML")
    data = json.loads(match.group(1))
    if not isinstance(data, list) or not data:
        raise ValueError("Savant embedded leaderboard data is empty")
    return data


def validate_frozen_selection(rows: list[dict[str, Any]], frozen: pd.DataFrame) -> None:
    pool = sorted(
        (
            row
            for row in rows
            if int(row.get("is_qualified", 0)) == 1
            and int(row.get("tot_n_empty", 0)) >= 500
            and int(row.get("tot_n_onbase", 0)) >= 250
        ),
        key=lambda row: (float(row["median_seconds_empty"]), int(row["entity_id"])),
    )
    positions = [round(index * (len(pool) - 1) / 5) for index in range(6)]
    selected = [pool[position] for position in positions]
    selected_ids = [int(row["entity_id"]) for row in selected]
    frozen_ids = frozen.sort_values("selection_position")["entity_id"].astype(int).tolist()
    if len(pool) != 111 or positions != [0, 22, 44, 66, 88, 110]:
        raise ValueError(
            f"Savant selection population changed: pool={len(pool)}, positions={positions}"
        )
    if selected_ids != frozen_ids:
        raise ValueError(
            f"Frozen pitcher IDs do not match current embedded data: {selected_ids} != {frozen_ids}"
        )
    lookup = {int(row["entity_id"]): row for row in selected}
    for frozen_row in frozen.itertuples(index=False):
        current = lookup[int(frozen_row.entity_id)]
        checks = {
            "savant_empty_count": int(current["tot_n_empty"]),
            "savant_onbase_count": int(current["tot_n_onbase"]),
            "savant_empty_median_seconds": float(current["median_seconds_empty"]),
            "savant_onbase_median_seconds": float(current["median_seconds_onbase"]),
        }
        for field, observed in checks.items():
            expected = getattr(frozen_row, field)
            if abs(float(expected) - float(observed)) > 1e-9:
                raise ValueError(
                    f"Frozen Savant value changed for {frozen_row.entity_id} {field}: "
                    f"{expected} != {observed}"
                )


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    frozen = pd.read_csv(PITCHERS_PATH)
    session = make_session()
    ledger: list[dict[str, Any]] = []

    html, record = fetch_cached(session, SAVANT_URL, RAW / "savant_pitch_tempo_2024.html")
    record["source_type"] = "savant_leaderboard_html"
    ledger.append(record)
    csv_bytes, record = fetch_cached(
        session, SAVANT_CSV_URL, RAW / "savant_pitch_tempo_2024.csv"
    )
    record["source_type"] = "savant_leaderboard_csv"
    ledger.append(record)

    savant_rows = parse_savant_data(html)
    validate_frozen_selection(savant_rows, frozen)

    csv_rows = list(csv.reader(csv_bytes.decode("utf-8-sig").splitlines()))
    csv_header = csv_rows[0] if csv_rows else []
    duplicate_headers = sorted({name for name in csv_header if csv_header.count(name) > 1})
    first_csv = csv_rows[1] if len(csv_rows) > 1 else []
    csv_onbase_repeats_empty = bool(
        len(first_csv) > 9 and first_csv[7] == first_csv[9]
    )
    qualified = [row for row in savant_rows if int(row.get("is_qualified", 0)) == 1]
    unqualified = [row for row in savant_rows if int(row.get("is_qualified", 0)) == 0]
    source_checks = pd.DataFrame(
        [
            {
                "checked_utc": utc_now(),
                "season": 2024,
                "embedded_rows": len(savant_rows),
                "selection_pool_rows": 111,
                "qualified_rows": len(qualified),
                "observed_minimum_qualified_total": min(
                    int(row["tot_n"]) for row in qualified
                ),
                "observed_maximum_unqualified_total": max(
                    int(row["tot_n"]) for row in unqualified
                ),
                "csv_data_rows": max(0, len(csv_rows) - 1),
                "csv_duplicate_headers": " | ".join(duplicate_headers),
                "csv_first_row_onbase_value_repeats_empty": csv_onbase_repeats_empty,
                "visible_rounding_decimals": 1,
                "embedded_median_decimals": 3,
                "notes": (
                    "Embedded tempoServerVals.data used for benchmark; CSV retained only to "
                    "document the duplicate-header and runners-on-column defect."
                ),
            }
        ]
    )
    source_checks.to_csv(SOURCE_CHECKS_PATH, index=False)

    games_to_pitchers: dict[int, set[int]] = defaultdict(set)
    game_dates: dict[int, str] = {}
    for pitcher in frozen.sort_values("selection_position").itertuples(index=False):
        url = GAME_LOG_URL.format(pitcher_id=int(pitcher.entity_id))
        content, record = fetch_cached(
            session, url, RAW / f"pitcher_{int(pitcher.entity_id)}_gamelog.json"
        )
        record["source_type"] = "mlb_pitcher_game_log"
        ledger.append(record)
        payload = json.loads(content)
        stats = payload.get("stats", [])
        splits = stats[0].get("splits", []) if stats else []
        if not splits:
            raise ValueError(f"No 2024 regular-season game log for {pitcher.entity_id}")
        for split in splits:
            game_pk = int(split["game"]["gamePk"])
            games_to_pitchers[game_pk].add(int(pitcher.entity_id))
            game_dates[game_pk] = str(split.get("date") or "")

    manifest_rows: list[dict[str, Any]] = []
    sorted_games = sorted(games_to_pitchers, key=lambda game: (game_dates[game], game))
    for selection_order, game_pk in enumerate(sorted_games, start=1):
        url = FEED_URL.format(game_pk=game_pk)
        destination = RAW / f"game_{game_pk}.json"
        try:
            content, record = fetch_cached(session, url, destination)
            payload = json.loads(content)
        except (requests.RequestException, json.JSONDecodeError, OSError) as exc:
            record = {
                "source_url": url,
                "cache_path": destination.relative_to(ROOT).as_posix(),
                "retrieved_utc": utc_now(),
                "sha256": "",
                "bytes": "",
                "http_status": "",
                "download_status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
            payload = {}
        record["source_type"] = "mlb_live_game_feed"
        ledger.append(record)
        if not payload:
            continue
        game_data = payload.get("gameData", {})
        game = game_data.get("game", {})
        if game.get("type") != "R":
            raise ValueError(f"Game {game_pk} is not regular season: {game.get('type')}")
        teams = game_data.get("teams", {})
        venue = game_data.get("venue", {})
        status = game_data.get("status", {})
        manifest_rows.append(
            {
                "selection_order": selection_order,
                "period": "tempo_benchmark_2024",
                "game_pk": game_pk,
                "official_date": game_data.get("datetime", {}).get("officialDate"),
                "game_date_utc": game_data.get("datetime", {}).get("dateTime"),
                "away_team_id": teams.get("away", {}).get("id"),
                "away_team": teams.get("away", {}).get("name"),
                "home_team_id": teams.get("home", {}).get("id"),
                "home_team": teams.get("home", {}).get("name"),
                "venue_id": venue.get("id"),
                "venue": venue.get("name"),
                "game_type": game.get("type"),
                "schedule_status": status.get("detailedState"),
                "selected_pitcher_ids": "|".join(
                    str(value) for value in sorted(games_to_pitchers[game_pk])
                ),
                "feed_url": url,
                "cache_path": destination.relative_to(ROOT).as_posix(),
                "retrieved_utc": record["retrieved_utc"],
                "sha256": record["sha256"],
                "bytes": record["bytes"],
                "download_status": record["download_status"],
                "download_error": record["error"],
            }
        )
        if selection_order % 20 == 0 or selection_order == len(sorted_games):
            print(f"Processed {selection_order}/{len(sorted_games)} benchmark game feeds.", flush=True)

    ledger_frame = pd.DataFrame(ledger)
    ledger_frame = ledger_frame[
        [
            "source_type", "source_url", "cache_path", "retrieved_utc", "sha256",
            "bytes", "http_status", "download_status", "error",
        ]
    ]
    ledger_frame.to_csv(LEDGER_PATH, index=False)
    manifest = pd.DataFrame(manifest_rows).sort_values("selection_order")
    manifest.to_csv(MANIFEST_PATH, index=False)

    failures = ledger_frame["download_status"].eq("failed").sum()
    if failures:
        raise SystemExit(f"Benchmark retrieval has {failures} failed downloads.")
    print(
        f"Verified 6 frozen Savant pitchers and cached {len(manifest)} unique regular-season games.",
        flush=True,
    )


if __name__ == "__main__":
    main()
