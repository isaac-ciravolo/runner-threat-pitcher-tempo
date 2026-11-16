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
