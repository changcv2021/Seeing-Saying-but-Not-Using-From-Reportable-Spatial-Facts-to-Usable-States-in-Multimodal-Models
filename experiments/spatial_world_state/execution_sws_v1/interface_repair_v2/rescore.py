"""Versioned SWS rescoring: gold-blind views in a separate process, original scorers reused."""
import copy
import importlib
import io
import sys
import unittest
from collections import Counter,defaultdict
from pathlib import Path

REPAIR=Path(__file__).resolve().parent
sys.path.insert(0,str(REPAIR.parent))
from common_auto_v2 import *
from adapter import VERSION,RULES,normalize
from real_processor_v1 import verify
from e0_snapshot import interval

CASES={
    'D01':dict(batch='ca_source_d01_20260910',scorer='real_score_v1',table='all_physical_request_scores.csv',statistics='primary_statistics.csv',correct='content_correct'),
    'E7':dict(batch='e7_d01_v1_20260910',scorer='e7_score_v1',table='per_request_diagnostics.csv',statistics='grouped_statistics.csv',correct='correct'),
    'E9':dict(batch=None,scorer='score_e9_v1',table='all_request_scores.csv',statistics='primary_statistics.csv',correct='correct'),
}


def base(root):return root/'rescoring/interface_v2_20260910'


def folder(root,case):return root/'batches'/CASES[case]['batch'] if CASES[case]['batch'] else root


def snapshot(root,case,model):return base(root)/case/model/('snapshot_'+os.environ['SLURM_JOB_ID'])


def inputs(root,case,model):
    source=folder(root,case)
    if case=='E9':
        for r in rows(source/'public_inputs/E9/requests.jsonl'):
            yield r,source/'raw'/model/'records'/(r['request_id']+'.json')
    else:
        for sh in load(source/'manifest/shards.json'):
            for r in rows(sh['request_file']['path']):
                yield r,source/'raw'/model/f'shard_{sh["shard"]:03}'/'records'/(r['request_id']+'.json')


def lock_sources(c,root):
    paths={};code={}
    for case in CASES:
        source=folder(root,case)
        lock=source/'manifest/REQUEST_LOCK.json' if case!='E9' else root/'manifest/E9_request_lock.json'
        paths[str(lock)]=entry(lock);data=load(lock)
        verify(data.get('code',[])+data.get('private_inputs',[]))
        for ref in data.get('code',[]):code[ref['path']]=entry(ref['path'])
        for ref in data.get('private_inputs',[]):paths[ref['path']]=entry(ref['path'])
        if case=='E9':
            for p in (root/'private_gold/E9.jsonl',root/'matched/E9_structure.jsonl'):paths[str(p)]=entry(p)
        scores=source/'scores' if case!='E9' else root/'scores/E9'
        for p in scores.rglob('*'):
            if p.is_file() and p.suffix in ('.json','.jsonl','.csv','.md'):paths[str(p)]=entry(p)
    names=['adapter.py','test_adapter.py','rescore.py','job.sh']
    for name in names:code[str(REPAIR/name)]=entry(REPAIR/name)
    for name in ('contracts.py','common.py','common_auto_v2.py','review_policy_v2.py','config_auto_v2.json',
                 'real_processor_v1.py','real_design_v1.py','e7_design_v1.py','e0_snapshot.py','real_score_v1.py','e7_score_v1.py','score_e9_v1.py'):
        code[str(CODE/name)]=entry(CODE/name)
    pipeline=Path(c['project'])/'research/state_binding_phase_a1/core_execution_v3'
    for name in ('pipeline_v3.py','v3common.py'):code[str(pipeline/name)]=entry(pipeline/name)
    code[str(Path(c['package'])/'tools/research_utils.py')]=entry(Path(c['package'])/'tools/research_utils.py')
    return list(code.values()),list(paths.values())


