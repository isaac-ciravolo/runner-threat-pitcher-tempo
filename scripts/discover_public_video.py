"""Search MLB public game-content metadata for continuous-footage candidates."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "video_content"
DATA = ROOT / "data"
CONTENT_URL = "https://statsapi.mlb.com/api/v1/game/{game_pk}/content"
CONTINUOUS_RE = re.compile(
    r"\b(full|entire|complete)\b.*\b(inning|at[- ]?bat|game)\b", re.IGNORECASE
)
INNING_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+inning\b", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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
    session.headers.update({"User-Agent": "runner-threat-video-validation/1.0"})
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def duration_seconds(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    parts = value.split(":")
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return None
    if len(numbers) == 3:
        return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    return None


def video_items(payload: Any) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            playbacks = value.get("playbacks")
            item_id = value.get("id") or value.get("guid")
            if item_id and isinstance(playbacks, list) and playbacks:
                found[str(item_id)] = value
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload)
    return list(found.values())


def preferred_playback(item: dict[str, Any]) -> str:
    playbacks = item.get("playbacks", [])
    for name in ("highBit", "mp4Avc", "hlsCloud", "HTTP_CLOUD_WIRED"):
        for playback in playbacks:
            if playback.get("name") == name and playback.get("url"):
                return playback["url"]
    return next((playback.get("url", "") for playback in playbacks), "")


def main() -> None:
    candidates = pd.read_csv(DATA / "video_validation_candidates.csv")
    availability = pd.read_csv(DATA / "video_availability_log.csv", keep_default_na=False)
    for column in ("search_method", "search_reviewer"):
        if column not in availability:
            availability[column] = ""
    RAW.mkdir(parents=True, exist_ok=True)
    session = make_session()
    access_time = utc_now()
    source_rows: list[dict[str, Any]] = []
    ledger_rows: list[dict[str, Any]] = []
    archives: dict[int, dict[str, Any]] = {}
    failures = 0

    for game_pk in sorted(candidates["game_pk"].unique()):
        url = CONTENT_URL.format(game_pk=int(game_pk))
        path = RAW / f"game_{int(game_pk)}.json"
        try:
            if path.exists():
                content = path.read_bytes()
                status = "cache_hit"
                retrieved = datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).isoformat(timespec="seconds").replace("+00:00", "Z")
                http_status = 200
            else:
                response = session.get(url, timeout=(10, 45))
                response.raise_for_status()
                content = response.content
                path.write_bytes(content)
                status = "downloaded"
                retrieved = utc_now()
                http_status = response.status_code
            payload = json.loads(content)
            error = ""
        except (requests.RequestException, json.JSONDecodeError, OSError) as exc:
            failures += 1
            content = b""
            payload = {}
            status = "failed"
            retrieved = utc_now()
            http_status = ""
            error = f"{type(exc).__name__}: {exc}"

        mlbtv_items = []
        for epg in payload.get("media", {}).get("epg", []):
            if epg.get("title") == "MLBTV":
                mlbtv_items.extend(epg.get("items", []))
        archives[int(game_pk)] = {
            "available": bool(mlbtv_items),
            "free_game": any(bool(item.get("freeGame")) for item in mlbtv_items),
            "feeds": " | ".join(
                sorted(
                    {
                        str(item.get("callLetters") or item.get("mediaFeedType") or "unknown")
                        for item in mlbtv_items
                    }
                )
            ),
        }

        ledger_rows.append(
            {
                "game_pk": int(game_pk),
                "source_url": url,
                "cache_path": path.relative_to(ROOT).as_posix(),
                "retrieved_utc": retrieved,
                "sha256": hashlib.sha256(content).hexdigest() if content else "",
                "bytes": len(content) if content else "",
                "http_status": http_status,
                "download_status": status,
                "error": error,
            }
        )

        for item in video_items(payload):
            title = str(item.get("title") or "")
            continuous_candidate = bool(CONTINUOUS_RE.search(title))
            inning_match = INNING_RE.search(title)
            inning = int(inning_match.group(1)) if inning_match else None
            item_id = item.get("id") or item.get("guid")
            page_url = f"https://www.mlb.com/video/{item_id}" if item_id else ""
            source_rows.append(
                {
                    "game_pk": int(game_pk),
                    "title": title,
                    "duration": item.get("duration"),
                    "duration_seconds": duration_seconds(item.get("duration")),
                    "public_page_url": page_url,
                    "playback_url": preferred_playback(item),
                    "continuous_candidate": continuous_candidate,
                    "parsed_inning": inning,
                    "description": item.get("description") or "",
                    "access_date_utc": access_time,
                    "continuity_status": "unverified_candidate" if continuous_candidate else "not_applicable",
                    "notes": (
                        "Title suggests continuous footage; verify half-inning, edits, audio/timecode, "
                        "and both releases manually."
                        if continuous_candidate
                        else "Highlight metadata only; not treated as continuous timing evidence."
                    ),
                }
            )

    sources = pd.DataFrame(source_rows).drop_duplicates(
        ["game_pk", "public_page_url", "title"]
    )
    continuous = sources.loc[sources["continuous_candidate"]].copy()
    continuous.to_csv(DATA / "public_video_source_candidates.csv", index=False)
    pd.DataFrame(ledger_rows).to_csv(DATA / "video_content_download_ledger.csv", index=False)

    for index, row in availability.iterrows():
        if str(row.get("search_method", "")).strip().lower() == "manual":
            continue
        matches = continuous.loc[
            continuous["game_pk"].eq(int(row["game_pk"]))
            & continuous["parsed_inning"].eq(int(candidates.loc[
                candidates["validation_id"].eq(row["validation_id"]), "inning"
            ].iloc[0]))
        ]
        if not matches.empty:
            source = matches.iloc[0]
            availability.loc[index, "search_status"] = "located_continuity_unverified"
            availability.loc[index, "video_source"] = f"MLB: {source['title']}"
            availability.loc[index, "video_url"] = source["public_page_url"]
            availability.loc[index, "access_date_utc"] = access_time
            availability.loc[index, "continuity_status"] = "unverified_candidate"
            availability.loc[index, "search_method"] = "automated_metadata"
            availability.loc[index, "search_notes"] = source["notes"]
        else:
            archive = archives.get(int(row["game_pk"]), {})
            availability.loc[index, "access_date_utc"] = access_time
            availability.loc[index, "search_method"] = "automated_metadata"
            if archive.get("available") and not archive.get("free_game"):
                availability.loc[index, "search_status"] = "inaccessible"
                availability.loc[index, "video_source"] = (
                    f"MLB.TV archived broadcast ({archive.get('feeds', 'feed')})"
                )
                availability.loc[index, "video_url"] = (
                    f"https://www.mlb.com/tv/g{int(row['game_pk'])}"
                )
                availability.loc[index, "continuity_status"] = "not_inspected"
                availability.loc[index, "search_notes"] = (
                    "Full-game archive metadata is present with freeGame=false; no same-inning "
                    "continuous public clip was found in MLB game-content metadata. Film Room "
                    "and other public sources still require manual search."
                )
            else:
                availability.loc[index, "search_status"] = "not_found"
                availability.loc[index, "search_notes"] = (
                    "No same-inning continuous candidate found in MLB game-content metadata. "
                    "Film Room, MLB page search, and other public sources still require manual search."
                )
    availability.to_csv(DATA / "video_availability_log.csv", index=False)

    print(
        f"Searched {candidates['game_pk'].nunique()} game-content endpoints; "
        f"{failures} failures; {len(continuous)} continuous-title candidates found."
    )
    print(
        "Frozen interval matches needing continuity review:",
        int(availability["search_status"].eq("located_continuity_unverified").sum()),
    )
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
