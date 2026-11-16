import unittest

import pandas as pd

from scripts.grouped_events import grouping_plan, collapse_outcome_groups
from scripts.runner_control_audit import build_opportunity_windows


class GroupingTests(unittest.TestCase):
    def play(self):
        return {'playEvents': [
            {'index': 0, 'isPitch': True, 'playId': 'pitch'},
            {'index': 1, 'actionPlayId': 'pitch', 'details': {'eventType': 'stolen_base_2b'}},
        ]}

    def test_exact_pitch_and_nonpitch_parents(self):
        play = self.play()
        self.assertEqual(grouping_plan(play), ({1: 0}, []))
        play['playEvents'][0]['isPitch'] = False
        play['playEvents'][0]['type'] = 'pickoff'
        self.assertEqual(grouping_plan(play), ({1: 0}, []))

    def test_unrelated_interruption_blocks_collapse(self):
        play = self.play()
        play['playEvents'].insert(1, {'index': 5, 'details': {'eventType': 'mound_visit'}})
        mapping, unresolved = grouping_plan(play)
        self.assertEqual(mapping, {})
        self.assertEqual(unresolved[0]['reason'], 'interleaved_or_nested_group')

    def test_missing_link_is_not_inferred(self):
        play = self.play()
        del play['playEvents'][1]['actionPlayId']
        self.assertEqual(grouping_plan(play)[0], {})
        self.assertEqual(grouping_plan(play)[1][0]['reason'], 'missing_or_nonunique_parent')

    def test_linked_catcher_throw_belongs_to_completed_pitch_play(self):
        play = self.play()
        play['playEvents'].insert(1, {'index': 5, 'type': 'pickoff', 'actionPlayId': 'pitch',
                                     'details': {'fromCatcher': True}})
        self.assertEqual(grouping_plan(play), ({5: 0, 1: 0}, []))
        play['playEvents'][1]['details']['fromCatcher'] = False
        self.assertEqual(grouping_plan(play)[0], {})

    def test_delayed_steal_belongs_to_window_ending_at_pitch(self):
        base = dict(game_pk=1, at_bat_index=2, official_date='2024-06-01', inning=3,
                    half_inning='top', pitcher_id=10, pitcher_name='P', batter_id=20,
                    batter_name='B', bases_before='1B', bases_after='1B', runner_1b_before=30,
                    runner_1b_after=30, runner_2b_after=None, runner_3b_after=None,
                    derived_pre_balls=0, derived_pre_strikes=0, derived_pre_outs=1,
                    feed_count_balls=1, feed_count_strikes=0, feed_count_outs=1,
                    post_away_score=0, post_home_score=0)
        events = pd.DataFrame([
            dict(base, event_index=0, event_order=0, game_sequence=1, event_key='1:2:0',
                 is_pitch=True, play_id='pitch'),
            dict(base, event_index=1, event_order=1, game_sequence=2, event_key='1:2:1',
                 is_pitch=False, play_id=None, bases_after='2B', runner_1b_after=None, runner_2b_after=30),
            dict(base, event_index=2, event_order=2, game_sequence=3, event_key='1:2:2',
                 is_pitch=True, play_id='later', bases_before='2B', bases_after='2B',
                 runner_1b_before=None, runner_1b_after=None, runner_2b_after=30),
        ])
        actions = pd.DataFrame([dict(event_key='1:2:1', event_index=1, event_order=1,
                                     action_id='raw-steal', action_type='steal_attempt', initiator_role='runner')])
        play = self.play()
        play['about'] = {'atBatIndex': 2}
        feed = {'gamePk': 1, 'liveData': {'plays': {'allPlays': [play]}}}
        grouped, moved, mapping = collapse_outcome_groups(feed, events, actions)
        states = pd.DataFrame([dict(game_pk=1, at_bat_index=2, half_inning_ended=False)])
        windows = build_opportunity_windows(grouped, moved, states)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows.iloc[0].open_balls, 0)
        self.assertEqual(windows.iloc[0].steal_attempt_count, 1)
        self.assertTrue(windows.iloc[0].following_pitch_exists)
        self.assertEqual(grouped.iloc[0].bases_after, '2B')
        self.assertEqual(mapping, {'1:2:1': '1:2:0'})
        self.assertEqual(moved.iloc[0].action_id, 'raw-steal')
        self.assertEqual(moved.iloc[0].source_event_index, 1)
