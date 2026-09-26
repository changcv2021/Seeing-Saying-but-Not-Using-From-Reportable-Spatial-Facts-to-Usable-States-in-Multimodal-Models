"""Preserve Phase A and freeze synthetic calibration before any real A1 outcomes."""
import shutil
from common import *
from interfaces import request

def main():
    a=arguments(__doc__).parse_args(); cfg,root=setup(a)
    if a.dry_run: print('PLANNED: preservation plus synthetic setup only'); return
    require_compute()
    old=Path(cfg['phase_a_root']); oldcode=Path(cfg['phase_a_code'])
    # Full Phase A namespace: raw, gold, scores, prompts, inputs, reports and media.
    targets=sorted(p for p in old.rglob('*') if p.is_file())
    targets+=sorted(p for p in oldcode.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    targets+=[Path(cfg['phase_a_csv'])]
    audit=[entry(p) for p in targets]
    save(root/'manifest/phase_a_files_before.jsonl',audit,'jsonl',frozen=True)
    save(root/'phase_a_preservation_check.json',dict(status='BASELINE_RECORDED_NOT_FINAL_CHECK',
        files=len(audit),manifest_sha256=sha(root/'manifest/phase_a_files_before.jsonl'),
        read_only_policy=True,old_scorer_not_rescored=True),frozen=True)
    for name in ['PROJECT_SPEC.md','AGENTS.md','datasets.yaml','SpaceConflict_PhaseA1_Codex_Work_Guide_CN.md']:
        p=Path(cfg['project'])/name; out=root/'reference'/name; out.parent.mkdir(parents=True,exist_ok=True)
        if out.exists() and sha(out)!=sha(p): raise ValueError('REFERENCE_CHANGED')
        if not out.exists(): shutil.copy2(p,out)
    save(root/'config_snapshot.json',cfg,frozen=True)
    inp=[]; gold=[]
    def add(group,cond,text,sch,value,**kw):
        r=request(cfg,group,cond,text,sch,level='SETUP_ONLY',state_dimension='SYNTHETIC',**kw)
        inp.append(r); gold.append(dict(request_id=r['request_id'],schema=sch,expected=value,
            provenance='DETERMINISTIC_EXPLICIT_SYNTHETIC_TABLE_NOT_BENCHMARK_GOLD'))
    tables=[(i,i+3,'count') for i in range(6)]+[('LEFT_OF','RIGHT_OF',['LEFT_OF','RIGHT_OF']),('BELOW','ABOVE',['ABOVE','BELOW'])]
    for i,(pre,post,dom) in enumerate(tables):
        group=f'a1_setup_synthetic_{i:02d}'; vals={'PRE':pre,'POST':post}
        order=['PRE','POST'] if i%2==0 else ['POST','PRE']
        table='Explicit independent register table. Do not infer any change beyond the entries.\n'+'\n'.join(f'{t}: query_value = {json.dumps(vals[t])}' for t in order)
        for target in ['PRE','POST']:
            value=vals[target]; other='POST' if target=='PRE' else 'PRE'
            sch=dict(kind='value',domain=dom,nullable=False)
            suffix=f'\nReturn query_value for TARGET = {target}.'
            add(group,'S1_SINGLE_LOOKUP',f'Explicit table.\n{target}: query_value = {json.dumps(value)}'+suffix,sch,value,target=target)
            add(group,'S2_MULTI_SELECT' if target=='PRE' else 'S3_TARGET_FLIP',table+suffix,sch,value,target=target)
            sham='Explicit table.\n'+'\n'.join(f'{t}: '+(f'query_value = {json.dumps(value)}' if t==target else 'unrelated_register = "orange"') for t in order)
            add(group,'S4_SHAM',sham+suffix,sch,value,target=target)
            if dom=='count':
                replacement=max(pre,post)+2
                swap='Explicit independent register table.\n'+'\n'.join(f'{t}: query_value = {value if t==target else replacement}' for t in order)
                add(group,'S5_DISTRACTOR_REPLACEMENT',swap+suffix,sch,value,target=target,replacement=replacement)
            missing=f'Explicit table. Only the following entry is supplied.\n{other}: query_value = {json.dumps(vals[other])}'+suffix
            add(group,'S6_MISSING_TARGET',missing,dict(sch,nullable=True),None,target=target)
            claims=[value,vals[other]]+([max(pre,post)+1] if dom=='count' else [])
            for j,c in enumerate(claims):
                add(group,'S8_VERDICT',table+f'\nTARGET = {target}. Claim: target query_value equals {json.dumps(c)}.',
                    dict(kind='verdict'), 'SUPPORTED' if c==value else 'CONTRADICTORY',target=target,claim_type=['target','other','neither'][j])
        for keyorder in [['PRE','POST'],['POST','PRE']]:
            add(group,'S7_JOINT',table+'\nReport both named registers.',dict(kind='joint',domain=dom,nullable=False,keys=keyorder),vals,key_order=keyorder)
    for i in range(6):
        op='ADD' if i%2==0 else 'REMOVE'; category=['table','chair','lamp','stool','sofa','cabinet'][i]; amount=i//2+1
        text=f'Intervention: {op.lower()} exactly {amount} objects of category "{category}". Parse only this explicit intervention.'
        add(f'a1_setup_action_{i:02d}','S9_ACTION_PARSE',text,dict(kind='action'),dict(operation=op,target=category,amount=amount))
    assert len({r['request_id'] for r in inp})==len(inp)
    save(root/'inputs/setup_v1/requests.jsonl',inp,'jsonl',frozen=True)
    save(root/'gold/setup_v1.jsonl',gold,'jsonl',frozen=True)
    sources=[entry(p) for p in sorted((CODE/'src').glob('*.py'))]
    save(root/'manifest/setup_v1_lock.json',dict(status='FROZEN_BEFORE_CALIBRATION',
        requests=len(inp),worlds=len({r['group_id'] for r in inp}),
        inputs_sha256=sha(root/'inputs/setup_v1/requests.jsonl'),gold_sha256=sha(root/'gold/setup_v1.jsonl'),
        code=sources,config_sha256=sha(a.config),no_real_worlds_or_media=True,
        schema_gate_per_model_per_interface=cfg['schema_gate_minimum'],semantic_accuracy_not_a_prompt_selection_gate=True),frozen=True)
    save(root/'LIVE_STATUS.json',dict(status='SETUP_FROZEN_AWAITING_GPU_CALIBRATION',setup_requests_per_model=len(inp),mechanism_started=False))
    print(json.dumps(dict(status='PASS',preserved_files=len(audit),setup_requests_per_model=len(inp))))

if __name__=='__main__': main()