def freeze(c,root):
    import test_adapter
    buf=io.StringIO();result=unittest.TextTestRunner(stream=buf,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_adapter))
    dest=base(root);save(dest/'tests'/('tests_'+os.environ['SLURM_JOB_ID']+'.txt'),buf.getvalue(),'text')
    if not result.wasSuccessful():raise RuntimeError(buf.getvalue())
    code,protected=lock_sources(c,root)
    data=dict(version=VERSION,created_at=now(),job_id=os.environ['SLURM_JOB_ID'],rules=RULES,models=c['models'],cases=list(CASES),
        code=code,protected_prior_files=protected,tests=result.testsRun,status='PASS',
        user_authorization='20260910_REQUEST_MODIFY_FORMAT_EFFECT_AND_RESCORE_WHERE_NEEDED',
        method_status='POSTHOC_INTERFACE_CORRECTION_NOT_ORIGINAL_PREREGISTERED_STRICT_SCORE',
        canonicalization_inputs=['raw_response_text','public_schema'],
        raw_mutation=False,gold_mutation=False,prompt_mutation=False,model_reruns=0,
        identical_policy_all_models_all_conditions=True,output_token_cap_unchanged=512,
        scientific_status='DISCOVERY_AUTO_ONLY_PROVISIONAL',
        schema_coverage=['COUNT_VALUE','YES_NO_NULL_VALUE','COUNT_FACTS_2','YES_NO_NULL_FACTS_2','COUNT_FACTS_4','JOINT_FACT_VERDICT','VERDICT'],
        regression_scope='CPU_PARSER_AND_NORMALIZER_NOT_A_NEW_MODEL_SMOKE')
    save(dest/'NORMALIZATION_LOCK.json',data);print(json.dumps(dict(stage='FREEZE',status='PASS',tests=result.testsRun,version=VERSION)),flush=True)


def canonicalize(c,root,a):
    lock=load(base(root)/'NORMALIZATION_LOCK.json');verify(lock['code'])
    sys.path.insert(0,str(Path(c['project'])/'research/state_binding_phase_a1/core_execution_v3'))
    from pipeline_v3 import install_gold_guard
    audit=install_gold_guard()
    dest=snapshot(root,a.batch,a.model);records=[]
    for r,path in inputs(root,a.batch,a.model):
        row=dict(request_id=r['request_id'],world_cluster_id=r['world_cluster_id'],schema=r['schema'],
            request_hash=r['model_independent_request_hash'],model=a.model,case=a.batch,status='NOT_RUN')
        if path.exists():
            raw=load(path)
            if raw['request_hash']!=r['model_independent_request_hash']:raise ValueError('RAW_REQUEST_HASH_MISMATCH')
            normalized=normalize(raw['raw_response'],r['schema'])
            row.update(status='RETURNED',original_raw=entry(path),raw_response=raw['raw_response'],
                lookup_key=digest([raw['raw_response'],r['schema']]),normalization=normalized,
                output_tokens=raw.get('output_tokens'),truncated=raw.get('truncated'),
                semantic_regeneration=False,scoring_view_not_a_model_response=True)
        records.append(row)
    save(dest/'canonical_views.jsonl',records,'jsonl')
    returned=[r for r in records if r['status']=='RETURNED']
    if audit['private_gold_open_attempts']:raise ValueError('NORMALIZER_OPENED_GOLD')
    save(dest/'CANONICALIZATION_ACCEPTANCE.json',dict(status='COMPLETE' if len(returned)==len(records) else 'PARTIAL',
        planned=len(records),returned=len(returned),gold_access_audit=dict(audit),job_id=os.environ['SLURM_JOB_ID'],
        views=entry(dest/'canonical_views.jsonl'),normalization_lock=entry(base(root)/'NORMALIZATION_LOCK.json'),
        strict_invalid=sum(r['normalization']['strict']['status']=='INVALID' for r in returned),
        normalized_invalid=sum(r['normalization']['normalized']['status']=='INVALID' for r in returned),
        changed=sum(r['normalization']['changed'] for r in returned)))
    print(json.dumps(dict(stage='GOLD_BLIND_CANONICALIZATION',case=a.batch,model=a.model,planned=len(records),returned=len(returned),gold_access_audit=audit)),flush=True)


def table(path):
    import csv
    with Path(path).open() as f:return list(csv.DictReader(f))


def boolean(value):return True if value=='True' else False if value=='False' else None


