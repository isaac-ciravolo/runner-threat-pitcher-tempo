import unittest

import pandas as pd

from scripts.conditional_success_audit import classify
from scripts.pipeline_validation import ValidationError


class SuccessAuditTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({
            'recorded_steal_attempt_record_count': [0, 1, 1, 2, 1],
            'recorded_steal_success_count': [0, 1, 0, 1, 0],
            'recorded_steal_unsuccessful_count': [0, 0, 1, 1, 0],
            'recorded_steal_ambiguous_count': [0, 0, 0, 0, 1],
            'recorded_steal_attempt_indicator': [False, True, True, True, True],
            'recorded_steal_outcome_class': ['none', 'recorded_success', 'recorded_unsuccessful',
                                           'ambiguous_or_multiple', 'ambiguous_or_multiple'],
            'attempt_history_eligible': [True, True, False, True, True],
            'conditional_success_history_eligible': [False, True, False, False, False],
        })

    def test_dispositions_preserve_attribution_and_ambiguity(self):
        self.assertEqual(classify(self.frame()).tolist(), [
            'not_recorded_attempt', 'binary_history_eligible', 'binary_attribution_excluded',
            'unresolved_or_multiple', 'unresolved_or_multiple'])

    def test_inconsistent_counts_and_eligibility_fail(self):
        for column, value in [('recorded_steal_success_count', 2),
                              ('conditional_success_history_eligible', False),
                              ('recorded_steal_attempt_record_count', -1)]:
            with self.subTest(column=column):
                frame = self.frame()
                frame.loc[1, column] = value
                with self.assertRaises(ValidationError):
                    classify(frame)


if __name__ == '__main__':
    unittest.main()
