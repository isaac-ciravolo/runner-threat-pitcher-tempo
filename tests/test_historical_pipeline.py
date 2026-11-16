import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.historical_collection import (
    atomic_write_bytes,
    classify_schedule_status,
    parse_schedule,
    update_manifest_record,
    validate_final_feed,
)
from scripts.historical_processing import (
    ForwardHistoryState,
    build_catcher_timeline,
    catcher_at_open,
    rule_regime,
    parse_utc_mixed,
    starting_catcher,
    validate_requested_seasons,
)


def final_feed_bytes(game_pk=1):
    payload = {
        "gamePk": game_pk,
        "gameData": {
            "game": {"type": "R"},
            "status": {"abstractGameState": "Final", "detailedState": "Final"},
            "datetime": {"dateTime": "2024-04-01T17:00:00Z"},
        },
        "liveData": {
            "boxscore": {"teams": {"away": {}, "home": {}}},
            "plays": {
                "allPlays": [
                    {
                        "about": {
                            "isComplete": True,
                            "endTime": "2024-04-01T20:00:00Z",
                        },
                        "playEvents": [
                            {"endTime": "2024-04-01T19:59:59Z"}
                        ],
                    }
                ]
            },
        },
    }
    return json.dumps(payload).encode()


def history_frame(attempt=False):
    return pd.DataFrame(
        [
            {
                "runner_id": 10,
                "attempt_history_eligible": True,
                "recorded_steal_attempt_indicator": attempt,
                "recorded_steal_attempt_record_count": int(attempt),
                "recorded_steal_success_count": 0,
                "recorded_steal_unsuccessful_count": int(attempt),
                "recorded_steal_ambiguous_count": 0,
            }
        ]
    )


class HistoricalCollectionTests(unittest.TestCase):
    def test_detailed_cancellation_overrides_abstract_final(self):
        game = {
            "status": {
                "abstractGameState": "Final",
                "detailedState": "Cancelled",
                "reason": "Rain",
            }
        }

        self.assertEqual(classify_schedule_status(game), "canceled")

    def test_atomic_cache_ignores_interrupted_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "current.json"
            valid = final_feed_bytes()
            atomic_write_bytes(target, valid)
            interrupted = target.with_name(".current.json.999.tmp")
            interrupted.write_bytes(b"partial")

            observed = target.read_bytes()
            is_valid, reason, metadata = validate_final_feed(observed, 1)

            self.assertTrue(is_valid, reason)
            self.assertEqual(metadata["feed_play_count"], 1)
            self.assertEqual(interrupted.read_bytes(), b"partial")

    def test_feed_validation_rejects_wrong_game_and_nonfinal(self):
        is_valid, reason, _ = validate_final_feed(final_feed_bytes(2), 1)
        self.assertFalse(is_valid)
        self.assertEqual(reason, "game_pk_mismatch")

        payload = json.loads(final_feed_bytes())
        payload["gameData"]["status"]["abstractGameState"] = "Live"
        is_valid, reason, _ = validate_final_feed(json.dumps(payload).encode(), 1)
        self.assertFalse(is_valid)
        self.assertTrue(reason.startswith("feed_not_final"))

    def test_final_feed_accepts_trailing_incomplete_rain_play(self):
        payload = json.loads(final_feed_bytes())
        payload["liveData"]["plays"]["allPlays"].append(
            {
                "about": {
                    "isComplete": False,
                    "endTime": "2024-04-01T20:05:00Z",
                },
                "playEvents": [
                    {
                        "isPitch": True,
                        "endTime": "2024-04-01T20:04:00Z",
                    },
                    {
                        "isPitch": False,
                        "endTime": "2024-04-01T20:05:00Z",
                        "details": {"eventType": "game_advisory"},
                    },
                ],
            }
        )

        is_valid, reason, metadata = validate_final_feed(
            json.dumps(payload).encode(), 1
        )

        self.assertTrue(is_valid, reason)
        self.assertEqual(metadata["feed_trailing_incomplete_play_count"], 1)
        self.assertEqual(metadata["feed_trailing_incomplete_pitch_count"], 1)

    def test_schedule_deduplicates_game_pk_and_preserves_status_evidence(self):
        base = {
            "gamePk": 7,
            "gameType": "R",
            "officialDate": "2024-04-01",
            "gameDate": "2024-04-01T17:00:00Z",
            "teams": {
                "away": {"team": {"id": 1, "name": "A"}},
                "home": {"team": {"id": 2, "name": "B"}},
            },
            "venue": {"id": 3, "name": "Park"},
        }
        postponed = {
            **base,
            "status": {
                "abstractGameState": "Preview",
                "detailedState": "Postponed",
            },
        }
        final = {
            **base,
            "gameDate": "2024-04-02T17:00:00Z",
            "rescheduledFromDate": "2024-04-01",
            "status": {
                "abstractGameState": "Final",
                "detailedState": "Final",
            },
        }
        payload = {
            "dates": [
                {"date": "2024-04-01", "games": [postponed]},
                {"date": "2024-04-02", "games": [final]},
            ]
        }

        manifest = parse_schedule(payload, 2024, "https://example.test")

        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest.iloc[0]["status_class"], "rescheduled_completed")
        self.assertEqual(manifest.iloc[0]["schedule_occurrence_count"], 2)
        self.assertIn("postponed", manifest.iloc[0]["status_classes_seen"])

    def test_test_year_requires_explicit_flag(self):
        with self.assertRaises(ValueError):
            validate_requested_seasons([2024, 2025])
        self.assertEqual(
            validate_requested_seasons([2025], allow_test_data=True),
            (2025,),
        )

    def test_reloaded_empty_text_column_accepts_restart_update(self):
        manifest = pd.DataFrame(
            {"game_pk": [1], "error": [float("nan")]}
        ).set_index("game_pk", drop=False)

        update_manifest_record(manifest, 1, {"error": "", "cache_source": "cache"})

        self.assertEqual(manifest.at[1, "error"], "")
        self.assertEqual(manifest.at[1, "cache_source"], "cache")


