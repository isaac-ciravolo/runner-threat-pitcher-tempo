import unittest
from scripts.chronology_audit import audit_feed
from scripts.chronology_dispositions import availability
import pandas as pd

class ChronologyTests(unittest.TestCase):
    def feed(self):
        return {'gameData':{'datetime':{'dateTime':'2023-10-02T17:10:00Z','resumeDate':'2023-10-02'}},'liveData':{'plays':{'allPlays':[{'about':{'startTime':'2023-09-28T23:00:00Z','endTime':'2023-09-29T01:00:00Z','isComplete':True},'playEvents':[{'isPitch':False,'startTime':'2023-09-28T22:00:00Z','endTime':'2023-09-28T22:01:00Z'},{'isPitch':True,'startTime':'2023-09-28T23:01:00Z','endTime':'2023-09-28T23:02:00Z'}]}]}}}
    def test_resume_header_is_not_freeze(self):
        r=audit_feed(self.feed())
        self.assertEqual(r['freeze_time'],'2023-09-28T22:00:00+00:00')
        self.assertTrue(r['header_after_last_event'])
        self.assertTrue(r['resolved_bounds'])
    def test_inverted_and_missing_times_flagged(self):
        f=self.feed(); events=f['liveData']['plays']['allPlays'][0]['playEvents']; events[0]['endTime']='2023-09-27T00:00:00Z'; events[1].pop('endTime')
        r=audit_feed(f)
        self.assertEqual(r['inverted_events'],1); self.assertEqual(r['missing_event_times'],1)
    def test_implausibly_early_event_stops_bounds_gate(self):
        f=self.feed(); f['liveData']['plays']['allPlays'][0]['playEvents'][0]['startTime']='2023-09-01T00:00:00Z'
        self.assertFalse(audit_feed(f)['resolved_bounds'])
    def test_finalization_override_cannot_release_in_september(self):
        t,reason=availability({'game_pk':716404,'last_observed_time':'2023-09-29T01:22:11Z'})
        self.assertEqual(t,pd.Timestamp('2023-10-05T04:00:00Z'))
    def test_rain_buffer_is_explicit(self):
        t,reason=availability({'game_pk':663065,'last_observed_time':'2022-06-07T01:50:00Z'})
        self.assertEqual(t,pd.Timestamp('2022-06-08T01:50:00Z'))
        self.assertIn('assumption',reason)
if __name__=='__main__': unittest.main()