def run_legacy(c,root,a,mode,views):
    spec=CASES[a.batch];module=importlib.import_module(spec['scorer']);source=folder(root,a.batch)
    original=source/'scores'/a.model/('snapshot_'+os.environ['SLURM_JOB_ID']) if a.batch!='E9' else root/'scores/E9'/a.model
    target=snapshot(root,a.batch,a.model)/mode
    lookup={}
    for row in views:
        if row['status']!='RETURNED':continue
        value=row['normalization']['strict' if mode=='strict_replay' else 'normalized']
        key=row['lookup_key']
        if key in lookup and lookup[key]!=value:raise ValueError('NONDETERMINISTIC_SCORING_VIEW')
        lookup[key]=value
    def parser(text,schema):
        key=digest([text,schema])
        if key not in lookup:raise ValueError('RAW_NOT_IN_GOLD_BLIND_SNAPSHOT')
        return copy.deepcopy(lookup[key])
    def relocate(path):
        p=Path(path)
        try:return target/p.relative_to(original)
        except ValueError:raise ValueError('LEGACY_WRITE_OUTSIDE_NEW_SCORING_NAMESPACE:'+str(p))
    module.parse=parser
    module.save=lambda path,value,kind='json':save(relocate(path),value,kind)
    module.csvsave=lambda path,values,fields=None:csvsave(relocate(path),values,fields)
    def mapped_entry(path):
        try:p=target/Path(path).relative_to(original)
        except ValueError:p=Path(path)
        return entry(p)
    module.entry=mapped_entry
    previous=sys.argv
    sys.argv=[spec['scorer']+'.py','--config',str(a.config),'--run-id',a.run_id,'--seed',str(a.seed),'--model',a.model,'--resume']
    try:module.main()
    finally:sys.argv=previous
    return target


