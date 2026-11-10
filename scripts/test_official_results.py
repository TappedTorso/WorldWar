import copy
import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path
from collect_official_results import collect, parse_delaware


def fixture():
    return [dict(office=office,candidate_name=name,election_name='2026 General Election',
        electiondate='2026-11-03T00:00:00.000',data_as_of='2026-11-04T03:03:18.000',
        total_votes=str(votes),percent_votes=str(votes),machine_votes=str(votes-5),absentee_votes='3',early_votes='2')
        for office in ['U.S. Senator','Representative In Congress'] for name,votes in [('Fixture A',60),('Fixture B',40)]]


class OfficialResultsTests(unittest.TestCase):
    def test_exact_identity_and_arithmetic(self):
        records=parse_delaware(fixture())
        self.assertEqual(set(records),{'e-de-house-00-2026','e-de-senate-2026'})
        self.assertEqual(records['e-de-house-00-2026']['total_votes'],100)
    def test_incomplete_or_wrong_election_rejected(self):
        for mutate in [lambda rows:rows.pop(),lambda rows:rows[0].update(election_name='2024 General Election'),
                       lambda rows:rows[0].update(total_votes='-1'),lambda rows:rows[0].update(machine_votes='100'),
                       lambda rows:rows[0].update(percent_votes='5'),lambda rows:rows[0].update(candidate_name='Fixture B')]:
            rows=fixture();mutate(rows)
            with self.assertRaises(ValueError):parse_delaware(rows)
    def test_placeholder_zero_and_saturation_rejected(self):
        rows=fixture()
        for r in rows:r.update(total_votes='0',machine_votes='0',absentee_votes='0',early_votes='0',percent_votes='0')
        with self.assertRaises(ValueError):parse_delaware(rows)
        with self.assertRaises(ValueError):parse_delaware(fixture()*500)

    def test_refresh_next_day_updates_source_date_without_inventing_review(self):
        seed={'contests':[{'id':identity} for identity in ['e-de-house-00-2026','e-de-senate-2026']],
              'sources':[{'id':'de-socrata-2026','retrieved_at':'2026-11-10T06:00:00Z',
                          'retrieval_date':'2026-11-10','reviewed_at':'2026-11-10T06:00:00Z'}]}
        def opener(*args,**kwargs):return io.BytesIO(json.dumps(fixture()).encode())
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'official.json'
            run=collect(seed,output,Path(temporary)/'runs.json',opener=opener,
                        clock=lambda:dt.datetime(2026,11,11,7,0,tzinfo=dt.timezone.utc))
            self.assertEqual(run['status'],'ok')
            source=json.loads(output.read_text())['sources'][0]
            self.assertEqual(source['retrieval_date'],'2026-11-11')
            self.assertEqual(source['retrieved_at'],'2026-11-11T07:00:00Z')
            self.assertIsNone(source['reviewed_at'])


if __name__=='__main__':unittest.main()
