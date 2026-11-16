import unittest

import pandas as pd

from scripts.movement_evidence import movement_action_type, movement_evidence
from scripts.runner_control_audit import build_action_audit
from tests.test_runner_control_audit import event_row


class MovementEvidenceTests(unittest.TestCase):
    def movement(self, player, reason):
        return {'details': {'runner': {'id': player}, 'movementReason': reason}}

    def test_actions_keep_the_existing_pickoff_distinction(self):
        self.assertEqual(movement_action_type('r_caught_stealing_2b'), 'steal_attempt')
        self.assertEqual(movement_action_type('r_pickoff_caught_stealing_2b'), 'pickoff_throw')
        self.assertIsNone(movement_action_type('r_adv_play'))

    def test_only_identified_actor_gets_complete_path(self):
        attempt = self.movement(1, 'r_stolen_base_2b')
        later_out = self.movement(1, 'r_out_other')
        other = self.movement(2, 'r_adv_play')
        kinds, paths = movement_evidence([attempt, later_out, other])
        self.assertEqual(kinds, {'steal_attempt'})
        self.assertEqual(paths, [attempt, later_out])

    def test_mixed_action_classes_remain_visible(self):
        kinds, _ = movement_evidence([self.movement(1, 'r_stolen_base_2b'),
                                      self.movement(2, 'r_pickoff_3b')])
        self.assertEqual(kinds, {'steal_attempt', 'pickoff_throw'})

    def test_pitch_attached_caught_stealing_is_recovered_once(self):
        movement = self.movement(30, 'r_caught_stealing_2b')
        movement['details'].update(playIndex=0, eventType='caught_stealing_2b')
        movement['movement'] = dict(start='1B', originBase='1B', end=None, isOut=True, outBase='2B')
        feed = {'gamePk': 1, 'liveData': {'plays': {'allPlays': [
            {'about': {'atBatIndex': 2}, 'playEvents': [{'index': 0, 'type': 'pitch', 'isPitch': True}],
             'runners': [movement]}]}}}
        events = pd.DataFrame([dict(event_row(0, is_pitch=True, play_id='p'), movement_summary='out')])
        sources = pd.DataFrame([dict(game_pk=1, selected_for_parse=True, source_population='test', cache_path='x')])
        old, _, _ = build_action_audit([(pd.Series(dtype=object), feed)], events, sources)
        repaired, _, _ = build_action_audit([(pd.Series(dtype=object), feed)], events, sources,
                                            include_movement_evidence=True)
        self.assertTrue(old.empty)
        self.assertEqual(len(repaired), 1)
        self.assertEqual(repaired.iloc[0].action_id, 'A-1-2-0-me')
        self.assertEqual(repaired.iloc[0].outcome_type, 'caught_stealing')
        event = feed['liveData']['plays']['allPlays'][0]['playEvents'][0]
        event.update(type='pickoff', isPitch=False, details={'fromCatcher': False, 'code': '1'})
        paired, _, _ = build_action_audit([(pd.Series(dtype=object), feed)], events, sources,
                                         include_movement_evidence=True)
        self.assertEqual(paired.action_type.tolist(), ['pickoff_throw', 'steal_attempt'])
        self.assertTrue(paired.action_id.is_unique)
        self.assertEqual(paired.action_type.eq('pickoff_throw').sum(), 1)
