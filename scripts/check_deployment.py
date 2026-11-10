#!/usr/bin/env python3
"""Exercise a disposable deployed stack without touching real editorial data."""
import argparse
import datetime as dt
import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base',required=True)
parser.add_argument('--disposable-test-database',action='store_true',required=True)
args=parser.parse_args()
base=args.base.rstrip('/')
token=os.environ['WORLDWAR_EDITOR_TOKEN']

def request(path,body=None,authorized=False,expected=200):
    headers={'Content-Type':'application/json'}
    if authorized:headers['Authorization']='Bearer '+token
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=60) as response:
            status=response.status;content=response.read()
    except urllib.error.HTTPError as error:
        status=error.code;content=error.read()
    assert status==expected,(path,status,content[:250])
    return json.loads(content)

assert request('/api/v1/health')['status']=='ok'
public=request('/api/v1/snapshot')
retired=public.get('tombstones',[])
def identities(kind):
    return {r['id'] for r in public[kind]} | {t['record']['id'] for t in retired if t['kind']==kind}
legacy=json.loads((Path(__file__).resolve().parents[1]/'data/map_data.json').read_text())
assert {r['id'] for r in legacy['nodes']} <= identities('actors')
assert {r['id'] for r in legacy['edges']} <= identities('relationships')
assert len(identities('contests'))>=470
request('/api/v1/editor/records',expected=401)
sid='synthetic-deployment-'+uuid.uuid4().hex[:12]
source={'id':sid,'title':'Synthetic deployment fixture','url':'https://example.org/test',
    'publisher':'Synthetic fixture','source_type':'primary','published_at':None,
    'retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat(),'rights':'Synthetic fixture only',
    'note':'Disposable CI source; not a real-world observation.'}
created=request('/api/v1/editor/records/sources',{'record':source,'reason':'Disposable deployment validation'},True,201)
record=created.get('record',created)
request('/api/v1/records/sources/'+sid,expected=404)
request('/api/v1/editor/records/sources/'+sid+'/publish',{'expected_revision':record['revision'],'reason':'Publish synthetic CI fixture'},True)
assert request('/api/v1/records/sources/'+sid)['record']['id']==sid
with urllib.request.urlopen(base+'/',timeout=30) as response:
    html=response.read().decode()
    assert response.status==200 and '<html' in html and '/assets/' in html
print('Deployment proof passed: live API snapshot, private draft isolation, authenticated publication, same-origin proxy and app entry point. Database dialect is verified separately by postgres_smoke.py.')
