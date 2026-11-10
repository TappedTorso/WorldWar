import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from discovery_store import canonical_url, merge_articles, normalize_article, normalize_timestamp
import update_events


class DiscoveryTests(unittest.TestCase):
    def test_seen_time_is_not_published_time(self):
        legacy={'id':'old','headline':'Example','url':'https://example.org/A','published_at':'20261110T000000Z','tags':['UKRAINE']}
        record=normalize_article(legacy,provider='GDELT_DOC_API',retrieved_at='2026-11-10T01:00:00Z')
        self.assertIsNone(record['published_at'])
        self.assertEqual(record['discovered_at'],'2026-11-10T00:00:00Z')
        self.assertEqual(record['legacy_published_at'],'20261110T000000Z')

    def test_time_precision_and_invalid_values(self):
        self.assertIsNone(normalize_timestamp('2026-11-10'))
        self.assertIsNone(normalize_timestamp('20261310T000000Z'))
        self.assertIsNone(normalize_timestamp('2026-11-10T05:00:00'))
        self.assertEqual(normalize_timestamp('20261110000000'),'2026-11-10T00:00:00Z')

    def test_url_identity_deduplicates_headline_changes_not_distinct_paths(self):
        one=normalize_article({'id':'one','headline':'Title 1','url':'https://example.org/A?utm_source=x','seendate':'20261110000000'})
        two=normalize_article({'id':'two','headline':'Updated title','url':'https://example.org/A','seendate':'20261110010000'})
        merged=merge_articles([one],[two])
        self.assertEqual(len(merged),1)
        self.assertEqual(merged[0]['id'],'one')
        self.assertEqual(merged[0]['first_seen_at'],'2026-11-10T00:00:00Z')
        self.assertEqual(merged[0]['last_seen_at'],'2026-11-10T01:00:00Z')
        self.assertNotEqual(canonical_url('https://example.org/A'),canonical_url('https://example.org/a'))
        self.assertEqual(canonical_url('javascript:alert(1)'),'')

    def test_fresh_gdelt_and_rss_semantics(self):
        articles=[{'title':'War report','url':'https://example.org/a','seendate':'20261110T000000Z'},
                  {'title':'Publisher report','url':'https://example.org/b','published_at':'2026-11-09T12:00:00Z'}]
        records=update_events._build_events(articles)
        self.assertIsNone(records[0]['published_at'])
        self.assertEqual(records[0]['discovered_at'],'2026-11-10T00:00:00Z')
        self.assertEqual(records[1]['published_at'],'2026-11-09T12:00:00Z')
        self.assertIsNone(records[1]['discovered_at'])

    def test_quoted_short_query_repaired(self):
        with patch.object(update_events,'_query_gdelt',return_value={'articles':[]}) as query:
            _,result=update_events.fetch_stream('core','("war" OR "armed conflict")')
        self.assertEqual(query.call_args.args[0]['query'],'(war OR "armed conflict")')
        self.assertTrue(result['query_repaired'])

    def test_failed_refresh_retains_records_and_persists_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); old={'metadata':{'generated_at_utc':'2026-11-09T00:00:00Z'},'events':[{'id':'old','url':'https://example.org/a','headline':'Old'}]}
            (root/'events.json').write_text(json.dumps(old))
            with patch.multiple(update_events,DATA_DIR=root,OUT_PATH=root/'events.json',META_PATH=root/'meta.json',FALLBACK_ENABLED=False,STREAM_STAGGER_SECS=0,DRY_RUN=False), patch.object(update_events,'fetch_stream',return_value=([],{'name':'core','status':'error','error':'provider_non_json','fetched':0})):
                self.assertEqual(update_events.main(),0)
            saved=json.loads((root/'events.json').read_text())
            self.assertEqual(saved['events'],old['events'])
            self.assertEqual(saved['metadata']['generated_at_utc'],old['metadata']['generated_at_utc'])
            self.assertEqual(saved['metadata']['status'],'error')
            self.assertEqual(json.loads((root/'discovery/runs.json').read_text())[0]['status'],'error')
            self.assertFalse((root/'meta.json').exists())


if __name__=='__main__': unittest.main()
