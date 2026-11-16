import unittest

import pandas as pd

from scripts.prepare_opportunity_dataset import (
    build_disengagement_history,
    proposed_splits,
)


class OpportunityPreparationTests(unittest.TestCase):
    def test_grouped_stepoff_precedes_pickoff_outcome(self):
        events = pd.DataFrame([dict(game_pk=1, at_bat_index=0, event_index=1,
                                    event_order=1, event_key='1:0:1')])
        actions = pd.DataFrame([
            dict(event_key='1:0:1', event_index=1, action_id='step', action_type='step_off',
                 initiator_role='pitcher', raw_disengagement_num=1),
            dict(event_key='1:0:1', event_index=2, action_id='outcome', action_type='pickoff_throw',
                 initiator_role='pitcher', raw_disengagement_num=1),
        ])
        feed = {'gamePk': 1, 'liveData': {'plays': {'allPlays': [
            {'about': {'atBatIndex': 0}, 'playEvents': [{'index': 1}, {'index': 2}], 'runners': []}]}}}
        history, checks = build_disengagement_history(events, actions, [(pd.Series(), feed)],
                                                       event_key_map={'1:0:2': '1:0:1'})
        self.assertEqual(history.iloc[0].recorded_disengagements_since_reset_after_event, 1)
        self.assertTrue(checks.raw_number_matches.all())
        self.assertEqual(checks.counts_as_disengagement.tolist(), [True, False])

    def test_disengagement_history_deduplicates_outcome_continuation_and_resets(self):
        play = {
            "about": {"atBatIndex": 0},
            "playEvents": [
                {"index": 0},
                {"index": 1},
                {"index": 2},
                {"index": 3},
            ],
            "runners": [
                {
                    "movement": {"start": "1B", "end": "2B"},
                    "details": {"playIndex": 2},
                }
            ],
        }
        loaded = [
            (
                pd.Series({"game_pk": 1}),
                {
                    "gamePk": 1,
                    "liveData": {"plays": {"allPlays": [play]}},
                },
            )
        ]
        events = pd.DataFrame(
            [
                {
                    "game_pk": 1,
                    "at_bat_index": 0,
                    "event_index": order,
                    "event_order": order,
                    "event_key": f"1:0:{order}",
                }
                for order in range(4)
            ]
        )
        actions = pd.DataFrame(
            [
                {
                    "event_key": "1:0:0",
                    "action_id": "attempt",
                    "action_type": "pickoff_throw",
                    "initiator_role": "pitcher",
                    "raw_disengagement_num": 1,
                },
                {
                    "event_key": "1:0:1",
                    "action_id": "outcome-continuation",
                    "action_type": "pickoff_throw",
                    "initiator_role": "pitcher",
                    "raw_disengagement_num": 1,
                },
                {
                    "event_key": "1:0:3",
                    "action_id": "post-advance-stepoff",
                    "action_type": "step_off",
                    "initiator_role": "pitcher",
                    "raw_disengagement_num": 1,
                },
            ]
        )

        history, checks = build_disengagement_history(events, actions, loaded)

        self.assertTrue(checks.loc[checks["raw_number_available"], "raw_number_matches"].eq(True).all())
        self.assertEqual(int(checks["continuation_of_prior_pickoff_record"].sum()), 1)
        after_continuation = history.set_index("event_key").loc[
            "1:0:1", "recorded_disengagements_since_reset_after_event"
        ]
        after_advance = history.set_index("event_key").loc[
            "1:0:2", "recorded_disengagements_since_reset_after_event"
        ]
        after_stepoff = history.set_index("event_key").loc[
            "1:0:3", "recorded_disengagements_since_reset_after_event"
        ]
        self.assertEqual(after_continuation, 1)
        self.assertEqual(after_advance, 0)
        self.assertEqual(after_stepoff, 1)

    def test_proposed_splits_are_strictly_chronological(self):
        splits = proposed_splits().assign(
            start=lambda frame: pd.to_datetime(frame["start_date"]),
            end=lambda frame: pd.to_datetime(frame["end_date"]),
        )

        self.assertTrue(
            (
                splits["start"].iloc[1:].reset_index(drop=True)
                > splits["end"].iloc[:-1].reset_index(drop=True)
            ).all()
        )
        self.assertEqual(splits.iloc[-1]["split"], "final_test")
        self.assertFalse(bool(splits.iloc[-1]["tuning_allowed"]))


if __name__ == "__main__":
    unittest.main()