def score(c,root,a):
    locked=load(base(root)/'NORMALIZATION_LOCK.json');verify(locked['code']+locked['protected_prior_files'])
    dest=snapshot(root,a.batch,a.model);accepted=load(dest/'CANONICALIZATION_ACCEPTANCE.json');verify([accepted['views'],accepted['normalization_lock']])
    if accepted['gold_access_audit']['private_gold_open_attempts']!=0:raise ValueError('GOLD_BLINDNESS_FAILED')
    views=list(rows(dest/'canonical_views.jsonl'));raw_refs=[r['original_raw'] for r in views if r['status']=='RETURNED'];verify(raw_refs)
    strict_dir=run_legacy(c,root,a,'strict_replay',views)
    norm_dir=run_legacy(c,root,a,'normalized',views)
    spec=CASES[a.batch];before={r['request_id']:r for r in table(strict_dir/spec['table'])};after={r['request_id']:r for r in table(norm_dir/spec['table'])}
    if set(before)!=set(after) or set(before)!={r['request_id'] for r in views}:raise ValueError('SCORING_DENOMINATOR_CHANGED')
    differences=[];byworld=defaultdict(list);rules=Counter()
    for v in views:
        rid=v['request_id'];old=before[rid];new=after[rid]
        if old['execution_status']!=new['execution_status']:raise ValueError('EXECUTION_STATUS_CHANGED')
        was=boolean(old[spec['correct']]);got=boolean(new[spec['correct']]);returned=v['status']=='RETURNED'
        row=dict(request_id=rid,world_cluster_id=v['world_cluster_id'],case=a.batch,model=a.model,returned=returned,
            old_content_correct=was if returned else None,new_content_correct=got if returned else None,
            strict_schema_status=old['schema_status'],normalized_schema_status=new['schema_status'],
            correctness_changed=returned and was!=got,original_raw=v.get('original_raw'))
        if returned:
            row.update(operations=v['normalization']['operations'],canonical_text=v['normalization']['canonical_text'],raw_response=v['raw_response'])
            if v['normalization']['strict']['status']=='VALID' and (was!=got or v['normalization']['changed']):raise ValueError('ORIGINALLY_VALID_ANSWER_CHANGED')
            if was and not got:raise ValueError('NORMALIZATION_DESTROYED_PREVIOUSLY_CORRECT_CONTENT')
            for op in v['normalization']['operations']:rules[op['rule']]+=1
            byworld[v['world_cluster_id']].append(int(got)-int(was))
        differences.append(row)
    csvsave(dest/'per_request_score_changes.csv',differences)
    oldstats=table(strict_dir/spec['statistics']);newstats=table(norm_dir/spec['statistics'])
    def statkey(r):return tuple(r.get(k,'') for k in ('model_id','experiment','sample_family','family','condition','wording','metric','stratum'))
    oldgroups={statkey(r):r for r in oldstats};newgroups={statkey(r):r for r in newstats}
    if set(oldgroups)!=set(newgroups):raise ValueError('STATISTICAL_GROUPS_CHANGED')
    groupdiff=[]
    for key,old in oldgroups.items():
        new=newgroups[key]
        groupdiff.append(dict(group=list(key),old_estimate=old.get('estimate'),new_estimate=new.get('estimate'),
            estimate_changed=old.get('estimate')!=new.get('estimate'),old_ci95=[old.get('ci95_low'),old.get('ci95_high')],
            new_ci95=[new.get('ci95_low'),new.get('ci95_high')],worlds=new.get('worlds')))
    csvsave(dest/'grouped_metric_changes.csv',groupdiff)
    n=sum(r['returned'] for r in differences);oldcorrect=sum(r['old_content_correct'] is True for r in differences);newcorrect=sum(r['new_content_correct'] is True for r in differences)
    vals=[(w,sum(v),len(v)) for w,v in byworld.items()];lo,hi=interval(vals,c['seed'],5000)
    macrovals=[(w,sum(v)/len(v),1) for w,v in byworld.items()];mlo,mhi=interval(macrovals,c['seed'],5000)
    verify(locked['protected_prior_files']+locked['code']+raw_refs)
    report=dict(status='COMPLETE' if n==len(differences) else 'PARTIAL',case=a.batch,model=a.model,job_id=os.environ['SLURM_JOB_ID'],
        planned=len(differences),returned=n,worlds=len(byworld),strict_invalid=accepted['strict_invalid'],normalized_invalid=accepted['normalized_invalid'],
        format_recovered=sum(r['strict_schema_status']=='INVALID' and r['normalized_schema_status']=='VALID' for r in differences),
        old_content_correct=oldcorrect,new_content_correct=newcorrect,old_accuracy_returned=oldcorrect/n if n else None,new_accuracy_returned=newcorrect/n if n else None,
        accuracy_delta=(newcorrect-oldcorrect)/n if n else None,accuracy_delta_cluster_ci95=[lo,hi],
        world_macro_accuracy_delta=sum(v[1] for v in macrovals)/len(macrovals) if macrovals else None,world_macro_delta_ci95=[mlo,mhi],
        score_changed_requests=sum(r['correctness_changed'] for r in differences),changed_group_estimates=sum(r['estimate_changed'] for r in groupdiff),
        rule_applications=dict(rules),normalizer_gold_access_audit=accepted['gold_access_audit'],
        raw_and_historical_hashes_unchanged=True,protected_prior_files_checked=len(locked['protected_prior_files']),raw_files_checked=len(raw_refs),
        retained_response_regenerations=0,normalization_lock=entry(base(root)/'NORMALIZATION_LOCK.json'),
        method_status=locked['method_status'],scientific_grade='AUTO_ONLY_PROVISIONAL',
        overall_accuracy_is_descriptive_request_mix_not_full_benchmark=True,
        strict_results=str(strict_dir),normalized_results=str(norm_dir),per_request=entry(dest/'per_request_score_changes.csv'),
        grouped_changes=entry(dest/'grouped_metric_changes.csv'),canonical_views=entry(dest/'canonical_views.jsonl'))
    save(dest/'RESCORE_ACCEPTANCE.json',report)
    text=f'# {a.batch} / {a.model} 输出接口修复与重评分\n\n'
    text+=f'状态：{report["status"]}；{n}/{len(differences)} 条，{len(byworld)} world。\n\n'
    text+=f'格式无效：{report["strict_invalid"]} → {report["normalized_invalid"]}；内容完全答对：{oldcorrect} → {newcorrect}。\n\n'
    text+='相同原始回答、相同 gold、相同样本与统计程序；只替换经过无 gold 进程生成的解析视图。原结果和所有反例保留，没有模型重跑。\n\n'
    text+='这是用户授权的事后接口修正，不能写成原先预注册的严格 JSON 成绩；不是新推理或机制改善。总正确率仅为本批请求混合的描述，主要科学比较见 normalized 的分组与匹配统计。\n\n'
    text+='原始格式依从性仍使用 strict_replay；内容测量使用 normalized。未恢复字段仍无效，恢复为 null 不自动判正确。\n'
    save(dest/'rescore_report_cn.md',text,'text');print(json.dumps(report),flush=True)


