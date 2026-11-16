import unittest

import pandas as pd

from scripts.pipeline_validation import ValidationError
from scripts.rebuild_grouped_events import validate_disengagement_disposition


class DisengagementDispositionTests(unittest.TestCase):
    def checks(self):
        return pd.DataFrame([dict(action_id='A-746241-18-5-e', raw_number_available=True,
                                  raw_number_matches=False, raw_disengagement_num=3,
                                  reconstructed_disengagement_num=1)])

    def test_reviewed_outside_population_case(self):
        result = validate_disengagement_disposition(self.checks(), pd.DataFrame({'at_bat_index': [17, 19]}))
        self.assertIn('no_first_only_window', result)

    def test_same_case_with_eligible_window_blocks(self):
        with self.assertRaisesRegex(ValidationError, 'affects eligible'):
            validate_disengagement_disposition(self.checks(), pd.DataFrame({'at_bat_index': [18]}))

    def test_unreviewed_case_blocks(self):
        checks = self.checks()
        checks.loc[0, 'action_id'] = 'A-746242-18-5-e'
        with self.assertRaisesRegex(ValidationError, 'Unreviewed'):
            validate_disengagement_disposition(checks, pd.DataFrame({'at_bat_index': [17]}))
