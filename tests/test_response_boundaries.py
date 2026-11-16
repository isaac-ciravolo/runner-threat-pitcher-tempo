import unittest

import pandas as pd

from scripts.pipeline_validation import ValidationError
from scripts.verify_response_boundaries import verify_response_boundaries


class ResponseBoundaryTests(unittest.TestCase):
    def fixture(self):
        feed = {'gamePk': 1, 'liveData': {'plays': {'allPlays': [
            {'about': {'atBatIndex': 0}, 'playEvents': [
                {'index': 0, 'playId': 'pitch', 'isPitch': True},
                {'index': 1, 'actionPlayId': 'pitch', 'details': {'eventType': 'stolen_base_2b'}}]}]}}}
        frame = pd.DataFrame([dict(at_bat_index=0, feature_cutoff_game_sequence=0,
                                  close_event_index=0, response_action_ids='A-1-0-1-attempt',
                                  recorded_steal_attempt_record_count=1)])
        return frame, feed

    def test_annotation_after_close_belongs_to_linked_pitch(self):
        frame, feed = self.fixture()
        self.assertEqual(verify_response_boundaries(frame, feed)['attempts'], 1)

    def test_retrospective_link_is_rejected(self):
        frame, feed = self.fixture()
        frame.loc[0, 'feature_cutoff_game_sequence'] = 1
        frame.loc[0, 'close_event_index'] = 1
        with self.assertRaisesRegex(ValidationError, 'Linked response'):
            verify_response_boundaries(frame, feed)

    def test_duplicate_assignment_is_rejected(self):
        frame, feed = self.fixture()
        with self.assertRaisesRegex(ValidationError, 'assigned twice'):
            verify_response_boundaries(pd.concat([frame, frame]), feed)

    def test_pitch_attached_movement_has_its_own_source_check(self):
        frame, feed = self.fixture()
        play = feed['liveData']['plays']['allPlays'][0]
        play['playEvents'] = play['playEvents'][:1]
        play['runners'] = [{'details': {'playIndex': 0, 'movementReason': 'r_caught_stealing_2b'}}]
        frame.loc[0, 'response_action_ids'] = 'A-1-0-0-me'
        self.assertEqual(verify_response_boundaries(frame, feed)['attempts'], 1)
        play['runners'][0]['details']['movementReason'] = 'r_adv_play'
        with self.assertRaisesRegex(ValidationError, 'Attempt record accounting'):
            verify_response_boundaries(frame, feed)

    def test_unlabeled_eligible_movement_blocks_promotion(self):
        frame, feed = self.fixture()
        frame.loc[0, 'response_action_ids'] = ''
        frame.loc[0, 'recorded_steal_attempt_record_count'] = 0
        feed['liveData']['plays']['allPlays'][0]['runners'] = [
            {'details': {'playIndex': 0, 'movementReason': 'r_caught_stealing_2b'}}]
        with self.assertRaisesRegex(ValidationError, 'missing from response'):
            verify_response_boundaries(frame, feed)
