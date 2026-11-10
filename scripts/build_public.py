#!/usr/bin/env python3
"""Rebuild the deliberate public snapshot from versioned, public inputs only."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    destination=ROOT/'web/public/data'
    destination.mkdir(parents=True,exist_ok=True)
    # Do not read WORLDWAR_DATABASE_URL or the owner's private store during a
    # public build. Only explicitly versioned publication inputs are eligible.
    with tempfile.TemporaryDirectory(prefix='worldwar-public-') as temporary:
        url='sqlite:///'+str(Path(temporary)/'research.db')
        env={**os.environ,'PYTHONPATH':str(ROOT/'backend')}
        env.pop('WORLDWAR_EDITOR_TOKEN',None)
        def cli(*args):
            subprocess.run([sys.executable,'-m','worldwar.cli','--database-url',url,*map(str,args)],cwd=ROOT,env=env,check=True)
        cli('migrate','--legacy','data/map_data.json','--seed','data/publication/seed.json')
        overrides=ROOT/'data/publication/official-results.json'
        if overrides.exists() and json.loads(overrides.read_text()).get('contests'):
            cli('import-official-results','--input',overrides,'--publish-official-results')
        archive=ROOT/'data/discovery/archive.json'
        if archive.exists():
            cli('ingest-discovery','--input',archive,'--adapter','gdelt','--publish-unreviewed')
        for path in ['data/discovery/runs.json','data/discovery/election-runs.json','data/discovery/protest-runs.json']:
            if (ROOT/path).exists():cli('import-jobs','--input',path)
        cli('apply-publication-actions','--input','data/publication/seed.json')
        cli('snapshot','--output',destination/'research.json')
    if archive.exists():shutil.copyfile(archive,destination/'discovery-metadata.json')
    # A compatibility archive is data, not a second active application.
    shutil.copyfile(ROOT/'data/map_data.json',destination/'legacy-conflict-records.json')
    print('Public data prepared from versioned inputs; private runtime store was not read.')


if __name__=='__main__':main()
