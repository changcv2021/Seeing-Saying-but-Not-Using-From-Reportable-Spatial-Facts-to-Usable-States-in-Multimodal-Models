"""Fixed-category, seeded case extraction; preserves supporting and contrary cases."""
from base import *


def write_cases(cfg,root,per,controls,all_matches,measurement_items):
    byid={(r['model'],r['request_id']):r for r in per if r['correct'] is not None}
    groups=unique(rows(root/'manifest/discovery/state_group_manifest.jsonl'),'group_id') if per else {}
    complete=[r for r in per if r['correct'] is not None]
    candidates={name:[] for name in ['INPUT_INTERFACE_COUNTEREXAMPLE','LOCAL_FACT_REPORT_ERROR','POST_ERROR_WITH_PRE_REPORT_CORRECT',
        'REPORT_BINDING_SWAP','NONDEGENERATE_NON_TARGET_HIT','MATCHED_CONTROL_COUNTEREXAMPLE','LARGER_MODEL_MATCHED_SUCCESS','ANSWER_INTERFACE_CHANGE']}
    for r in measurement_items:
        if r['prediction']['status']=='INVALID' or r['prediction'].get('schema_warnings'):
            candidates['INPUT_INTERFACE_COUNTEREXAMPLE'].append(dict(key=r['model']+r['request_id'],evidence=[r['raw_path']],
                description='Preserved setup output-contract counterexample; not a discovery mechanism case.',request_id=r['request_id'],model=r['model'],phase=r.get('phase')))
    for r in complete:
        roles={s['alias']:s['role'] for s in groups.get(r['group_id'],{}).get('states',[])}
        category=None
        if r['condition']=='FACT_SEPARATE' and r['correct'] is False and r['prediction']['status']=='VALUE' and roles.get(r['target']) in ['PRE','OBJECT_SCOPE']:
            category='LOCAL_FACT_REPORT_ERROR'
        elif 'REPORT_BINDING_SWAP' in r['label_evidence']: category='REPORT_BINDING_SWAP'
        elif 'NON_TARGET_VALUE_HIT' in r['label_evidence'] and not r['gold'].get('domain',{}).get('binary_degenerate',True):
            category='NONDEGENERATE_NON_TARGET_HIT'
        if category:
            candidates[category].append(dict(key=r['model']+r['request_id'],evidence=[r['raw_path']],request_id=r['request_id'],model=r['model'],
                cluster_id=r['cluster_id'],description='Observed response only; independent derived-input review PROVISIONAL.',prediction=r['prediction'],gold=r['gold']))
        if r['condition']=='FACT_SEPARATE' and roles.get(r['target'])=='POST' and not r['correct'] and r['prediction']['status']=='VALUE':
            pre=next((s for s in complete if (s['model'],s['group_id'],s['condition'])==(r['model'],r['group_id'],'FACT_SEPARATE') and roles.get(s['target'])=='PRE'),None)
            if pre and pre['correct']:
                candidates['POST_ERROR_WITH_PRE_REPORT_CORRECT'].append(dict(key=r['model']+r['request_id'],evidence=[pre['raw_path'],r['raw_path']],
                    model=r['model'],request_id=r['request_id'],cluster_id=r['cluster_id'],description='Candidate to inspect update versus context effects, NOT certified STATE_COMPUTATION_CANDIDATE: complete premise coverage is not established.'))
        if r['model']=='qwen35_27b' and r['correct']:
            smaller=[byid.get((m,r['request_id'])) for m in cfg['models'][:2]]
            failed=[s for s in smaller if s and s['correct'] is False]
            if failed:
                candidates['LARGER_MODEL_MATCHED_SUCCESS'].append(dict(key=r['request_id'],request_id=r['request_id'],model=r['model'],cluster_id=r['cluster_id'],
                    evidence=[r['raw_path']]+[s['raw_path'] for s in failed],description='Same preselected request: 27B correct and at least one smaller model incorrect. This is a counterexample to a scale-universal failure claim.'))
    for r in controls:
        if r['primary_eligible'] and r['variant']=='base' and r['MULTI_hit']==r['SHAM_hit']:
            evidence=[x['raw_path'] for x in complete if (x['model'],x['group_id'],x['target'],x['variant'])==(r['model'],r['group_id'],r['target'],'base') and x['condition'] in ['G_MULTI_VALUE','G_SHAM_VALUE']]
            candidates['MATCHED_CONTROL_COUNTEREXAMPLE'].append(dict(key=r['model']+r['group_id']+r['target'],model=r['model'],cluster_id=r['cluster_id'],evidence=evidence,
                description='This pair does not show excess MULTI non-target-value hits relative to SHAM.',MULTI_hit=r['MULTI_hit'],SHAM_hit=r['SHAM_hit']))
    for r in all_matches:
        if r['comparison'] in ['VERDICT_to_ABC','VERDICT_to_semantic'] and r['net']:
            candidates['ANSWER_INTERFACE_CHANGE'].append(dict(key=r['model']+r['intervention_request_id'],model=r['model'],cluster_id=r['cluster_id'],
                evidence=[r['base_raw_path'],r['intervention_raw_path']],description='Correctness changes on a fixed label interface control; direction retained.',net=r['net'],comparison=r['comparison']))
    chosen=[]; text='# Phase A 案例与反例\n\n每个预定类别最多 2 个，按固定 seed=20260907 排序；没有该类就明确记录未观察到。原始响应和所有未选案例都未删除。候选不等于机制证明，派生输入仍 PROVISIONAL。\n\n'
    for category, cc in candidates.items():
        text+='## '+category+f'（候选 {len(cc)}）\n\n'
        if not cc:
            text+='NOT_OBSERVED / NOT_RUN：当前完整或已返回的记录中无合格案例；不是不存在这种失败的证明。\n\n'; continue
        for c in sorted(cc,key=lambda x:stable_rank(cfg['seed'],x['key']))[:2]:
            chosen.append(dict(category=category,**c))
            text+='- '+c['description']+'\n'
            text+='  '+json.dumps({k:v for k,v in c.items() if k not in ['description','evidence','key']},ensure_ascii=False)+'\n'
            for path in c['evidence']: text+='  证据：['+Path(path).name+'](<'+path+'>)\n'
            text+='\n'
    write(root/'examples_cn.md',text,'text')
    write(root/'scores/case_index.json',dict(selection='Fixed categories; seeded two per category; all raw retained',category_counts={k:len(v) for k,v in candidates.items()},cases=chosen))