def summary(c,root,a):
    dest=base(root);items=[];missing=[]
    for case in a.cases:
        for model in c['models']:
            reports=sorted((dest/case/model).glob('snapshot_*/RESCORE_ACCEPTANCE.json'),key=lambda p:int(p.parent.name.split('_')[-1]))
            if not reports:missing.append(dict(case=case,model=model,status='NOT_COMPLETED'));continue
            r=load(reports[-1]);r['report_ref']=entry(reports[-1]);items.append(r)
    name='SUMMARY_'+'_'.join(a.cases)+'_'+os.environ['SLURM_JOB_ID']
    save(dest/(name+'.json'),dict(status='COMPLETE' if not missing and all(r['status']=='COMPLETE' for r in items) else 'PARTIAL',results=items,missing=missing))
    text='# SWS 输出接口修复与重评分\n\n原始响应、旧分数、gold、提示和模型权重均未修改。下列为同一回答的统一格式归一化重评分，不是模型重跑。\n\n'
    text+='| 批次 | 模型 | 返回/计划 | world | 格式无效：原→新 | 内容完全答对：原→新 | 答对率：原→新 |\n|---|---|---:|---:|---:|---:|---:|\n'
    for r in items:
        old=f'{r["old_accuracy_returned"]:.2%}' if r['returned'] else 'NA';new=f'{r["new_accuracy_returned"]:.2%}' if r['returned'] else 'NA'
        text+=f'| {r["case"]} | {r["model"]} | {r["returned"]}/{r["planned"]} | {r["worlds"]} | {r["strict_invalid"]} → {r["normalized_invalid"]} | {r["old_content_correct"]} → {r["new_content_correct"]} | {old} → {new} |\n'
    text+='\n不同批次不得混为全 benchmark 分数。D01/E7 为 discovery，E9 为独立符号控制；模型之间使用同一规则。整体表是描述性请求混合，机制分析必须使用重新计算的分组结果、world 配对 CI 和匹配表。\n\n'
    text+='规则仅包含完整代码块包装、单个多余句号、已闭合值后的一个外层括号、允许空值位置中的字符串 null；拒绝重复键、补猜缺失值、在多份答案中选优、数值字符串转换。每条变换在 canonical_views 与 per_request_score_changes 中可追溯。\n\n'
    text+='归一化在独立进程完成，未打开 gold；后续才读取标准答案评分。修正规则为用户授权的事后接口版本，严格依从性仍单独保留。\n\n'
    for r in items:
        text+=f'- {r["case"]} / {r["model"]}：[{r["status"]}]({Path(r["report_ref"]["path"]).parent}/rescore_report_cn.md)，请求准确率差 {r["accuracy_delta"]}，world 聚类 95% CI {r["accuracy_delta_cluster_ci95"]}。\n'
    for r in missing:text+=f'- {r["case"]} / {r["model"]}：NOT_COMPLETED，不能当完成。\n'
    save(dest/(name+'.md'),text,'text');print(json.dumps(dict(status='COMPLETE' if not missing else 'PARTIAL',report=str(dest/(name+'.md')),results=len(items),missing=missing)),flush=True)


def main():
    p=arguments(__doc__);p.add_argument('--stage',required=True,choices=['freeze','canonicalize','score','summary'])
    p.add_argument('--batch',choices=list(CASES));p.add_argument('--model');p.add_argument('--cases',nargs='+',choices=list(CASES),default=['D01','E9'])
    a=p.parse_args();c,root=setup(a)
    if a.dry_run:print(json.dumps(dict(stage=a.stage,case=a.batch,model=a.model,new_root=str(base(root)),model_generations=0)));return
    if a.stage=='freeze':freeze(c,root)
    elif a.stage=='summary':summary(c,root,a)
    else:
        if a.model not in c['models'] or a.batch not in CASES:raise ValueError('SCOPE_NOT_ALLOWED')
        if a.stage=='canonicalize':canonicalize(c,root,a)
        else:score(c,root,a)


if __name__=='__main__':main()
