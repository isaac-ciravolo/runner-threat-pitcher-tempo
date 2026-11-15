"""Select and cache the fixed 2024 feasibility-audit sample.

Selection uses schedule metadata only.  It never inspects game outcomes, pitch
timing, runner events, or other live-feed content before games are selected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MANIFEST_PATH = ROOT / "data" / "audit_sample_manifest.csv"
LEDGER_PATH = ROOT / "data" / "audit_download_ledger.csv"
RAW_METADATA_PATH = RAW / "download_metadata.json"

SEED = 20241115
SELECTION_RULE_VERSION = "schedule-only-v1"
WINDOWS = (
    ("early", "2024-03-28", "2024-04-30"),
    ("middle", "2024-06-15", "2024-07-15"),
    ("late", "2024-09-01", "2024-09-29"),
)
GAMES_PER_WINDOW = 10
SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
FEED_URL_TEMPLATE = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def make_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.75,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers.update({"User-Agent": "runner-threat-pitcher-tempo-feasibility-audit/1.0"})
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def load_raw_metadata() -> dict[str, dict[str, Any]]:
    if not RAW_METADATA_PATH.exists():
        return {}
    return json.loads(RAW_METADATA_PATH.read_text(encoding="utf-8"))


def save_raw_metadata(metadata: dict[str, dict[str, Any]]) -> None:
    RAW_METADATA_PATH.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def fetch_json(
    session: requests.Session,
    url: str,
    destination: Path,
    raw_metadata: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return decoded JSON plus a download/cache ledger record."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    relative_path = destination.relative_to(ROOT).as_posix()

    if destination.exists():
        content = destination.read_bytes()
        digest = sha256_bytes(content)
        stored = raw_metadata.get(relative_path, {})
        record = {
            "source_url": url,
            "cache_path": relative_path,
            "retrieved_utc": stored.get("retrieved_utc", "unknown-cached-file"),
            "sha256": digest,
            "bytes": len(content),
            "http_status": stored.get("http_status", 200),
            "download_status": "cache_hit",
            "error": "",
        }
        return json.loads(content), record

    retrieved_utc = utc_now()
    response = session.get(url, timeout=(10, 45))
    response.raise_for_status()
    content = response.content
    payload = response.json()
    destination.write_bytes(content)
    digest = sha256_bytes(content)
    record = {
        "source_url": url,
        "cache_path": relative_path,
        "retrieved_utc": retrieved_utc,
        "sha256": digest,
        "bytes": len(content),
        "http_status": response.status_code,
        "download_status": "downloaded",
        "error": "",
    }
    raw_metadata[relative_path] = record.copy()
    save_raw_metadata(raw_metadata)
    return payload, record


def prepared_url(session: requests.Session, url: str, params: dict[str, Any]) -> str:
    request = requests.Request("GET", url, params=params)
    return session.prepare_request(request).url


def schedule_candidates(schedule: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for date_block in schedule.get("dates", []):
        for game in date_block.get("games", []):
            status = game.get("status", {})
            if game.get("gameType") != "R" or status.get("abstractGameState") != "Final":
                continue
            teams = game.get("teams", {})
            venue = game.get("venue", {})
            candidates.append(
                {
                    "game_pk": int(game["gamePk"]),
                    "official_date": game["officialDate"],
                    "game_date_utc": game.get("gameDate"),
                    "away_team_id": teams.get("away", {}).get("team", {}).get("id"),
                    "away_team": teams.get("away", {}).get("team", {}).get("name"),
                    "home_team_id": teams.get("home", {}).get("team", {}).get("id"),
                    "home_team": teams.get("home", {}).get("team", {}).get("name"),
                    "venue_id": venue.get("id"),
                    "venue": venue.get("name"),
                    "schedule_status": status.get("detailedState"),
                }
            )
    return sorted(candidates, key=lambda row: (row["official_date"], row["game_pk"]))


def select_sample(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for window_index, (period, start_date, end_date) in enumerate(WINDOWS):
        pool = [
            row.copy()
            for row in candidates
            if start_date <= row["official_date"] <= end_date
        ]
        random.Random(SEED + window_index).shuffle(pool)
        used_dates: set[str] = set()
        used_venues: set[int] = set()
        window_rows: list[dict[str, Any]] = []
        for row in pool:
            if row["official_date"] in used_dates or row["venue_id"] in used_venues:
                continue
            row.update(
                {
                    "period": period,
                    "window_start": start_date,
                    "window_end": end_date,
                    "seed": SEED,
                    "selection_rule_version": SELECTION_RULE_VERSION,
                    "selection_rationale": (
                        "Schedule-only seeded sample; one game per date and venue "
                        f"within the {period} window; no live-feed fields inspected."
                    ),
                }
            )
            window_rows.append(row)
            used_dates.add(row["official_date"])
            used_venues.add(row["venue_id"])
            if len(window_rows) == GAMES_PER_WINDOW:
                break
        if len(window_rows) != GAMES_PER_WINDOW:
            raise RuntimeError(
                f"Only {len(window_rows)} eligible games selected for {period}; "
                f"expected {GAMES_PER_WINDOW}."
            )
        selected.extend(window_rows)

    for selection_order, row in enumerate(selected, start=1):
        row["selection_order"] = selection_order
    return selected


def run() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    raw_metadata = load_raw_metadata()
    session = make_session()
    schedule_params = {
        "sportId": 1,
        "gameType": "R",
        "startDate": WINDOWS[0][1],
        "endDate": WINDOWS[-1][2],
        "hydrate": "team,venue",
    }
    schedule_url = prepared_url(session, SCHEDULE_URL, schedule_params)
    ledger_rows: list[dict[str, Any]] = []
    try:
        schedule, schedule_record = fetch_json(
            session,
            schedule_url,
            RAW / "schedule_2024_regular.json",
            raw_metadata,
        )
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        print(f"Schedule retrieval failed: {exc}", file=sys.stderr)
        return 1

    schedule_record.update({"record_type": "schedule", "game_pk": ""})
    ledger_rows.append(schedule_record)
    selected = select_sample(schedule_candidates(schedule))

    failures = 0
    for row in selected:
        game_pk = row["game_pk"]
        feed_url = FEED_URL_TEMPLATE.format(game_pk=game_pk)
        destination = RAW / f"game_{game_pk}.json"
        try:
            feed, record = fetch_json(session, feed_url, destination, raw_metadata)
            if int(feed.get("gamePk", -1)) != game_pk or "liveData" not in feed:
                raise ValueError("response is not the expected live game feed")
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            failures += 1
            record = {
                "source_url": feed_url,
                "cache_path": destination.relative_to(ROOT).as_posix(),
                "retrieved_utc": utc_now(),
                "sha256": "",
                "bytes": "",
                "http_status": "",
                "download_status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
        record.update({"record_type": "game_feed", "game_pk": game_pk})
        ledger_rows.append(record)
        row.update(
            {
                "feed_url": record["source_url"],
                "cache_path": record["cache_path"],
                "retrieved_utc": record["retrieved_utc"],
                "sha256": record["sha256"],
                "bytes": record["bytes"],
                "download_status": record["download_status"],
                "download_error": record["error"],
            }
        )

    manifest_columns = [
        "selection_order",
        "period",
        "window_start",
        "window_end",
        "seed",
        "selection_rule_version",
        "game_pk",
        "official_date",
        "game_date_utc",
        "away_team_id",
        "away_team",
        "home_team_id",
        "home_team",
        "venue_id",
        "venue",
        "schedule_status",
        "selection_rationale",
        "feed_url",
        "cache_path",
        "retrieved_utc",
        "sha256",
        "bytes",
        "download_status",
        "download_error",
    ]
    pd.DataFrame(selected)[manifest_columns].to_csv(MANIFEST_PATH, index=False)
    ledger_columns = [
        "record_type",
        "game_pk",
        "source_url",
        "cache_path",
        "retrieved_utc",
        "sha256",
        "bytes",
        "http_status",
        "download_status",
        "error",
    ]
    pd.DataFrame(ledger_rows)[ledger_columns].to_csv(LEDGER_PATH, index=False)
    print(
        f"Selected {len(selected)} games; "
        f"{len(selected) - failures} feeds available; {failures} failures."
    )
    print(f"Manifest: {MANIFEST_PATH.relative_to(ROOT)}")
    print(f"Download ledger: {LEDGER_PATH.relative_to(ROOT)}")
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    raise SystemExit(run())


if __name__ == "__main__":
    main()
