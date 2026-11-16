import unittest

from scripts.movement_evidence import movement_action_type, movement_evidence


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
