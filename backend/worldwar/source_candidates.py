"""A domain-specific, durable source inbox with no factual publication path."""
from __future__ import annotations

import hashlib
import re
import uuid
from urllib.parse import urlsplit

from sqlalchemy import select

from .discovery import canonical_url, publication_date
from .importers import digest
from .models import CandidateIngestion, Job, Record
from .schemas import utc_now
from .service import ServiceError, create_draft, key


def ingest_source_candidates(factory, data, *, domain, adapter='source-candidates'):
    if not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,80}', adapter):
        raise ValueError('invalid adapter name')
    if domain not in ('protests', 'elections', 'conflicts'):
        raise ValueError('unknown source-candidate domain')
    job_id='source-inbox-'+uuid.uuid4().hex
    now=utc_now()
    with factory.begin() as session:
        session.add(Job(id=job_id,adapter=adapter,domain=domain,started_at=now,completed_at=None,
                        status='partial',fetched_count=0,accepted_count=0,error=None,
                        public_visible=False,note='Private source-candidate import; original collection health is imported separately'))
    rows=data.get('events',data.get('articles')) if isinstance(data,dict) else None
    if not isinstance(rows,list):
        with factory.begin() as session:
            job=session.get(Job,job_id);job.status='error';job.completed_at=utc_now();job.error='Source-candidate wrapper is invalid.'
        return dict(id=job_id,status='error',fetched_count=0,accepted_count=0,rejected_count=0)
    accepted,rejected=0,0
    for chunk_start in range(0,len(rows),200):
        with factory.begin() as session:
            for article in rows[chunk_start:chunk_start+200]:
                try:
                    with session.begin_nested():
                        if not isinstance(article,dict):
                            raise ValueError('candidate must be an object')
                        url=canonical_url(article.get('url',''))
                        known=session.scalar(select(CandidateIngestion).where(CandidateIngestion.canonical_url==url))
                        seen,_,_=publication_date(article.get('discovered_at') or article.get('first_seen_at') or now)
                        if seen is None:
                            raise ValueError('candidate discovery needs an exact timestamp when supplied')
                        if known:
                            known.last_seen_at=max(known.last_seen_at,seen)
                            p=dict(known.provenance)
                            p['candidate_domains']=sorted(set(p.get('candidate_domains',[]))|{domain})
                            known.provenance=p
                            continue
                        published,published_day,precision=publication_date(article.get('published_at'))
                        retrieved,_,_=publication_date(article.get('retrieved_at') or now)
                        title=article.get('headline') or article.get('title')
                        if not isinstance(title,str) or not title.strip():
                            raise ValueError('candidate title is missing')
                        hashed=hashlib.sha256(url.encode()).hexdigest()
                        source_id='candidate-source-'+hashed[:24]
                        if session.get(Record,key('sources',source_id)):
                            raise ValueError('candidate source identity collision')
                        payload=dict(id=source_id,title=title,url=url,publisher=article.get('source') or urlsplit(url).hostname,
                                     source_type='discovery',published_at=published,published_date=published_day,
                                     publication_precision=precision,retrieved_at=retrieved,
                                     retrieval_precision='timestamp' if retrieved else 'unknown',language=article.get('language') or article.get('lang'),
                                     rights='Metadata and original link only; linked publisher rights apply.',
                                     note=f'Unreviewed {domain} source candidate. No occurrence, action or factual claim is established.')
                        create_draft(session,'sources',payload,'Persist private source candidate for editorial review')
                        provenance={k:article[k] for k in ('provider','provider_seen_raw','date_basis','legacy_published_at','first_repository_revision','retrieved_at') if k in article}
                        provenance['candidate_domains']=[domain]
                        session.add(CandidateIngestion(id=hashed,adapter=adapter,external_id=str(article.get('id') or source_id),
                            canonical_url=url,content_sha256=digest(payload),first_seen_at=seen,last_seen_at=seen,
                            source_published_at=published,provenance=provenance,record_key=key('sources',source_id),job_id=job_id))
                        accepted+=1
                except (ValueError,TypeError,KeyError,ServiceError):
                    rejected+=1
    with factory.begin() as session:
        job=session.get(Job,job_id)
        job.status='partial' if rejected else 'ok';job.completed_at=utc_now()
        job.fetched_count=len(rows);job.accepted_count=accepted
        job.error=f'{rejected} invalid source candidate(s) rejected.' if rejected else None
    return dict(id=job_id,status='partial' if rejected else 'ok',fetched_count=len(rows),accepted_count=accepted,rejected_count=rejected)
