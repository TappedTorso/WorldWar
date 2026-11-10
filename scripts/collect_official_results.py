#!/usr/bin/env python3
"""Refresh explicitly supported official result feeds, retaining previous snapshots.

Only Delaware's verified machine feed is currently enabled. Minnesota is a
reviewed manual snapshot: the normal HTTP endpoint returns an access challenge
on this host. This job neither bypasses it nor claims nationwide live coverage.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import hashlib
import json
import re
import urllib.request
from pathlib import Path
from discovery_store import atomic_json

URL='https://data.delaware.gov/resource/yg7x-kgjc.json?election_name=2026%20General%20Election&%24limit=2000'
OFFICES={'U.S. Senator':('e-de-senate-2026','senate',None),'Representative In Congress':('e-de-house-00-2026','house','00')}


def parse_delaware(rows):
    if not isinstance(rows,list) or len(rows)>=2000:
        raise ValueError('Result feed invalid or pagination limit reached')
    results={}
    for office,(identity,kind,district) in OFFICES.items():
        candidates=[]; as_of=set(); names=set()
        matching=[r for r in rows if r.get('office')==office]
        if len(matching)<2:
            raise ValueError('Missing expected federal candidate rows')
        for row in matching:
            if row.get('election_name')!='2026 General Election' or not str(row.get('electiondate','')).startswith('2026-11-03'):
                raise ValueError('Election identity does not match the enabled cycle')
            name=str(row.get('candidate_name','')).strip()
            if not name or name in names:raise ValueError('Missing or duplicate candidate identity')
            names.add(name)
            value=str(row.get('total_votes',''))
            if not re.fullmatch(r'\d+',value):raise ValueError('Invalid vote count')
            votes=int(value)
            components=[row.get(k) for k in ('machine_votes','absentee_votes','early_votes')]
            if all(v is not None for v in components):
                if any(not re.fullmatch(r'\d+',str(v)) for v in components) or sum(map(int,components))!=votes:
                    raise ValueError('Vote components do not reconcile')
            pct=float(row['percent_votes']) if row.get('percent_votes') is not None else None
            if pct is not None and not 0<=pct<=100:raise ValueError('Invalid percentage')
            candidates.append({'name':name,'party':row.get('party') or None,'votes':votes,'percentage':pct})
            if row.get('data_as_of'):as_of.add(row['data_as_of'])
        total=sum(c['votes'] for c in candidates)
        if total<=0:raise ValueError('Zero-only feed is not accepted as reported results')
        if len(as_of)!=1:raise ValueError('Missing or inconsistent source update time')
        for c in candidates:
            if c['percentage'] is not None and abs(c['percentage']-c['votes']/total*100)>0.1:
                raise ValueError('Candidate percentage disagrees with complete contest totals')
        results[identity]={'office':kind,'district':district,'candidates':candidates,'total_votes':total,'result_as_of_raw':next(iter(as_of))}
    return results


def collect(seed, output, runs_path, opener=urllib.request.urlopen, clock=lambda:dt.datetime.now(dt.timezone.utc)):
    now=clock().isoformat().replace('+00:00','Z')
    old=json.loads(output.read_text()) if output.exists() else {'schema_version':'1.0','sources':[],'contests':[]}
    run={'id':'delaware-official-'+now,'adapter':'delaware-socrata-2026','domain':'elections','started_at':now,
         'completed_at':None,'status':'error','fetched_count':0,'accepted_count':0,'error':None}
    try:
        request=urllib.request.Request(URL,headers={'User-Agent':'WorldWarResearch/2.0 (+https://github.com/TappedTorso/WorldWar)'})
        with opener(request,timeout=30) as response:
            raw=response.read(4_000_001)
        if len(raw)>4_000_000:raise ValueError('Source response too large')
        rows=json.loads(raw); results=parse_delaware(rows)
        registry={c['id']:c for c in seed['contests']}
        new_records=[]
        for identity,fields in results.items():
            record=copy.deepcopy(registry[identity])
            record.update(fields)
            record.update({'source_ids':['de-socrata-2026','de-unofficial'],'evidence_status':'unreviewed',
                'review_method':'validated_official_adapter','reviewed_at':None,'updated_at':now,
                'publication_status':'published','status':'reported_unofficial','winner':None,'winner_basis':None,
                'result_as_of':None,'summary':'Official-source unofficial tally snapshot. This automatic observation is not a certification or a winner call.',
                'reporting_note':'Source update '+fields['result_as_of_raw']+' (timezone unstated). Automatically validated official feed; not manually re-reviewed. Certification not established.'})
            new_records.append(record)
        sources=[copy.deepcopy(s) for s in seed['sources'] if s['id'] in {'de-socrata-2026','de-unofficial'}]
        for source in sources:
            if source['id']=='de-socrata-2026':
                source.update({'retrieved_at':now,'retrieval_date':now[:10],'retrieval_precision':'timestamp',
                    'reviewed_at':None,'content_sha256':hashlib.sha256(raw).hexdigest(),'source_type':'official'})
        records={r['id']:r for r in old['contests']};records.update({r['id']:r for r in new_records})
        all_sources={s['id']:s for s in old['sources']};all_sources.update({s['id']:s for s in sources})
        old={'schema_version':'1.0','sources':list(all_sources.values()),'contests':list(records.values())}
        run.update(status='ok',fetched_count=len(rows),accepted_count=len(new_records))
    except Exception as exc:
        # No source body, query, token or network response is written into public logs.
        run['error']=type(exc).__name__+': official result refresh failed validation or retrieval; previous snapshot retained'
    run['completed_at']=clock().isoformat().replace('+00:00','Z')
    atomic_json(output,old)
    runs=json.loads(runs_path.read_text()) if runs_path.exists() else []
    atomic_json(runs_path,runs+[run])
    return run


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=Path,default=Path('data/publication/seed.json'))
    parser.add_argument('--output',type=Path,default=Path('data/publication/official-results.json'))
    parser.add_argument('--runs',type=Path,default=Path('data/discovery/election-runs.json'))
    args=parser.parse_args()
    print(json.dumps(collect(json.loads(args.seed.read_text()),args.output,args.runs),indent=2))
