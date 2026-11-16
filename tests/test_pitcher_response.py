import unittest
import pandas as pd
import numpy as np
from scripts.pitcher_response import features,fit,NUM,CATEGORIES,TARGET

class ResponseTests(unittest.TestCase):
    def frame(self):
        d=pd.DataFrame({c:[0.,1.,2.,0.,1.,2.] for c in NUM})
        for c in CATEGORIES: d[c]=['a','a','b','b','a','b']
        d[TARGET]=[0,0,1,0,1,0]; d['raw']=[.01,.02,.03,.04,.05,.06]
        for era in ['pre_2023','post_2023']: d[f'runner_prior_{era}_eligible_opportunities']=[0,1,2,3,4,5]
        return d
    def test_future_fields_do_not_enter_response_features(self):
        d=self.frame(); x=features(d,'raw',True)
        d[TARGET]=1-d[TARGET]
        for c in ['terminal_window','runner_identity_changed_within_window','recorded_steal_attempt_indicator','recorded_pitcher_pickoff_count','close_reason']: d[c]=999
        pd.testing.assert_frame_equal(x,features(d,'raw',True))
    def test_unseen_identities_produce_finite_predictions(self):
        d=self.frame(); m=fit(d,'raw'); d.loc[0,'pitcher_id']='unseen'
        self.assertTrue(np.isfinite(m.predict_proba(features(d,'raw'))).all())
    def test_context_does_not_include_threat(self):
        d=self.frame(); x=features(d); d.raw=1-d.raw
        pd.testing.assert_frame_equal(x,features(d))
if __name__=='__main__': unittest.main()
