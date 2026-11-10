"""Resume a first-time store bootstrap without overwriting later editorial work."""
from pathlib import Path
import json
import os
import subprocess
import sys
from sqlalchemy import func, select
from worldwar.database import make_engine, migrate, sessions
from worldwar.models import ImportBatch, Record
from worldwar.schemas import utc_now

PREFIX='service-bootstrap-v1:'


def initialize(engine, root, runner=None):
    migrate(engine)
    factory=sessions(engine)
    def mark(session,name):
        session.add(ImportBatch(id=PREFIX+name,imported_at=utc_now(),kind='service_bootstrap',
                    counts={'completed':1},metadata_payload={'step':name}))
    with factory.begin() as session:
        if session.get(ImportBatch,PREFIX+'complete'):
            return 'Existing completed research store retained.'
        started=session.get(ImportBatch,PREFIX+'started')
        if not started:
            if session.scalar(select(func.count()).select_from(Record)):
                return 'Existing independently managed store retained; no bootstrap inputs reapplied.'
            mark(session,'started')
    if runner is None:
        def runner(*args):
            subprocess.run([sys.executable,'-m','worldwar.cli',*map(str,args)],check=True)
    steps=[('reviewed-baseline',('migrate','--legacy',root/'map_data.json','--seed',root/'publication/seed.json'))]
    official=root/'publication/official-results.json'
    if official.exists() and json.loads(official.read_text()).get('contests'):
        steps.append(('official-results',('import-official-results','--input',official,'--publish-official-results')))
    if (root/'discovery/archive.json').exists():
        steps.append(('discovery-archive',('ingest-discovery','--input',root/'discovery/archive.json','--adapter','gdelt','--publish-unreviewed')))
    if (root/'discovery/protest-candidates.json').exists():
        steps.append(('protest-inbox',('ingest-source-candidates','--input',root/'discovery/protest-candidates.json','--domain','protests')))
    for name in ['runs.json','election-runs.json','protest-runs.json']:
        if (root/'discovery'/name).exists():
            steps.append(('jobs-'+name,('import-jobs','--input',root/'discovery'/name)))
    steps.append(('publication-actions',('apply-publication-actions','--input',root/'publication/seed.json')))
    for name,args in steps:
        with factory() as session:
            completed=session.get(ImportBatch,PREFIX+name) is not None
        if completed:continue
        # The CLI transactions are idempotent. If the process stops between a
        # successful command and this checkpoint, retry safely reuses its work.
        runner(*args)
        with factory.begin() as session:mark(session,name)
    with factory.begin() as session:mark(session,'complete')
    return 'Initialized persistent research store; all bootstrap steps completed.'


if __name__=='__main__':
    engine=make_engine()
    try:print(initialize(engine,Path(os.environ.get('WORLDWAR_SEED_DIRECTORY','/data'))))
    finally:engine.dispose()
