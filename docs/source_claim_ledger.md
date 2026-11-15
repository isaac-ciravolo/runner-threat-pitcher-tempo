# Source and claim ledger

Checked 2026-11-15. This ledger covers the feasibility audit only. It does not establish an originality claim; the literature review remains pending.

| Source | Claim used in this audit | Evidence type | Limitation / boundary |
|---|---|---|---|
| [MLB schedule endpoint](https://statsapi.mlb.com/api/v1/schedule?sportId=1&gameType=R&startDate=2024-03-28&endDate=2024-09-29&hydrate=team%2Cvenue) | Returned 2024 MLB regular-season schedule metadata without authentication on 2026-11-15; used only for sample selection. | Direct HTTP 200 response, cached and checksummed. | MLB publishes response copyright text but no stability guarantee was located in the sources checked. |
| [MLB live game feed pattern](https://statsapi.mlb.com/api/v1.1/game/746572/feed/live) | `GET /api/v1.1/game/{gamePk}/feed/live` returned completed-game metadata and play-by-play without authentication on 2026-11-15. | Direct HTTP 200 response for all 30 selected games; source URLs, retrieval times, and SHA-256 values are in `data/audit_download_ledger.csv`. | Endpoint availability does not document field semantics or future compatibility. Raw responses must be cached. |
| [MLB-StatsAPI endpoint catalog](https://github.com/toddrob99/MLB-StatsAPI/wiki/Endpoints) | Independently cross-checks the live-feed URL pattern and default `v1.1` version. | Unofficial, open-source endpoint catalog. | Not MLB documentation and not authority for timestamp meaning. |
| Cached `playEvents.startTime` and `endTime` fields | Values are formatted with three fractional-second digits in all 10,156 audited events. | Automated structural observation. | Millisecond formatting is not demonstrated measurement precision. No checked source defines `startTime` as ball release. |
| Cached runner movements and `matchup.splits.menOnBase` | In this sample, `menOnBase` matches the reconstructed plate-appearance end bucket for all 2,283 plays, not a reliably frozen pre-action state. | Automated reconstruction plus consistency check. | Sample-specific observation; do not generalize without additional seasons/schema checks. |
| [MLB Film Room launch description](https://www.mlb.com/news/mlb-film-room-launch) and [current Film Room](https://www.mlb.com/video) | MLB states that Film Room includes every MLB pitch since 2017 and provides searchable clips, making it a candidate manual-video source. | MLB article and current public search page. | Search is dynamically rendered; clip boundaries, frame stepping, and continuous pre-pitch coverage require manual testing. Availability can change. |
| [MLB.TV archived-games help](https://www.mlb.com/live-stream-games/help-center/subscription-access-how-to-watch-mlbtv-on-android-mobile-devices) | MLB.TV provides archived games to subscribers. | MLB help documentation. | Subscription/login and blackout/access constraints make it unsuitable as the only reproducible public validation source. |
| [MLB Game Story for game 746655](https://www.mlb.com/stories/game/746655) | Publicly corroborates Tanner Bibee's pickoff of Dominic Fletcher, the audited opportunity that ended without another pitch. | Indexed MLB Game Story. | Game Stories are selective highlights, not a complete pitch-level record or timing source. |

## Claims deliberately not made

- The feed timestamps are not called release times.
- Recorded interruption labels are not assumed complete.
- Official steals and caught stealing are not treated as every runner decision or attempt.
- The audit does not establish novelty, causal effects, or pitcher-strategy recommendations.
