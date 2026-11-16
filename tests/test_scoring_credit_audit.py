import unittest

from scripts.scoring_credit_audit import reconcile


class ScoringCreditTests(unittest.TestCase):
    def feed(self, tags, sb, cs):
        events = [dict(index=index, details={'eventType': tag}, player={'id': 7})
                  for index, tag in enumerate(tags)]
        return {'liveData': {'plays': {'allPlays': [{'about': {'atBatIndex': 0}, 'playEvents': events}]},
                             'boxscore': {'teams': {'away': {'players': {}}, 'home': {'players': {
                                 'ID7': {'person': {'id': 7}, 'stats': {'batting': {
                                     'stolenBases': sb, 'caughtStealing': cs}}}}}}}}}

    def test_ordinary_and_pickoff_credits(self):
        rows, vocabulary, issues = reconcile(self.feed(['stolen_base_2b', 'caught_stealing_3b',
                                                       'pickoff_caught_stealing_2b'], 1, 2))
        self.assertTrue(rows[0]['agrees'])
        self.assertEqual(sum(vocabulary.values()), 3)
        self.assertEqual(issues, [])

    def test_error_variant_is_inventoried_not_counted(self):
        rows, vocabulary, _ = reconcile(self.feed(['caught_stealing_2b_error'], 0, 0))
        self.assertTrue(rows[0]['agrees'])
        self.assertEqual(vocabulary['caught_stealing_2b_error'], 1)

    def test_missing_actor_is_retained(self):
        feed = self.feed(['stolen_base_2b'], 1, 0)
        del feed['liveData']['plays']['allPlays'][0]['playEvents'][0]['player']
        rows, _, issues = reconcile(feed)
        self.assertFalse(rows[0]['agrees'])
        self.assertEqual(issues[0]['issue'], 'missing_actor')

    def test_boxscore_disagreement_is_not_rewritten(self):
        rows, _, _ = reconcile(self.feed(['stolen_base_2b'], 2, 0))
        self.assertFalse(rows[0]['agrees'])
        self.assertEqual(rows[0]['boxscore_sb'], 2)
        self.assertEqual(rows[0]['tagged_sb'], 1)

    def test_player_on_both_sides_of_resumed_game(self):
        feed = self.feed(['stolen_base_2b', 'caught_stealing_2b'], 1, 0)
        feed['liveData']['boxscore']['teams']['away']['players']['ID7'] = {
            'person': {'id': 7}, 'stats': {'batting': {'stolenBases': 0, 'caughtStealing': 1}}}
        rows, _, _ = reconcile(feed)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['boxscore_sides'], 2)
        self.assertTrue(rows[0]['agrees'])

    def test_pitch_attached_movement_recovers_missing_credit(self):
        feed = self.feed([], 0, 1)
        play = feed['liveData']['plays']['allPlays'][0]
        movement = {'details': {'runner': {'id': 7}, 'playIndex': 0,
                                 'eventType': 'caught_stealing_2b', 'movementReason': 'r_caught_stealing_2b'}}
        play['runners'] = [movement, movement.copy()]
        rows, _, _ = reconcile(feed)
        self.assertFalse(rows[0]['agrees'])
        self.assertTrue(rows[0]['movement_agrees'])
        self.assertEqual(rows[0]['movement_cs'], 1)

    def test_accompanying_advance_is_not_a_second_attempt(self):
        feed = self.feed([], 0, 0)
        feed['liveData']['plays']['allPlays'][0]['runners'] = [
            {'details': {'runner': {'id': 7}, 'playIndex': 0, 'eventType': 'caught_stealing_home',
                          'movementReason': 'r_adv_play'}}]
        rows, _, _ = reconcile(feed)
        self.assertTrue(rows[0]['movement_agrees'])
        self.assertEqual(rows[0]['movement_cs'], 0)
