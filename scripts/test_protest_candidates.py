import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from collect_protest_candidates import collect, windows


class ProtestCandidateTests(unittest.TestCase):
    def test_half_open_windows_and_zero_inference_prevented(self):
        start=dt.datetime(2026,9,1,tzinfo=dt.timezone.utc);end=start+dt.timedelta(days=21)
        self.assertEqual(len(list(windows(start,end,7))),3)
        def fail(*a,**k):raise RuntimeError('provider failed')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);collect(root,start,end,request=fail,stagger=0)
            ledger=json.loads((root/'protest-backfill.json').read_text())
            self.assertEqual([w['status'] for w in ledger['windows']],['error','error','unattempted'])
            self.assertEqual(json.loads((root/'protest-candidates.json').read_text())['events'],[])
    def test_articles_remain_candidates_and_idempotent(self):
        start=dt.datetime(2026,9,1,tzinfo=dt.timezone.utc);end=start+dt.timedelta(days=7)
        def response(*a,**k):return {'articles':[{'title':'Fixture protest reporting','url':'https://example.org/report','seendate':'20260901120000'}]}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);collect(root,start,end,request=response,stagger=0);collect(root,start,end,request=response,stagger=0)
            records=json.loads((root/'protest-candidates.json').read_text())['events']
            self.assertEqual(len(records),1)
            self.assertEqual(records[0]['evidence_status'],'unreviewed')
            self.assertIsNone(records[0]['published_at'])
            self.assertNotIn('occurred_start',records[0])

    def test_daily_collection_keeps_historical_failure_ledger(self):
        start=dt.datetime(2026,9,1,tzinfo=dt.timezone.utc)
        def fail(*a,**k):raise RuntimeError('provider failed')
        def empty(*a,**k):return {'articles':[]}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            collect(root,start,start+dt.timedelta(days=21),request=fail,stagger=0)
            today=dt.datetime(2026,11,10,tzinfo=dt.timezone.utc)
            collect(root,today-dt.timedelta(days=1),today,request=empty,stagger=0)
            ledger=json.loads((root/'protest-backfill.json').read_text())
            self.assertEqual([w['status'] for w in ledger['windows']],['error','error','unattempted','ok'])


if __name__=='__main__':unittest.main()