class CatcherAndHistoryTests(unittest.TestCase):
    def test_mixed_timestamp_precision_preserves_chronology(self):
        parsed = parse_utc_mixed(
            pd.Series(
                [
                    "2024-05-06T22:29:53+00:00",
                    "2024-05-07T01:02:03.456000+00:00",
                ]
            )
        )

        self.assertTrue(parsed.notna().all())
        self.assertLess(parsed.iloc[0], parsed.iloc[1])

    def test_starting_catcher_ignores_final_position_field(self):
        feed = {
            "gameData": {"players": {}},
            "liveData": {
                "boxscore": {
                    "teams": {
                        "home": {
                            "players": {
                                "ID10": {
                                    "person": {"id": 10, "fullName": "True Starter"},
                                    "battingOrder": "100",
                                    "position": {"code": "3"},
                                    "allPositions": [{"code": "2"}, {"code": "3"}],
                                },
                                "ID20": {
                                    "person": {"id": 20, "fullName": "Final Catcher"},
                                    "battingOrder": "200",
                                    "position": {"code": "2"},
                                    "allPositions": [{"code": "3"}],
                                },
                            }
                        },
                        "away": {"players": {}},
                    }
                }
            },
        }
        events = pd.DataFrame(
            columns=[
                "half_inning",
                "action_position_code",
                "is_substitution",
                "event_type",
                "action_player_id",
            ]
        )

        catcher_id, _name, method, _confidence = starting_catcher(
            feed, "home", events
        )

        self.assertEqual(catcher_id, 10)
        self.assertEqual(
            method, "unique_starting_batting_order_catcher_position_history"
        )

    def test_chronological_catcher_substitution(self):
        feed = {
            "gameData": {
                "players": {
                    "ID10": {"id": 10, "fullName": "Starter"},
                    "ID20": {"id": 20, "fullName": "Replacement"},
                    "ID30": {"id": 30, "fullName": "Away Catcher"},
                }
            },
            "liveData": {
                "boxscore": {
                    "teams": {
                        "home": {
                            "players": {
                                "ID10": {
                                    "person": {"id": 10, "fullName": "Starter"},
                                    "battingOrder": "100",
                                    "position": {"code": "2"},
                                    "allPositions": [{"code": "2"}],
                                }
                            }
                        },
                        "away": {
                            "players": {
                                "ID30": {
                                    "person": {"id": 30, "fullName": "Away Catcher"},
                                    "battingOrder": "100",
                                    "position": {"code": "2"},
                                    "allPositions": [{"code": "2"}],
                                }
                            }
                        },
                    }
                }
            },
        }
        events = pd.DataFrame(
            [
                {
                    "game_sequence": 5,
                    "half_inning": "top",
                    "action_position_code": "2",
                    "is_substitution": True,
                    "event_type": "defensive_substitution",
                    "action_player_id": 20,
                    "event_key": "1:3:0",
                }
            ]
        )

        timeline = build_catcher_timeline(feed, events)
        before = catcher_at_open(timeline, "top", 4)
        after = catcher_at_open(timeline, "top", 5)

        self.assertEqual(before["opening_catcher_id"], 10)
        self.assertEqual(after["opening_catcher_id"], 20)
        self.assertEqual(
            after["opening_catcher_assignment_method"],
            "ordered_defensive_substitution_or_switch",
        )

    def test_same_day_and_suspended_completion_cutoff(self):
        state = ForwardHistoryState()
        frame = history_frame(attempt=True)
        state.queue_game(
            season=2023,
            completion_time=pd.Timestamp("2023-04-01T18:00:00Z"),
            frame=frame,
        )

        state.release_completed_before(pd.Timestamp("2023-04-01T17:00:00Z"))
        before_completion = state.snapshot(10, coverage_complete=True)
        state.release_completed_before(pd.Timestamp("2023-04-01T19:00:00Z"))
        after_completion = state.snapshot(10, coverage_complete=True)

        self.assertEqual(
            before_completion["runner_prior_all_regimes_eligible_opportunities"],
            0,
        )
        self.assertEqual(
            after_completion["runner_prior_all_regimes_eligible_opportunities"],
            1,
        )
        self.assertEqual(
            after_completion["runner_prior_post_2023_attempted_opportunities"],
            1,
        )

    def test_missing_history_differs_from_zero_and_no_exposure(self):
        state = ForwardHistoryState()
        no_exposure = state.snapshot(99, coverage_complete=True)
        missing = state.snapshot(99, coverage_complete=False)
        state.queue_game(
            season=2022,
            completion_time=pd.Timestamp("2022-04-08T02:00:00Z"),
            frame=history_frame(attempt=False),
        )
        state.release_completed_before(pd.Timestamp("2022-04-09T00:00:00Z"))
        observed_zero = state.snapshot(10, coverage_complete=True)

        self.assertEqual(no_exposure["runner_history_status"], "no_prior_eligible_exposure")
        self.assertEqual(
            missing["runner_history_status"],
            "missing_or_incomplete_historical_coverage",
        )
        self.assertEqual(
            observed_zero["runner_history_status"],
            "observed_zero_attempts_with_positive_exposure",
        )

    def test_rule_environment_is_season_specific(self):
        self.assertEqual(rule_regime(2022), "pre_2023_no_disengagement_limit")
        self.assertEqual(
            rule_regime(2023),
            "post_2023_two_disengagement_limit_with_advance_reset",
        )


if __name__ == "__main__":
    unittest.main()
