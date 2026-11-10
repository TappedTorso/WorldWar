#!/usr/bin/env python3
"""Recover metadata from repository history; never infer occurrence history."""
from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path
from discovery_store import atomic_json, merge_articles, normalize_article


def recover(repo: Path, since: str, output: Path):
    revisions = subprocess.check_output(['git','log','--reverse','--format=%H','--since='+since,'HEAD','--','data/events.json'],cwd=repo,text=True).splitlines()
    all_articles = []
    errors = []
    for revision in revisions:
        try:
            raw = subprocess.check_output(['git','show',revision+':data/events.json'],cwd=repo,stderr=subprocess.DEVNULL)
            data = json.loads(raw)
            meta = data.get('metadata', {})
            items = [normalize_article(a,provider=meta.get('provider','GDELT_DOC_API'),
                    retrieved_at=meta.get('generated_at_utc'),revision=revision) for a in data.get('events',[])]
            all_articles = merge_articles(all_articles, items)
        except (subprocess.CalledProcessError,ValueError,TypeError) as exc:
            errors.append({'revision':revision,'error':type(exc).__name__})
    payload = {'metadata': {'schema_version':'1.0','kind':'discovery_archive','history_since':since,
                'repository_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
                'snapshots_recovered':len(revisions)-len(errors), 'errors':errors,
                'article_count':len(all_articles),
                'note':'Recovered article metadata from Git snapshots, not a verified chronology. GDELT seen dates are discovery dates; missing history is not zero activity.'},
               'events':all_articles}
    atomic_json(output,payload)
    return payload['metadata']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--since',default='2026-09-01T00:00:00Z')
    parser.add_argument('--output',type=Path,default=Path('data/discovery/archive.json'))
    args=parser.parse_args()
    print(json.dumps(recover(Path(__file__).resolve().parents[1],args.since,args.output),indent=2))
