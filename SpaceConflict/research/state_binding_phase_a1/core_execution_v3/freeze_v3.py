"""Freeze only researcher-verified shared worlds; no predictions used for eligibility."""
from v3common import *
from review_v3 import CHECKS


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    review=csvrows(root/'review/researcher_records.csv')
    manifest=load(root/'review/review_bundle_manifest.json')
    original={r['group_id']:r for r in manifest['records']}
    if len(review)!=16 or len({r['group_id'] for r in review})!=16: raise ValueError('REVIEW_GROUPS_CHANGED')
    if sha(root/'review/draft_requests.jsonl')!=manifest['request_file_sha256']: raise ValueError('DRAFT_CHANGED_AFTER_REVIEW')
    if sha(root/'private_gold/core_draft.jsonl')!=manifest['private_gold_sha256']: raise ValueError('GOLD_CHANGED_AFTER_REVIEW')
    verified={}; exclusions=[]
    for row in review:
        before=original[row['group_id']]
        for k in ['group_id','world_id','underlying_world_id','stratum','level','presentation_hash','review_bundle_sha256']:
            if row[k]!=before[k]: raise ValueError('REVIEW_IDENTITY_OR_HASH_CHANGED:'+k)
        if row['stratum']=='L4_BINARY_RELATION_SECONDARY':
            exclusions.append(dict(group_id=row['group_id'],reason='DEFERRED_REFERENCE_FRAME')); continue
        if row['new_review_status']!='VERIFIED_FOR_A1':
            exclusions.append(dict(group_id=row['group_id'],reason=row['new_review_status'])); continue
        if not row['reviewer_name'].strip() or not row['reviewed_at'].strip(): raise ValueError('RESEARCHER_IDENTITY_TIME_MISSING')
        date=datetime.fromisoformat(row['reviewed_at'].replace('Z','+00:00'))
        if date.tzinfo is None: raise ValueError('REVIEW_TIMEZONE_MISSING')
        for k in CHECKS:
            allowed=['TRUE']+(['NOT_APPLICABLE'] if k=='action_amount_confirmed' and row['level']=='L1' else [])
            if row[k] not in allowed: raise ValueError('MISSING_RESEARCHER_CHECK:'+row['group_id']+':'+k)
        verified[row['group_id']]=row
    if not any(r['level']=='L4' for r in verified.values()): raise ValueError('NO_VERIFIED_L4_COUNT_WORLDS')
    req=list(rows(root/'review/draft_requests.jsonl')); truth={g['request_id']:g for g in rows(root/'private_gold/core_draft.jsonl')}
    selected=[]
    for r in req:
        rr=verified.get(r['group_id'])
        if not rr: continue
        excluded=set(x.strip() for x in rr['conditions_not_eligible'].split(';') if x.strip())
        known={q['condition'] for q in req if q['group_id']==r['group_id']}
        if excluded-known: raise ValueError('UNKNOWN_CONDITION_EXCLUSION')
        if r['condition']=='POST_NO_MEDIA' and rr['post_no_media_witnesses_confirmed']!='TRUE': excluded.add('POST_NO_MEDIA')
        if r['condition'] in excluded:
            exclusions.append(dict(group_id=r['group_id'],request_id=r['request_id'],reason='RESEARCHER_CONDITION_NOT_ELIGIBLE')); continue
        selected.append(r)
    if a.dry_run: print(json.dumps(dict(status='REVIEW_VALID_NOT_FROZEN',worlds=len(verified),requests_per_model=len(selected)))); return
    compute()
    if load(root/'reports/gpu_engineering.json')['status']!='PASS': raise ValueError('GPU_END_TO_END_NOT_PASSED')
    auth=load(root/'resources/core_authorization.json')
    if not auth.get('approved') or auth['run_id']!=c['run_id']: raise ValueError('CORE_GPU_BUDGET_MISSING')
    save(root/'inputs/core/requests.jsonl',selected,'jsonl')
    save(root/'private_gold/core.jsonl',[truth[r['request_id']] for r in selected],'jsonl')
    (root/'private_gold/core.jsonl').chmod(0o600)
    save(root/'manifest/core_exclusions.json',exclusions)
    csvsave(root/'manifest/researcher_review_frozen.csv',review)
    save(root/'manifest/core_lock.json',dict(status='CORE_FROZEN_VERIFIED_FOR_A1',run_id=c['run_id'],
         requests_per_model=len(selected),inputs_sha256=sha(root/'inputs/core/requests.jsonl'),
         config_sha256=sha(a.config),review_sha256=sha(root/'review/researcher_records.csv'),code=code_entries(c),
         resource_authorization_sha256=sha(root/'resources/core_authorization.json'),
         worlds=list(verified),models=c['models'],selection='REVIEW_ONLY_NO_PREDICTION_BASED_SELECTION'))
    print(json.dumps(dict(status='CORE_FROZEN_VERIFIED_FOR_A1',worlds=len(verified),requests_per_model=len(selected))))


if __name__=='__main__': main()
