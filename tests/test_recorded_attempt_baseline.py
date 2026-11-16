import unittest
import numpy as np
import pandas as pd
from scripts.recorded_attempt_baseline import features, fit, predict, NUM, CAT, LABEL

class BaselineTests(unittest.TestCase):
    def frame(self):
        d = pd.DataFrame({c: [0.,1.,2.,0.,1.,2.] for c in NUM})
        for c in CAT: d[c] = ['a','a','b','a','b','b']
        d['season'] = [2022,2022,2023,2023,2023,2023]
        d[LABEL] = [0,0,1,0,0,1]
        for b in ['pre_2023','post_2023']:
            d[f'runner_prior_{b}_eligible_opportunities'] = [0,10,20,30,40,50]
            d[f'runner_prior_{b}_attempted_opportunities'] = [0,0,1,1,2,2]
        return d

    def test_future_fields_cannot_change_predictions(self):
        d = self.frame(); m = fit(d,'separate_history'); p = predict(m,d)
        d[LABEL] = 1-d[LABEL]
        for c in ['terminal_window','runner_identity_changed_within_window','recorded_pitcher_pickoff_count','recorded_steal_success_count','close_reason']:
            d[c] = 999
        np.testing.assert_array_equal(p,predict(m,d))

    def test_rule_and_cold_start(self):
        d = self.frame(); x = features(d,'separate_history',.02)
        self.assertEqual(x.loc[0,'pre_2023_rate'],.02)
        self.assertEqual(x.loc[0,'pre_2023_cold'],1)
        self.assertEqual(x.loc[1,'disengagements_remaining_without_penalty'],0)
        self.assertEqual(x.loc[2,'disengagements_remaining_without_penalty'],2)
        self.assertFalse(any('pre_2023_' in c for c in features(d,'post_history',.02)))

    def test_missing_context_and_unseen_category(self):
        d = self.frame(); m = fit(d,'context'); d.loc[0,'inning'] = np.nan
        d.loc[0,'half_inning'] = 'unseen'
        self.assertTrue(np.isfinite(predict(m,d)).all())

if __name__ == '__main__': unittest.main()
