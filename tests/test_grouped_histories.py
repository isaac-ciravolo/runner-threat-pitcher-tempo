import unittest

import pandas as pd

from scripts.grouped_histories import SUFFIXES, verify_histories
from scripts.pipeline_validation import ValidationError


class GroupedHistoryTests(unittest.TestCase):
    def fixture(self):
        rows = []
        for game in (1, 2, 3):
            row = dict(game_pk=game, season=2023, runner_id=10, opportunity_id=str(game),
                       attempt_history_eligible=True, recorded_steal_attempt_indicator=game == 1,
                       recorded_steal_attempt_record_count=int(game == 1),
                       recorded_steal_success_count=int(game == 1),
                       recorded_steal_unsuccessful_count=0, recorded_steal_ambiguous_count=0)
            for era in ('all_regimes', 'pre_2023', 'post_2023'):
                for suffix in SUFFIXES:
                    value = 0
                    if game == 3 and era != 'pre_2023':
                        value = {'eligible_opportunities': 2, 'attempted_opportunities': 1,
                                 'attempt_records': 1, 'successes': 1}.get(suffix, 0)
                    row[f'runner_prior_{era}_{suffix}'] = value
            rows.append(row)
        timing = pd.DataFrame({'game_pk': [1, 2, 3],
                               'freeze': pd.to_datetime(['2023-01-01', '2023-01-03', '2023-01-05'], utc=True),
                               'available': pd.to_datetime(['2023-01-03', '2023-01-04', '2023-01-06'], utc=True)}).set_index('game_pk')
        return pd.DataFrame(rows), timing

    def test_equal_availability_is_not_earlier(self):
        frame, timing = self.fixture()
        self.assertEqual(verify_histories(frame, timing, {1, 2, 3}), 54)

    def test_corrupted_history_fails(self):
        frame, timing = self.fixture()
        frame.loc[1, 'runner_prior_post_2023_eligible_opportunities'] = 1
        with self.assertRaises(ValidationError):
            verify_histories(frame, timing, {2})
