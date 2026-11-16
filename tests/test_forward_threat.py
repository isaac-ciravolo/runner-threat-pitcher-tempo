import unittest
import numpy as np
import pandas as pd
from scripts.forward_threat import training_mask, calibration_pool, fit_calibration, apply_calibration

class ForwardThreatTests(unittest.TestCase):
    def test_strict_completion_and_rule_era(self):
        origin=pd.Timestamp('2023-07-01',tz='UTC')
        d=pd.DataFrame({'completion':pd.to_datetime(['2023-06-30','2023-07-01','2023-07-02','2022-10-01'],utc=True),'season':[2023,2023,2023,2022],'raw':[.1,.1,.1,.1]})
        d['start']=pd.Timestamp('2022-01-01',tz='UTC')
        self.assertEqual(training_mask(d,origin).tolist(),[True,False,False,True])
        self.assertEqual(calibration_pool(d,origin,2023).index.tolist(),[0])
        d.loc[0,'start']=pd.Timestamp('2023-07-02',tz='UTC')
        self.assertFalse(training_mask(d,origin).iloc[0])

    def test_fallback_is_exact_identity(self):
        p=np.array([.01,.2,.3]); m,status=fit_calibration(p,[0,0,1])
        self.assertIsNone(m); np.testing.assert_array_equal(apply_calibration(m,p),p)

    def test_calibration_preserves_order_and_ignores_future(self):
        p=np.linspace(.01,.9,1000); y=np.arange(1000)>699
        m,status=fit_calibration(p,y)
        self.assertEqual(status,'logistic_recalibration')
        q=apply_calibration(m,p)
        self.assertTrue((np.diff(q)>=0).all())
        self.assertTrue(np.isfinite(apply_calibration(m,[0,1])).all())

if __name__=='__main__': unittest.main()
