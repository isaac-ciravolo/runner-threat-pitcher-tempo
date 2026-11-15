import unittest

import pandas as pd

from scripts.audit_feeds import _apply_movements, build_intervals, extract_events


def movement(runner_id, start, end, *, is_out=False, out_number=None, play_index=0):
    return {
        "movement": {
            "originBase": start,
            "start": start,
            "end": end,
            "outBase": None,
            "isOut": is_out,
            "outNumber": out_number,
        },
        "details": {
            "runner": {"id": runner_id, "fullName": str(runner_id)},
            "eventType": "test",
            "playIndex": play_index,
        },
    }


class RunnerStateTests(unittest.TestCase):
    def test_multisegment_runner_path_is_collapsed(self):
        bases = {"1B": 10, "2B": 20}
        movements = [
            movement(30, None, "2B"),
            movement(10, "1B", "3B"),
            movement(10, "3B", "score"),
            movement(20, "2B", "score"),
        ]

        observed, anomalies = _apply_movements(bases, movements)

        self.assertEqual(observed, {"2B": 30})
        self.assertEqual(anomalies, [])

    def test_runner_placement_and_intervening_stepoff_are_preserved(self):
        manifest_row = pd.Series(
            {
                "selection_order": 1,
                "period": "test",
                "official_date": "2024-07-01",
                "away_team": "Away",
                "home_team": "Home",
                "venue": "Park",
            }
        )
        feed = {
            "gamePk": 1,
            "liveData": {
                "plays": {
                    "allPlays": [
                        {
                            "about": {
                                "atBatIndex": 0,
                                "inning": 10,
                                "halfInning": "top",
                                "isComplete": True,
                                "startTime": "2024-07-01T00:00:00.000Z",
                                "endTime": "2024-07-01T00:00:30.000Z",
                            },
                            "matchup": {
                                "pitcher": {"id": 1, "fullName": "Pitcher"},
                                "batter": {"id": 2, "fullName": "Batter"},
                                "splits": {"menOnBase": "RISP"},
                            },
                            "result": {
                                "eventType": "test",
                                "awayScore": 0,
                                "homeScore": 0,
                            },
                            "runners": [],
                            "playEvents": [
                                {
                                    "index": 0,
                                    "type": "action",
                                    "isPitch": False,
                                    "base": 2,
                                    "player": {"id": 99},
                                    "details": {
                                        "eventType": "runner_placed",
                                        "event": "Runner Placed On Base",
                                        "description": "Runner starts inning at 2nd base.",
                                    },
                                    "count": {"balls": 0, "strikes": 0, "outs": 0},
                                    "startTime": "2024-07-01T00:00:00.000Z",
                                    "endTime": "2024-07-01T00:00:01.000Z",
                                },
                                {
                                    "index": 1,
                                    "type": "pitch",
                                    "isPitch": True,
                                    "playId": "p1",
                                    "details": {"call": {"code": "B", "description": "Ball"}},
                                    "count": {"balls": 1, "strikes": 0, "outs": 0},
                                    "startTime": "2024-07-01T00:00:05.000Z",
                                    "endTime": "2024-07-01T00:00:06.000Z",
                                },
                                {
                                    "index": 2,
                                    "type": "stepoff",
                                    "isPitch": False,
                                    "details": {"description": "Step Off"},
                                    "count": {"balls": 1, "strikes": 0, "outs": 0},
                                    "startTime": "2024-07-01T00:00:10.000Z",
                                    "endTime": "2024-07-01T00:00:11.000Z",
                                },
                                {
                                    "index": 3,
                                    "type": "pitch",
                                    "isPitch": True,
                                    "playId": "p2",
                                    "details": {"call": {"code": "C", "description": "Called Strike"}},
                                    "count": {"balls": 1, "strikes": 1, "outs": 0},
                                    "startTime": "2024-07-01T00:00:25.000Z",
                                    "endTime": "2024-07-01T00:00:26.000Z",
                                },
                            ],
                        }
                    ]
                }
            },
        }

        events, states = extract_events([(manifest_row, feed)])
        intervals = build_intervals(events)

        self.assertEqual(events.loc[events.event_index.eq(0), "bases_after"].iloc[0], "2B")
        self.assertEqual(events.loc[events.event_index.eq(1), "bases_before"].iloc[0], "2B")
        self.assertTrue(states["matchup_matches_end"].iloc[0])
        self.assertEqual(intervals["event_start_interval_seconds"].iloc[0], 20.0)
        self.assertTrue(intervals["step_off_flag"].iloc[0])
        self.assertEqual(intervals["intervening_action_count"].iloc[0], 1)


if __name__ == "__main__":
    unittest.main()
