import unittest

import pandas as pd

from scripts.opening_identities import pitcher_timeline, repair_opening_identities
from scripts.pipeline_validation import ValidationError


class PitcherTimelineTests(unittest.TestCase):
    def fixture(self):
        return {'gamePk': 1, 'liveData': {'boxscore': {'teams': {
            'home': {'pitchers': [10, 11]}, 'away': {'pitchers': [20]}}},
            'plays': {'allPlays': [{'about': {'atBatIndex': 0, 'halfInning': 'top'},
                'matchup': {'pitcher': {'id': 11}}, 'playEvents': [
                    {'index': 0, 'isPitch': True},
                    {'index': 1, 'details': {'eventType': 'pitching_substitution'}, 'player': {'id': 11}},
                    {'index': 2, 'isPitch': True}]}]}}}

    def test_final_matchup_does_not_leak_before_substitution(self):
        snapshots, events, changes = pitcher_timeline(self.fixture())
        self.assertEqual(snapshots[0]['top'], 10)
        self.assertEqual(snapshots[1]['top'], 10)
        self.assertEqual(snapshots[2]['top'], 11)
        self.assertEqual(snapshots[3]['bottom'], 20)
        self.assertEqual(changes, [(0, 1, True, False)])

    def test_unrecorded_identity_change_fails(self):
        feed = self.fixture()
        feed['liveData']['plays']['allPlays'][0]['playEvents'].pop(1)
        with self.assertRaises(ValidationError):
            pitcher_timeline(feed)

    def test_window_cutoff_and_attribution_are_repaired_together(self):
        feed = self.fixture()
        feed['gameData'] = {'players': {'ID10': {'id': 10, 'fullName': 'Starter'},
                                        'ID11': {'id': 11, 'fullName': 'Reliever'}}}
        frame = pd.DataFrame([dict(pitcher_id=11, pitcher_name='Reliever', half_inning='top',
                                  at_bat_index=0, feature_cutoff_game_sequence=0,
                                  feature_cutoff_event_order=-1, close_event_order=2,
                                  attempt_history_eligible=True, recorded_steal_attempt_record_count=1,
                                  recorded_steal_outcome_class='recorded_success',
                                  history_count_exclusion_reason=float('nan'))])
        fixed, changed = repair_opening_identities(frame, feed)
        self.assertEqual(changed, 1)
        self.assertEqual(fixed.iloc[0].pitcher_id, 10)
        self.assertTrue(fixed.iloc[0].pitcher_identity_changed_within_window)
        self.assertFalse(fixed.iloc[0].attempt_history_eligible)
        self.assertEqual(frame.iloc[0].pitcher_id, 11)
