#!/usr/bin/env python3
"""Collect protest article candidates, never counted or published as occurrences.

Use explicit dates for historical collection. Windows, saturation and failures
are retained so a partial attempt cannot become a claimed completed backfill.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import time
from pathlib import Path
from discovery_store import atomic_json, merge_articles, normalize_article
from update_events import _query_gdelt

QUERY='(protest OR demonstration OR strike OR blockade OR occupation)'


def windows(start,end,days=7):
    current=start
    while current<end:
        following=min(current+dt.timedelta(days=days),end)
        yield current,following
        current=following


def collect(root,start,end,window_days=7,request=_query_gdelt,stagger=10):
    path=root/'protest-candidates.json';log=root/'protest-runs.json';plan=root/'protest-backfill.json'
    previous=json.loads(path.read_text()) if path.exists() else {'metadata':{},'events':[]}
    articles=previous['events']; runs=json.loads(log.read_text()) if log.exists() else []
    ledger=json.loads(plan.read_text()) if plan.exists() else {'schema_version':'1.0','windows':[]}
    by_key={w['id']:w for w in ledger['windows']}
    ranges=list(windows(start,end,window_days))
    # Preserve historical windows when the scheduled daily collection runs.
    # Queue this request up front so an interrupted backfill retains its gaps.
    for left,right in ranges:
        key=left.isoformat()+'/'+right.isoformat()
        by_key.setdefault(key,{'id':key,'start':left.isoformat(),'end_exclusive':right.isoformat(),'status':'unattempted'})
    failures=0
    for i,(left,right) in enumerate(ranges):
        key=left.isoformat()+'/'+right.isoformat()
        if by_key.get(key,{}).get('status')=='ok':continue
        now=dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')
        run={'id':'protest-discovery-'+hashlib.sha256((key+now).encode()).hexdigest()[:20],
             'adapter':'gdelt-protest-discovery','domain':'protests','started_at':now,'completed_at':None,
             'status':'error','fetched_count':0,'accepted_count':0,'error':None,
             'note':'Article candidates only. No occurrence or activity count is derived from these records.'}
        window={'id':key,'start':left.isoformat(),'end_exclusive':right.isoformat(),'status':'unattempted'}
        try:
            params={'query':QUERY,'mode':'ArtList','format':'json','maxrecords':'250','sort':'DateAsc',
                    'startdatetime':left.strftime('%Y%m%d%H%M%S'),
                    'enddatetime':(right-dt.timedelta(seconds=1)).strftime('%Y%m%d%H%M%S')}
            payload=request(params,retries=2)
            raw=payload.get('articles')
            if not isinstance(raw,list):raise ValueError('Provider did not supply article list')
            candidates=[]
            for item in raw:
                record=normalize_article(item,provider='GDELT_DOC_API',retrieved_at=now)
                if record:
                    record['candidate_domain']='protests'
                    record['language']=item.get('language')
                    record['source_country']=item.get('sourcecountry')
                    candidates.append(record)
            count_before=len(articles);articles=merge_articles(articles,candidates)
            status='partial' if len(raw)>=250 else 'ok'
            run.update(status=status,fetched_count=len(raw),accepted_count=len(articles)-count_before)
            window.update(status=status,fetched_count=len(raw),possibly_truncated=len(raw)>=250)
            if len(raw)>=250:window['note']='Result cap reached. Subdivide query window before claiming complete candidate retrieval.'
            failures=0
        except Exception as exc:
            failures+=1
            category='provider_rate_limited_429' if 'status=429' in str(exc) else 'candidate_retrieval_failed'
            run['error']=category+'; no zero-activity inference'
            window.update(status='error',note=run['error'])
        run['completed_at']=dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')
        runs.append(run);by_key[key]=window
        atomic_json(path,{'metadata':{'schema_version':'1.0','kind':'source_candidates','domain':'protests',
             'article_count':len(articles),'note':'Unreviewed article metadata. None of these items is automatically a protest occurrence.'},'events':articles})
        atomic_json(log,runs)
        atomic_json(plan,{'schema_version':'1.0','requested_start':start.isoformat(),'requested_end_exclusive':end.isoformat(),
             'note':'Collection-window ledger, not geographic observation coverage. Failed and capped windows require follow-up.',
             'windows':sorted(by_key.values(),key=lambda item:(item['start'],item['end_exclusive']))})
        print(json.dumps(run),flush=True)
        if failures>=2:
            print('Two failed windows: stop this bounded attempt and retain remaining unattempted windows.',flush=True)
            break
        if i<len(ranges)-1 and stagger:time.sleep(stagger)
    return articles


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start',help='UTC date, inclusive')
    parser.add_argument('--end',help='UTC date, exclusive')
    parser.add_argument('--window-days',type=int,default=7)
    parser.add_argument('--directory',type=Path,default=Path('data/discovery'))
    args=parser.parse_args()
    end=dt.datetime.fromisoformat(args.end).replace(tzinfo=dt.timezone.utc) if args.end else dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    start=dt.datetime.fromisoformat(args.start).replace(tzinfo=dt.timezone.utc) if args.start else end-dt.timedelta(days=1)
    if start>=end or args.window_days<1:parser.error('Valid positive window and start before end required')
    collect(args.directory,start,end,args.window_days)
