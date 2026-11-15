import unittest

import pandas as pd

from scripts.runner_control_audit import (
    _mapping_for_event,
    _outcome,
    build_opportunity_windows,
)


def event_row(order, *, is_pitch=False, play_id=None, before="1B", after="1B"):
    return {
        "game_pk": 1,
        "official_date": "2024-06-01",
        "at_bat_index": 2,
        "event_index": order,
        "event_order": order,
        "event_key": f"1:2:{order}",
        "inning": 3,
        "half_inning": "top",
        "pitcher_id": 10,
        "pitcher_name": "Pitcher",
        "batter_id": 20,
        "batter_name": "Batter",
        "is_pitch": is_pitch,
        "play_id": play_id,
        "bases_before": before,
        "bases_after": after,
        "runner_1b_before": 30 if before == "1B" else None,
        "runner_1b_after": 30 if after == "1B" else None,
        "derived_pre_balls": 0,
        "derived_pre_strikes": 0,
        "derived_pre_outs": 1,
        "feed_count_balls": 0,
        "feed_count_strikes": 0,
        "feed_count_outs": 1,
    }


class RunnerControlAuditTests(unittest.TestCase):
    def test_pickoff_initiator_uses_from_catcher(self):
        pitcher = {"type": "pickoff", "details": {"fromCatcher": False}}
        catcher = {"type": "pickoff", "details": {"fromCatcher": True}}

        self.assertEqual(_mapping_for_event(pitcher)[:2], ("pickoff_throw", "pitcher"))
        self.assertEqual(_mapping_for_event(catcher)[:2], ("pickoff_throw", "catcher"))

    def test_disengagement_violation_has_explicit_mapping(self):
        event = {
            "type": "action",
            "details": {
                "eventType": "forced_balk",
                "violation": {"type": "pitcher_disengagement"},
            },
        }

        self.assertEqual(
            _mapping_for_event(event)[:2],
            ("disengagement_violation", "pitcher"),
        )

    def test_batter_movement_is_not_a_runner_outcome(self):
        walk = {
            "movement": {"originBase": None, "start": None, "end": "1B", "isOut": False},
            "details": {"eventType": "walk"},
        }

        observed = _outcome("timer_violation", [walk])

        self.assertEqual(observed[0], "no_runner_outcome")
        self.assertFalse(observed[1])
        self.assertFalse(observed[3])
        self.assertTrue(observed[5])

    def test_window_keeps_multiple_throws_and_terminal_action(self):
        events = pd.DataFrame(
            [
                event_row(0),
                event_row(1),
                event_row(2, is_pitch=True, play_id="p2"),
                event_row(3, before="1B", after="empty"),
            ]
        )
        actions = pd.DataFrame(
            [
                {"event_key": "1:2:0", "action_id": "a0", "action_type": "pickoff_throw", "initiator_role": "pitcher"},
                {"event_key": "1:2:1", "action_id": "a1", "action_type": "pickoff_throw", "initiator_role": "pitcher"},
                {"event_key": "1:2:3", "action_id": "a3", "action_type": "pickoff_throw", "initiator_role": "pitcher"},
            ]
        )
        states = pd.DataFrame(
            [{"game_pk": 1, "at_bat_index": 2, "half_inning_ended": True}]
        )

        windows = build_opportunity_windows(events, actions, states)

        self.assertEqual(len(windows), 2)
        self.assertEqual(windows.iloc[0]["open_timing"], "before_first_event")
        self.assertEqual(windows.iloc[0]["pickoff_throw_count"], 2)
        self.assertEqual(windows.iloc[0]["close_reason"], "next_pitch")
        self.assertEqual(windows.iloc[1]["open_timing"], "after_pitch")
        self.assertEqual(windows.iloc[1]["close_reason"], "state_exit")
        self.assertTrue(windows.iloc[1]["terminal_without_pitch"])


if __name__ == "__main__":
    unittest.main()
