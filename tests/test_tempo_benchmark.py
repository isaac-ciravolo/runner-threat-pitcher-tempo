import unittest

import pandas as pd

from scripts.tempo_benchmark import build_tempo_pairs, summarize_measure


def event_frame():
    base = {
        "game_pk": 1,
        "official_date": "2024-04-01",
        "at_bat_index": 2,
        "pitcher_id": 10,
        "pitcher_name": "Pitcher",
        "batter_id": 20,
        "batter_name": "Batter",
        "event_type": "pitch",
        "event_name": "Pitch",
        "event_record_type": "pitch",
        "action_category": "pitch",
        "description": "",
    }
    rows = [
        {
            **base,
            "event_order": 0,
            "event_index": 0,
            "is_pitch": True,
            "play_id": "p0",
            "call_description": "Ball",
            "start_time": pd.Timestamp("2024-04-01T00:00:00Z"),
            "end_time": pd.Timestamp("2024-04-01T00:00:01Z"),
            "bases_before": "1B",
            "bases_after": "1B",
        },
        {
            **base,
            "event_order": 1,
            "event_index": 1,
            "is_pitch": False,
            "play_id": None,
            "event_type": "pickoff_1b",
            "event_name": "Pickoff Attempt 1B",
            "event_record_type": "action",
            "action_category": "pickoff",
            "description": "Pickoff attempt",
            "call_description": None,
            "start_time": pd.Timestamp("2024-04-01T00:00:05Z"),
            "end_time": pd.Timestamp("2024-04-01T00:00:06Z"),
            "bases_before": "1B",
            "bases_after": "empty",
        },
        {
            **base,
            "event_order": 2,
            "event_index": 2,
            "is_pitch": True,
            "play_id": "p2",
            "call_description": "Called Strike",
            "start_time": pd.Timestamp("2024-04-01T00:00:20Z"),
            "end_time": pd.Timestamp("2024-04-01T00:00:22Z"),
            "bases_before": "empty",
            "bases_after": "empty",
        },
        {
            **base,
            "event_order": 3,
            "event_index": 3,
            "is_pitch": True,
            "play_id": "p3",
            "call_description": "Swinging Strike",
            "start_time": pd.Timestamp("2024-04-01T00:00:38Z"),
            "end_time": pd.Timestamp("2024-04-01T00:00:41Z"),
            "bases_before": "empty",
            "bases_after": "empty",
        },
        {
            **base,
            "event_order": 4,
            "event_index": 4,
            "is_pitch": True,
            "play_id": "p4",
            "call_description": "Ball",
            "start_time": pd.Timestamp("2024-04-01T00:00:55Z"),
            "end_time": pd.Timestamp("2024-04-01T00:00:58Z"),
            "bases_before": "empty",
            "bases_after": "empty",
        },
    ]
    return pd.DataFrame(rows)


class TempoBenchmarkTests(unittest.TestCase):
    def test_pairing_preserves_actions_and_both_timestamp_measures(self):
        pairs = build_tempo_pairs(event_frame())
        first = pairs.iloc[0]

        self.assertEqual(len(pairs), 3)
        self.assertTrue(first["documented_rule_eligible"])
        self.assertEqual(first["base_state"], "bases_empty")
        self.assertEqual(first["preceding_state"], "runners_on")
        self.assertEqual(first["intervening_action_count"], 1)
        self.assertIn("pickoff_1b", first["intervening_actions"])
        self.assertAlmostEqual(first["start_to_start_seconds"], 20.0)
        self.assertAlmostEqual(first["end_to_end_seconds"], 21.0)

    def test_preceding_called_strike_is_eligible_but_swing_is_not(self):
        pairs = build_tempo_pairs(event_frame())

        self.assertTrue(pairs.iloc[1]["documented_rule_eligible"])
        self.assertEqual(pairs.iloc[1]["preceding_call"], "Called Strike")
        self.assertFalse(pairs.iloc[2]["documented_rule_eligible"])
        self.assertEqual(pairs.iloc[2]["preceding_call"], "Swinging Strike")

    def test_summary_uses_current_pitch_base_state_and_keeps_long_interval(self):
        pairs = build_tempo_pairs(event_frame())
        pitchers = pd.DataFrame(
            [{"entity_id": 10, "entity_name": "Pitcher"}]
        )
        summary = summarize_measure(
            pairs, pitchers, value_column="start_to_start_seconds"
        )
        empty = summary.loc[summary["base_state"].eq("bases_empty")].iloc[0]

        self.assertEqual(empty["feed_eligible_intervals"], 2)
        self.assertAlmostEqual(empty["feed_median_seconds"], 19.0)
        self.assertEqual(empty["action_interrupted"], 1)


if __name__ == "__main__":
    unittest.main()
