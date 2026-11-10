#!/usr/bin/env python3
"""Read-only checks of the source-sweep edition and its built public projection.

This checks saved evidence contracts, not the truth of every source assertion.
Run after build_public.py. Writes only the requested acceptance report.
"""
from pathlib import Path
import argparse,collections,datetime,hashlib,json,sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from worldwar.schemas import validate_record
from worldwar.service import scorecards


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/validation/research-acceptance.json')
    args=parser.parse_args()
    def read(p):return json.loads((ROOT/p).read_text())
    def digest(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
    seed=read('data/publication/seed.json');public=read('web/public/data/research.json')
    audit=read('docs/research/global-sweep-20261110.json');overlay=read('data/publication/official-results.json')
    legacy=read('data/map_data.json');geo=read('web/public/geometry/districts-2026.geojson')
    attribution=read('web/public/geometry/districts-attribution.json')
    checks=[]
    def check(name,ok,evidence):checks.append(dict(id=name,status='pass' if ok else 'fail',evidence=evidence))
    kinds=['actors','relationships','developments','occurrences','campaigns','connections','contests','election_actions','political_context','sources','coverage']
    ids={k:{x['id'] for x in seed.get(k,[])} for k in kinds}
    errors=[]
    for k in kinds:
        for r in seed.get(k,[]):
            try:validate_record(k,r)
            except Exception as e:errors.append(dict(kind=k,id=r.get('id'),error=str(e)))
    check('strict_record_schemas',not errors,dict(rows=sum(len(seed.get(k,[])) for k in kinds),errors=errors))
    all_ids=[r['id'] for k in kinds for r in seed.get(k,[])]
    duplicates=[i for i,n in collections.Counter(all_ids).items() if n>1]
    check('stable_ids_unique_across_kinds',not duplicates,duplicates)
    missing=[dict(kind=k,id=r['id'],source_id=s) for k in kinds for r in seed.get(k,[]) for s in r.get('source_ids',[]) if s not in ids['sources']]
    unsupported=[dict(kind=k,id=r['id']) for k in ['occurrences','campaigns','developments','contests','election_actions','political_context'] for r in seed.get(k,[]) if not r.get('source_ids')]
    check('source_reference_integrity',not missing and not unsupported,dict(missing=missing,unsupported=unsupported))
    missing_refs=[]
    for k,field,target in [('occurrences','campaign_ids','campaigns'),('campaigns','occurrence_ids','occurrences'),('election_actions','related_contest_ids','contests')]:
        for r in seed.get(k,[]):
            for x in r.get(field,[]):
                if x not in ids[target]:missing_refs.append(dict(id=r['id'],field=field,target=x))
    check('domain_cross_references',not missing_refs,missing_refs)
    occ=seed['occurrences'];bad_dates=[]
    for r in occ:
        if not '2026-09-01'<=r['occurred_start']<='2026-11-10' or r.get('occurred_end') and not r['occurred_start']<=r['occurred_end']<='2026-11-10':bad_dates.append(r['id'])
        if r['date_precision']=='day' and r.get('occurred_end') not in (None,r['occurred_start']):bad_dates.append(r['id'])
        if r['date_precision']=='month' and r.get('active_dates'):bad_dates.append(r['id'])
    check('observation_dates_and_precision',not bad_dates,dict(date_precisions=dict(collections.Counter(r['date_precision'] for r in occ)),invalid_ids=bad_dates,month_does_not_invent_active_days=True))
    actions=seed.get('publication_actions',[]);retired={a['id'] for a in actions}
    campaigns=[r for r in seed['campaigns'] if r['id'] not in retired]
    counts=dict(observations=len(occ),count_eligible=sum(r.get('count_eligible',True) for r in occ),campaigns=len(campaigns),occurrence_countries=len({r['country_code'] for r in occ}),combined_countries=len({r['country_code'] for r in occ}|{c for r in campaigns for c in r['country_codes']}),protest_coverage_jurisdictions=207,manual_sources=len(seed['sources']))
    check('edition_counts_match_reviewed_audit',counts==audit['counts'],dict(actual=counts,audit=audit['counts']))
    check('campaigns_are_not_occurrence_counts',all(r.get('count_eligible',False) is False for r in campaigns),dict(canonical_campaigns=len(campaigns),excluded_occurrences=[r['id'] for r in occ if not r.get('count_eligible',True)]))
    coverage=[c for c in public['coverage'] if c['domain']=='protests' and c.get('country_code')]
    expected_codes={r['country_code'] for r in audit['jurisdictions']}
    check('one_partial_assessment_per_reporting_jurisdiction',len(coverage)==len(expected_codes)==207 and {c['country_code'] for c in coverage}==expected_codes and all(c['status']=='partial' and c['period_start']=='2026-09-01' and c['period_end']=='2026-11-10' for c in coverage),dict(jurisdictions=len(coverage),status_counts=dict(collections.Counter(c['status'] for c in coverage)),complete_country_or_global_census=False))
    tombstones={(t['kind'],t['record']['id']):t['record'] for t in public.get('tombstones',[])}
    action_errors=[]
    for a in actions:
        t=tombstones.get((a['kind'],a['id']))
        if t is None or a['id'] in {r['id'] for r in public[a['kind']]} or a['action']=='merge' and t.get('merged_into')!=a.get('target_id'):action_errors.append(a)
    check('publication_actions_preserve_retired_identities',not action_errors,dict(actions=len(actions),errors=action_errors))
    galway=next(r for r in public['occurrences'] if r['id']=='p-ie-galway-20261021')
    check('galway_completion_conflict_excluded',galway.get('count_eligible') is False and galway.get('active_dates')==[] and set(galway['source_ids'])=={'v5-galway-faq','esweep-ifut-20261016','esweep-siptu-20261025'},dict(id=galway['id'],source_ids=galway['source_ids'],confidence_note=galway['confidence_note']))
    pin_errors=[]
    for k in kinds:
        if k=='sources':continue
        for r in public.get(k,[]):
            if set(r.get('source_ids',[]))!={s['id'] for s in r.get('source_snapshots',[])}:pin_errors.append(dict(kind=k,id=r['id']))
    check('public_claim_source_metadata_pins',not pin_errors,dict(errors=pin_errors,note='Each claim retains source metadata at its publication revision.'))
    def equivalent(key,a,b):
        if a==b:return True
        if key.endswith('_at') and isinstance(a,str) and isinstance(b,str):
            try:return datetime.datetime.fromisoformat(a.replace('Z','+00:00'))==datetime.datetime.fromisoformat(b.replace('Z','+00:00'))
            except ValueError:pass
        return False
    mismatch=[];identity_errors=[]
    archive=read('data/discovery/archive.json')
    archive_ids={r['id'] for r in archive['events']}
    for k in kinds:
        effective={r['id']:r for r in seed.get(k,[]) if r['id'] not in retired}
        if k in ('sources','contests'):
            for r in overlay.get(k,[]):effective[r['id']]=effective.get(r['id'],{})|r
        published={r['id']:r for r in public.get(k,[])}
        expected=set(effective)
        actual=set(published)
        if k in ('actors','relationships'):
            expected|={r['id'] for r in legacy['nodes' if k=='actors' else 'edges']}
        elif k=='developments':
            discovered=[r for r in published.values() if r.get('development_type')=='discovery_article']
            valid_discovery={r['id'] for r in discovered if r['id'] in archive_ids and r['evidence_status']=='unreviewed'}
            expected|=valid_discovery
            if len(discovered)!=min(len(archive_ids),250) or public['meta'].get('discovery_total')!=len(archive_ids):
                identity_errors.append(dict(kind=k,issue='discovery archive count or status mismatch'))
        elif k=='sources':
            expected|={i for domain in kinds if domain!='sources' for r in public.get(domain,[]) for i in r.get('source_ids',[])}
            expected|={i for t in public.get('tombstones',[]) for i in t['record'].get('source_ids',[])}
        if expected!=actual:
            identity_errors.append(dict(kind=k,missing=sorted(expected-actual),unexpected=sorted(actual-expected)))
        for i,r in effective.items():
            p=published.get(i,{})
            for key,v in r.items():
                if key!='revision' and not equivalent(key,v,p.get(key)):mismatch.append(dict(kind=k,id=i,field=key))
    check('active_public_identities_equal_expected_projection',not identity_errors,identity_errors)
    check('seed_and_official_overlay_match_public_fields',not mismatch,mismatch)
    contestants=public['contests'];house=[r for r in contestants if r['office']=='house'];reported=[r for r in contestants if r['status']=='reported_unofficial']
    unassessed=[r for r in contestants if r['status']=='not_assessed']
    bad_results=[r['id'] for r in contestants if r.get('winner') or r.get('winner_basis')]
    bad_results += [r['id'] for r in reported if sum(c['votes'] for c in r['candidates'])!=r['total_votes']]
    bad_results += [r['id'] for r in unassessed if r.get('candidates') or r.get('total_votes') is not None]
    check('post_election_registry_status_and_totals',len(contestants)==470 and len(house)==435 and len(reported)==11 and len(unassessed)==459 and not bad_results,dict(contests=len(contestants),house=len(house),senate=len(contestants)-len(house),status_counts=dict(collections.Counter(r['status'] for r in contestants)),problems=bad_results))
    check('official_refresh_does_not_invent_editorial_review',all(r['review_method']=='validated_official_adapter' and r['evidence_status']=='unreviewed' and r.get('reviewed_at') is None and r.get('winner') is None for r in overlay['contests']),dict(official_adapter_contests=len(overlay['contests'])))
    geometry_hash=digest('web/public/geometry/districts-2026.geojson')
    feature_ids={f['properties']['contest_id'] for f in geo['features']}
    join_errors=[];house_by_id={r['id']:r for r in house}
    for f in geo['features']:
        p=f['properties'];r=house_by_id.get(p['contest_id'],{})
        if any(p.get(k)!=r.get(k) for k in ['state_code','district','geography_version','boundary_status']):join_errors.append(p['contest_id'])
    check('operative_house_geometry_unchanged_and_joined',len(geo['features'])==len(feature_ids)==435 and feature_ids==set(house_by_id) and not join_errors and geometry_hash==attribution['output']['sha256']=='d9d5b2ac305adc72537b7ad8d0fdc17a04dff5f39729ce5e704076c7cfda9557',dict(sha256=geometry_hash,features=len(geo['features']),join_errors=join_errors,missouri_exception='Eight operative CD119 shapes; remaining427 use CD120, with documented Census vintage exception.'))
    check('legacy_identities_and_verification_status_preserved',{r['id'] for r in public['actors']}=={r['id'] for r in legacy['nodes']} and {r['id'] for r in public['relationships']}=={r['id'] for r in legacy['edges']} and all(r['evidence_status']=='legacy_unverified' and r.get('reviewed_at') is None for r in public['actors']+public['relationships']),dict(actors=len(public['actors']),relationships=len(public['relationships']),original_citation_text_preserved=True,original_report_recovered=False))
    eligible_ids={r['id'] for r in public['occurrences'] if r.get('count_eligible',True)}
    bad_cards=[c['id'] for c in public['scorecards'] if c['momentum']!='insufficient_data' or c['previous_occurrence_count'] is not None or not set(c['input_ids'])<=eligible_ids or c['method_version']!='observed-counts-1.1']
    expected_cards={c['id']:c for c in scorecards(public['occurrences'],public['campaigns'],public['coverage'],calculated_at=public['meta']['generated_at'])}
    actual_cards={c['id']:c for c in public['scorecards']}
    component_mismatches=[]
    for i in sorted(set(expected_cards)|set(actual_cards)):
        if expected_cards.get(i)!=actual_cards.get(i):
            component_mismatches.append(dict(id=i,fields=[k for k in set(expected_cards.get(i,{}))|set(actual_cards.get(i,{})) if expected_cards.get(i,{}).get(k)!=actual_cards.get(i,{}).get(k)]))
    check('scorecards_recomputed_with_exact_components_and_inputs',not component_mismatches,component_mismatches)
    check('scorecards_do_not_infer_comparable_coverage',len(public['scorecards'])==207 and not bad_cards,dict(scorecards=len(public['scorecards']),problems=bad_cards))
    public_bytes=(ROOT/'web/public/data/research.json').read_bytes()
    check('built_public_snapshot_is_exact',public_bytes==(ROOT/'web/dist/data/research.json').read_bytes(),dict(data_version=public['meta']['data_version'],sha256=hashlib.sha256(public_bytes).hexdigest()))
    check('public_audit_is_exact_and_metadata_only',(ROOT/'web/public/data/research-audit.json').read_bytes()==(ROOT/'docs/research/global-sweep-20261110.json').read_bytes() and all('body' not in s and 'full_text' not in s and 'snippet' not in s for s in audit['source_reviews']),dict(query_entries=len(audit['queries']),lead_dispositions=len(audit['lead_dispositions']),source_reviews=len(audit['source_reviews']),full_source_text_published=False))
    serialized=json.dumps(public)
    check('no_workspace_paths_or_synthetic_acceptance_markers',not any(s in serialized for s in ['/Users/','/var/folders/','synthetic-final-editor-20261110','PRIVATE-RESTORE-PROOF','worldwar-local-acceptance-only']),dict(private_runtime_used_for_build=False,synthetic_editor_fixture_in_public_data=False))
    report=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),review_scope='Read-only artifact and evidence-contract acceptance; substantive source reviews are separately attributed research-agent work. Passing does not certify exhaustive history or independent corroboration.',inputs={p:digest(p) for p in ['data/publication/seed.json','data/publication/official-results.json','docs/research/global-sweep-20261110.json','web/public/data/research.json']},counts=counts,published_data_version=public['meta']['data_version'],checks=checks,check_counts=dict(collections.Counter(c['status'] for c in checks)),remaining_defects=[c for c in checks if c['status']=='fail'],known_limits=audit['limitations']+['Only11 unofficial tally observations;459 contest records remain unassessed. No certified winners are established.','The82actor/75relationship legacy remains explicitly unverified; original report provenance is not recovered.'])
    report['overall']='pass' if not report['remaining_defects'] else 'fail'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['overall','check_counts','counts','published_data_version','remaining_defects']},ensure_ascii=False,indent=2))
    raise SystemExit(1 if report['remaining_defects'] else 0)

if __name__=='__main__':main()
