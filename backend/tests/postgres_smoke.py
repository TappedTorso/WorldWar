"""Explicit live PostgreSQL integration proof, safe only in a disposable CI DB.

WORLDWAR_DATABASE_URL=postgresql+psycopg://... PYTHONPATH=backend python backend/tests/postgres_smoke.py
Creates a unique synthetic source and occurrence, publishes/corrects them,
verifies conflict protection and private/public separation, then restore proof.
Does not erase existing data. Requires --disposable-test-database acknowledgement.
"""
import argparse
import os
import uuid

from worldwar.database import make_engine, migrate, sessions
from worldwar.recovery import verify_restore
from worldwar.service import ServiceError, correct_draft, create_draft, editor_records, get_detail, publish
from worldwar.schemas import utc_now


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--disposable-test-database',action='store_true',required=True)
    parser.parse_args()
    url=os.environ.get('WORLDWAR_DATABASE_URL','')
    if not url.startswith(('postgresql://','postgresql+psycopg://','postgres://')):
        raise SystemExit('WORLDWAR_DATABASE_URL must name a disposable PostgreSQL database')
    engine=make_engine(url)
    migrate(engine)
    factory=sessions(engine)
    suffix=uuid.uuid4().hex[:12]
    sid='synthetic-source-'+suffix
    oid='synthetic-occurrence-'+suffix
    now=utc_now()
    with factory.begin() as session:
        s=create_draft(session,'sources',dict(id=sid,title='Synthetic integration fixture',url='https://example.org/test',
            publisher='Synthetic test publisher',source_type='primary',published_at=None,retrieved_at=now,
            rights='Synthetic fixture only',note='Not a real-world finding'),'PostgreSQL integration test')
        publish(session,'sources',sid,s['revision'],'Publish synthetic integration fixture')
        o=create_draft(session,'occurrences',dict(id=oid,title='Synthetic integration fixture',summary='Original synthetic summary',
            source_ids=[sid],evidence_status='reviewed',reviewed_at=now,country_code='ZZ',country='Synthetic fixture',
            place_name='Synthetic square',location_precision='city',occurred_start='2026-11-05',date_precision='day',
            action_type='demonstration',inclusion_rationale='Synthetic integration check'),'Create synthetic occurrence')
        original=publish(session,'occurrences',oid,o['revision'],'Publish synthetic observation')
    private_marker=f'Private correction marker {suffix} 100%_real'
    with factory.begin() as session:
        private=correct_draft(session,'occurrences',oid,dict(original,summary=private_marker),2,'Synthetic private correction')
    with factory() as session:
        assert get_detail(session,'occurrences',oid)['record']['summary']=='Original synthetic summary'
        assert get_detail(session,'occurrences',oid,private=True)['record']['summary']==private_marker
        page=editor_records(session,status='draft',kind='occurrences',q=private_marker,limit=1,offset=0)
        assert page['total']==1 and page['has_more'] is False
        assert page['items'][0]['record']['id']==oid and page['items'][0]['record']['revision']==3
        assert editor_records(session,status='draft',kind='sources',q=private_marker,limit=1,offset=0)['total']==0
    try:
        with factory.begin() as session:
            publish(session,'occurrences',oid,2,'Stale concurrent editor fixture')
    except ServiceError as exc:
        assert exc.status==409
    else:
        raise AssertionError('stale publication unexpectedly succeeded')
    with factory.begin() as session:
        published=publish(session,'occurrences',oid,private['revision'],'Publish synthetic correction')
        assert published['revision']==4
    report=verify_restore(engine)
    print({'status':'ok','dialect':engine.dialect.name,'immutable_revision':4,'restore':report})
    engine.dispose()


if __name__=='__main__':
    main()
