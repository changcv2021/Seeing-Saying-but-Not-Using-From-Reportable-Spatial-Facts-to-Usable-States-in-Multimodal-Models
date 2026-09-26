"""User-requested Phase 7 evidence snapshot. No new inference, no partial SELECT analysis."""
import gzip,shutil,zipfile,subprocess
from collections import defaultdict,Counter
from v2_common import *

def main():
    a=cli(__doc__).parse_args();context(a)
    stamp='snapshot_'+os.environ['SLURM_JOB_ID'];dest=ROOT/'review_packages'/stamp
    mirror=HERE.parent/('gpt_review_'+stamp);dest.mkdir(parents=True,exist_ok=True)
    captured=now();sources={};raw_index=[];activation_index={}
    def src(path):
        path=Path(path);ref=entry(path);sources[str(path)]=ref;return ref
    def copy(name,path):
        src(path);p=dest/name
        if p.exists():raise ValueError('REFUSE_PACKAGE_OVERWRITE:'+str(p))
        shutil.copyfile(path,p)
    def gz(name,data):
        if isinstance(data,str):data=data.encode()
        with (dest/name).open('xb') as f:f.write(gzip.compress(data,compresslevel=9,mtime=0))
    def readcsv(path):src(path);return csvrows(path)
    def readjson(path):src(path);return load(path)
    def csvbytes(rr):
        fields=list(dict.fromkeys(k for r in rr for k in r));s=io.StringIO();w=csv.DictWriter(s,fieldnames=fields,lineterminator='\n');w.writeheader()
        for r in rr:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})
        return s.getvalue()
    def decode(r):
        out={}
        for k,v in r.items():
            if v=='':out[k]=None
            elif v=='True':out[k]=True
            elif v=='False':out[k]=False
            elif isinstance(v,str) and (v.startswith('{') or v.startswith('[')):
                try:out[k]=json.loads(v)
                except json.JSONDecodeError:out[k]=v
            else:out[k]=v
        return out
    def ci_text(v):
        if v.get('mean') is None:return 'N/A'
        low,high=v.get('ci_low'),v.get('ci_high')
        return f'{v["mean"]:.3f} [{low:.3f}, {high:.3f}]' if low is not None else f'{v["mean"]:.3f} [CI不可估]'
    def statusrow(name,reason,state='NOT_RUN',**kw):return dict(module=name,status=state,reason=reason,**kw)

    # Freeze scheduler visibility at package start; submitted/running is not completed evidence.
    jobs=[load(p) for p in sorted((ROOT/'scheduler').glob('*.json')) if 'job_id' in load(p)]
    ids=sorted({r['job_id'] for r in jobs})
    sacct=subprocess.run(['sacct','-j',','.join(ids),'-X','-nP','--format=JobID,JobName%50,State,ExitCode,Elapsed'],capture_output=True,text=True,timeout=60)
    queue=subprocess.run(['squeue','-u','anonymous','-o','%.18i %.45j %.12T %.12M %R'],capture_output=True,text=True,timeout=45)
    queue_lines=queue.stdout.splitlines()
    scoped_queue='\n'.join(queue_lines[:1]+[line for line in queue_lines[1:] if line.split() and line.split()[0].split('_')[0] in ids])

    # W0 full cases; all counterexamples and numeric signature collisions retained.
    w0path=ROOT/'W0/W0_B1_CASE_MATRIX.csv';src(w0path);gz('02_W0_B1_CASE_MATRIX.csv.gz',w0path.read_bytes())
    w0=list(rows(ROOT/'W0/cases.jsonl'));src(ROOT/'W0/cases.jsonl');conditional=readcsv(ROOT/'W0/CONDITIONAL_METRICS.csv')
    errors=[];b1summary=[];cohorts=[]
    for r in w0:
        for c in ['b01','b06']:
            errors.append(dict(model=r['model'],world_cluster_id=r['world_cluster_id'],sequence=r['sequence_id'],condition=c.upper(),
                prediction=r[c+'_pred'],correct=r[c+'_correct'],parser=r[c+'_parser'],numeric_class=r[c+'_numeric_class'],
                all_matching_signatures=r[c+'_numeric_signatures'],cohorts=r['cohorts'],raw=r[c+'_raw']))
    csvsave(dest/'03_B01_B06_ERROR_PATTERNS.csv',errors)
    for m in MODELS:
        rr=[r for r in w0 if r['model']==m]
        for cond in ['b01','b02','b03','b05','b06','b07','b08','b09']:
            b1summary.append(dict(model=m,condition=cond.upper(),correct=sum(r[cond+'_correct'] is True for r in rr),
                **cluster_ci([dict(world_cluster_id=r['world_cluster_id'],value=int(r[cond+'_correct'] is True)) for r in rr])))
        for label in ['A','B','C','D','E']:
            cc=[r for r in rr if any(x.startswith(label+'_') for x in r['cohorts'])]
            cohorts.append(dict(model=m,cohort=label,sequences=len(cc),worlds=len({r['world_cluster_id'] for r in cc})))
        oldp=next((OLD_ROOT/'batches/B1/scores'/m).glob('snapshot_*/logical_scores.csv'))
        for r in readcsv(oldp):
            if r['condition'] in ['B00','B04','B13','B14']:continue
            raw_index.append(dict(module='W0_HISTORICAL_B1',model=m,request_id=r['request_id'],condition=r['condition'],world_cluster_id=r['world_cluster_id'],
                sequence=r['sequence'],raw_response=r['raw_response'],gold=decode(r)['expected'],prediction=decode(r)['prediction'],source_ref=decode(r)['raw'],status=r['execution_status']))
    csvsave(dest/'02a_W0_CONDITIONAL_METRICS.csv',conditional);csvsave(dest/'02b_W0_CONDITION_SUMMARY.csv',b1summary);csvsave(dest/'02c_W0_COHORT_COUNTS.csv',cohorts)

    # Completed behavior matrices + prompts; no image or checkpoint payloads copied.
    prompt_map={};behavior={};bsummaries={};bmatched=[];nmatched=[]
    for batch,filename in [('W1_TARGET','04_B2_TARGET_CONTRACT_RESULTS.csv'),('NONCOUNT','14_NONCOUNT_REPLICATION.csv')]:
        result=[];groups=[]
        for m in MODELS:
            path=next((ROOT/'batches'/batch/'scores'/m).glob('snapshot_*/DIAGNOSTIC_MATRIX.csv'))
            acc=readjson(path.parent/'ACCEPTANCE.json');assert acc['status']=='COMPLETE'
            rr=[decode(r) for r in readcsv(path)];result.extend(rr)
            groups.extend(readcsv(path.parent/'GROUP_RESULTS.csv'))
            for r in rr:
                raw_index.append(dict(module=batch,model=m,request_id=r['request_id'],world_cluster_id=r['world_cluster_id'],condition=r['condition'],
                    raw_response=r['raw_response'],gold=r['expected'],prediction=r['prediction'],source_ref=r['raw'],status=r['status']))
            if batch=='W1_TARGET':bmatched.extend(readcsv(path.parent/'MATCHED_CONTROLS.csv'))
            else:
                look={(r['world_cluster_id'],r['condition']):r for r in rr};worlds=sorted({r['world_cluster_id'] for r in rr})
                for right,left in [('EXPLICIT_S0','FULL_TRANSITION'),('EXPLICIT_S0','MATCHED_SHAM'),('MATCHED_SHAM','FULL_TRANSITION')]:
                    vals=[dict(world_cluster_id=w,value=int(look[w,right]['correct'])-int(look[w,left]['correct'])) for w in worlds]
                    nmatched.append(dict(model=m,contrast=right+' - '+left,**cluster_ci(vals)))
        csvsave(dest/filename,result);csvsave(dest/filename.replace('.csv','_SUMMARY.csv'),groups)
        behavior[batch]=result;bsummaries[batch]=groups
        path=ROOT/'batches'/batch/'public_inputs/requests.jsonl';src(path)
        for r in rows(path):prompt_map[r['request_id']]=dict(module=batch,**r)
    csvsave(dest/'04a_B2_MATCHED_CONTRASTS.csv',bmatched);csvsave(dest/'14a_NONCOUNT_MATCHED_CONTRASTS.csv',nmatched)
    # The state-collision-free denominator must be visible when discussing target selection.
    nongenerate=[]
    for m in MODELS:
        for condition in sorted({r['condition'] for r in behavior['W1_TARGET']}):
            rr=[r for r in behavior['W1_TARGET'] if r['model']==m and r['condition']==condition and r['s1']!=r['s2']]
            nongenerate.append(dict(model=m,condition=condition,subset='S1_NE_S2',programs=len(rr),correct=sum(r['correct'] for r in rr),
                **cluster_ci([dict(world_cluster_id=r['program_family'],value=int(r['correct'])) for r in rr])))
    csvsave(dest/'04b_B2_NONDEGENERATE_SUMMARY.csv',nongenerate)

    # I2 negative results and all missing probability/technical controls stay visible.
    copy('05_I2_LOGPROB_REANALYSIS.csv',ROOT/'W2/I2_LOGPROB_DIAGNOSTICS.csv')
    copy('05a_I2_GROUP_RESULTS.csv',ROOT/'W2/GROUP_RESULTS.csv')
    copy('05b_I2_MATCHED_SAME_TARGET.csv',ROOT/'W2/same_target_closure/MATCHED_CONTROL_RESULTS.csv')
    copy('05c_I2_TECHNICAL_GAPS.csv',ROOT/'W2/TECHNICAL_GAPS.csv')
    copy('05d_I2_TECHNICAL_FOLLOWUP.json',ROOT/'W2/technical_followup/ACCEPTANCE.json')
    i2=readjson(ROOT/'W2/I2_CLOSURE.json');i2closed=readjson(ROOT/'W2/same_target_closure/CLOSURE.json')
    i2src=OLD_ROOT/'i2_interchange_v1/reports/snapshot_8201958/ALL_RAW_RESPONSES.jsonl';src(i2src)
    for x in rows(i2src):
        r=x['record'];t=r['trial'];cs=r.get('candidate_scores',{})
        raw_index.append(dict(module='HISTORICAL_I2',trial_id=t['trial_id'],condition=t['control'],world_cluster_id=t['cluster_id'],status=r['status'],
            raw_response=r.get('response',{}).get('raw_response'),gold=x['gold'],baseline_response=x.get('baseline',{}).get('baseline',{}).get('raw_response'),
            candidate_logprobs={kind:{v['answer']:v['logprob'] for v in vals} for kind,vals in cs.items()},
            original_path=str(OLD_ROOT/'i2_interchange_v1/raw/qwen35_9b'/f'shard_{t["shard"]:03}/trials'/(t['trial_id']+'.json'))))

    # LOCALIZE is finalized. Partial SELECT outcomes are deliberately not read for this snapshot.
    i1=ROOT/'I1';loc=i1/'reports/localize/snapshot_8209203';accept=readjson(loc/'ACCEPTANCE.json');assert accept['finished_shards']==8
    path=loc/'DIAGNOSTIC_MATRIX.csv';src(path);local=[decode(r) for r in csvrows(path)];gz('07_I1_LOCALIZE_ALL.csv.gz',path.read_bytes())
    windows=readcsv(loc/'WINDOW_SUMMARY.csv');matched=readcsv(loc/'MATCHED_SPECIFICITY.csv');lock=readjson(i1/'selection/CANDIDATE_LOCK.json')
    copy('09_I1_MATCHED_EFFECTS.csv',loc/'WINDOW_SUMMARY.csv');gz('09a_I1_WORLD_MATCHED_EFFECTS.csv.gz',csvbytes(matched))
    copy('09b_FROZEN_LOCALIZE_CANDIDATES.json',i1/'selection/CANDIDATE_LOCK.json')
    tech=readjson(i1/'technical/qwen35_9b/TECHNICAL_ACCEPTANCE.json');audit=readjson(i1/'input_audit/ACCEPTANCE.json')
    tech['actual_processor_audit']=audit;tech['pair_specific_technical_gaps']=accept['counts'];save(dest/'06_I1_TECH_ACCEPTANCE.json',tech)
    panel=list(rows(i1/'public_inputs/panel.jsonl'));src(i1/'public_inputs/panel.jsonl');bycase={r['case_id']:r for r in panel}
    base_seen=set();local_extra=[]
    for k,r in enumerate(local):
        ref=r['raw'];check(ref);raw=load(ref['path']);t=raw['trial'];cs=raw.get('candidate_scores',{})
        raw_index.append(dict(module='I1_LOCALIZE',trial_id=r['trial_id'],case_id=r['case_id'],world_cluster_id=r['world_cluster_id'],status=r['status'],
            donor_kind=r['donor_kind'],raw_response=r['raw_response'],gold=r['gold'],prediction=r['prediction'],source_ref=ref,
            candidate_logprobs={kind:{v['answer']:v['logprob'] for v in vals} for kind,vals in cs.items()},score_only_values=raw.get('score_only_values')))
        for key in ['baseline_ref','donor_baseline_ref']:
            br=t.get(key)
            if not br or br['path'] in base_seen:continue
            check(br);b=load(br['path']);base_seen.add(br['path'])
            ar=b['activations'];activation_index[ar['path']]=dict(**ar,request_id=b['request_id'],baseline_ref=br,
                included_tensor_bytes=False,hash_origin='frozen baseline activation reference',rehash_at_packaging=False)
            raw_index.append(dict(module='I1_BASELINE',request_id=b['request_id'],status='RETURNED',source_ref=br,raw_response=b['baseline']['raw_response'],
                cached_response=b['cached']['raw_response'],noop_response=b['noop']['raw_response'],self_patch_response=b['self_patch']['raw_response'],
                equivalence_pass=b['equivalence_pass'],prompt=b['presentation']['rendered_prompt'],
                visual_hash=b['presentation']['presentation_hash'],anchors=b['presentation']['anchors']))
        if k%1000==0:print(json.dumps(dict(stage='PACKAGE_LOCALIZE',indexed=k)),flush=True)

    # Candidate free-generation effects; use baseline-conditional denominators, no zero-fill gaps.
    for win in lock['windows']:
        for cohort in ['A','B']:
            for donor in ['INFORMATIVE_S0','SAME_VALUE_SHAM','SUCCESS_DONOR']:
                allr=[r for r in local if int(r['depth'])==win['depth'] and r['anchor']==win['anchor'] and r['cohort']==cohort and r['donor_kind']==donor]
                rr=[r for r in allr if r['status']=='RETURNED'];parent={}
                def root(w):
                    parent.setdefault(w,w)
                    if parent[w]!=w:parent[w]=root(parent[w])
                    return parent[w]
                for r in rr:
                    w=r['world_cluster_id'];root(w)
                    if donor=='SUCCESS_DONOR':
                        d=bycase[r['case_id']]['success_donor_world']
                        if d:parent[root(d)]=root(w)
                for metric,eligible in [('rescue',[r for r in rr if not r['baseline_correct']]),('harm',[r for r in rr if r['baseline_correct']]),
                    ('donor_copy',[r for r in rr if r['donor_copy_identifiable']]),('delta_correct_lp',rr),('invalid',rr),('null',rr)]:
                    vals=[dict(world_cluster_id=root(r['world_cluster_id']),value=float(r[metric])) for r in eligible if r[metric] is not None]
                    local_extra.append(dict(depth=win['depth'],anchor=win['anchor'],cohort=cohort,donor=donor,metric=metric,
                        planned=len(allr),returned=len(rr),not_run=len(allr)-len(rr),independent_recipient_worlds=len({r['world_cluster_id'] for r in eligible}),
                        cluster_unit='donor_recipient_connected_component' if donor=='SUCCESS_DONOR' else 'recipient_world',**cluster_ci(vals)))
    csvsave(dest/'09c_I1_CANDIDATE_GENERATION_METRICS.csv',local_extra)

    # Required guide slots are present even when unfinished/ineligible. Do not read partial SELECT.
    waiting=statusrow('I1_SELECT','Frozen candidate validation is running; no finalized SELECT analysis included in this LOCALIZE snapshot.','RUNNING',
        job_id='8210757',final_analysis_job='8210758',metric=None)
    gz('08_I1_SELECT_ALL.csv.gz',csvbytes([waiting]))
    csvsave(dest/'10_I1_PROTECTION_COST.csv',[dict(waiting,module='I1_SELECTED_PROTECTION_AND_REVERSE',
        reason='Separate S0/protected/success/reverse controls running at two frozen windows; results not finalized; NOT zero damage.')])
    csvsave(dest/'11_I3_COMPONENT_RESULTS.csv',[statusrow('I3','SELECT GO prerequisite not yet established; no component localization results.',execution_eligibility='NOT_ELIGIBLE')])
    save(dest/'12_MECHANISM_LOCK.json',dict(status='NOT_ELIGIBLE',mechanism_locked=False,reason='Two LOCALIZE candidates are NOT a mechanism lock. SELECT and selective-protection evidence pending.',
        candidate_lock=src(i1/'selection/CANDIDATE_LOCK.json'),cross_scale_internal_inference='NOT_RUN'))
    csvsave(dest/'13_CROSS_SCALE_VALIDATION.csv',[statusrow('CROSS_SCALE_INTERNAL_'+m,'Mechanism lock absent; behavior comparisons are not internal mechanism validation.',execution_eligibility='NOT_ELIGIBLE') for m in ['qwen35_4b','qwen35_27b']])

    # Reviewable question texts and frozen decision rules, without bulky media.
    path=i1/'public_inputs/requests.jsonl';src(path)
    for r in rows(path):prompt_map[r['request_id']]=dict(module='I1',**r)
    oldp=OLD_ROOT/'batches/B1/public_inputs/requests.jsonl';src(oldp)
    need={r.get('request_id') for r in raw_index if r['module']=='W0_HISTORICAL_B1'}
    for r in rows(oldp):
        if r['request_id'] in need:prompt_map[r['request_id']]=dict(module='W0_HISTORICAL_B1',**r)
    protocols={name:readjson(p) for name,p in [('I1',i1/'manifest/PROTOCOL.json'),('I1_INPUT_LOCK',i1/'manifest/INPUT_LOCK.json'),
        ('W1',ROOT/'batches/W1_TARGET/manifest/PROTOCOL.json'),('NONCOUNT',ROOT/'batches/NONCOUNT/manifest/PROTOCOL.json'),('WORLD_PARTITION',ROOT/'W0/WORLD_PARTITION.json')]}
    gz('20_FROZEN_PROTOCOLS_AND_PROMPTS.json.gz',json.dumps(dict(protocols=protocols,requests=list(prompt_map.values())),ensure_ascii=False))
    copy('21_ORIGINAL_WORK_GUIDE_CN.md',GUIDE)
    gz('18_RAW_RESPONSE_INDEX.jsonl.gz',''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in raw_index))
    gz('19_ACTIVATION_INDEX.jsonl.gz',''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in activation_index.values()))
    save(dest/'17_EXECUTION_AND_SLURM.json',dict(snapshot_utc=captured,run_id=RUN,package_kind='INTERIM_LOCALIZE_REVIEW_NOT_FINAL',
        jobs=jobs,sacct=sacct.stdout,sacct_error=sacct.stderr,squeue=scoped_queue,squeue_error=queue.stderr,
        finalized_included=['W0','W1_ALL_THREE_MODELS','W2_REANALYSIS','NONCOUNT_ALL_THREE_MODELS','I1_LOCALIZE'],
        not_analyzed_in_this_package=['PARTIAL_SELECT','PARTIAL_PROTECTION','I3','CROSS_SCALE_INTERNAL'],
        source_root=str(ROOT),code_root=str(HERE),packaging_job=os.environ['SLURM_JOB_ID']))

    claims=[
        dict(id='C1',question='RQ1/RQ2',claim='独立视觉S0正确并不足以保证完整两步任务正确。',support='BEHAVIOR_SUPPORTED',
             conditions=['B02','B01','B05'],evidence=['02_W0_B1_CASE_MATRIX.csv.gz','02a_W0_CONDITIONAL_METRICS.csv','02c_W0_COHORT_COUNTS.csv'],
             limitations='独立请求不证明B01内部已存在正确S0；每world两序列相关；分类来自既有发现材料。'),
        dict(id='C2',question='RQ3',claim='显式初值救援与正确事实可报告之间存在行为差距；原B07不是S0位置匹配的sham。',support='BEHAVIOR_SUPPORTED_MECHANISM_UNRESOLVED',
             evidence=['02b_W0_CONDITION_SUMMARY.csv','20_FROZEN_PROTOCOLS_AND_PROMPTS.json.gz','14a_NONCOUNT_MATCHED_CONTRASTS.csv'],
             limitations='原B07提供S1且在A1之后；新版S0 sham用于I1，不能用旧B07直接证明S0角色特异性。'),
        dict(id='C3',question='RQ6',claim='B2 S1异常在一次冻结的语义问法和状态定义控制下消失，不支持把原异常直接称内部WSA。',support='TARGET_CONTRACT_EXPLANATION_SUPPORTED',
             samples='96 programs / 16 program families / model; three models',evidence=['04_B2_TARGET_CONTRACT_RESULTS.csv','04a_B2_MATCHED_CONTRASTS.csv','04b_B2_NONDEGENERATE_SUMMARY.csv'],
             limitations='不证明所有状态选择问题消失；4B/9B的S2问法反例仍在；不是新test。'),
        dict(id='C4',question='RQ7',claim='冻结I2单token S1 mapping没有得到argmax或稳定匹配概率证据支持。',support='SPECIFIC_MAPPING_NOT_SUPPORTED',
             samples='384 primary interventions / 16 pairs / 10 families',evidence=['05_I2_LOGPROB_REANALYSIS.csv','05b_I2_MATCHED_SAME_TARGET.csv','05d_I2_TECHNICAL_FOLLOWUP.json'],
             limitations='16技术控制仍未运行；部分同目标候选概率未保存；不等价于排除分布式/其他路径。'),
        dict(id='C5',question='RQ4/RQ5',claim='LOCALIZE存在两个按预定规则选出的候选，但选择性内部机制尚未验证。',support='EXPLORATORY_CANDIDATES_ONLY',
             samples='6144 planned / 5088 returned / 1056 not-run; main matched Type A 25 sequences / 20 worlds',
             evidence=['07_I1_LOCALIZE_ALL.csv.gz','09_I1_MATCHED_EFFECTS.csv','09b_FROZEN_LOCALIZE_CANDIDATES.json','09c_I1_CANDIDATE_GENERATION_METRICS.csv'],
             limitations='在32窗口中排序选出的区间未校正选择偏差；不得拿LOCALIZE区间当SELECT验证；缺失非随机，保护和反向结果未完。'),
        dict(id='C6',question='RQ8',claim='跨模型行为结果已完成；跨模型内部功能预测未运行。',support='INTERNAL_MECHANISM_NOT_RUN',
             evidence=['13_CROSS_SCALE_VALIDATION.csv','12_MECHANISM_LOCK.json'],limitations='不得将三模型行为实验冒充机制跨规模验证。'),
        dict(id='C7',question='RQ9',claim='显式初值相关行为差距也出现在本轮简单非计数坐标变换控制。',support='BOUNDED_BEHAVIOR_SUPPORTED',
             samples='47 independent source worlds; horizontal34/vertical6/depth7;188 requests/model',
             evidence=['14_NONCOUNT_REPLICATION.csv','14_NONCOUNT_REPLICATION_SUMMARY.csv','14a_NONCOUNT_MATCHED_CONTRASTS.csv'],
             limitations='二元关系、一次反射加identity；不是复杂运动/身份跟踪/一般3D状态机制；样本分布不平衡。')]
    save(dest/'15_CLAIM_EVIDENCE_MATRIX.json',dict(snapshot_utc=captured,scientific_status='PROVISIONAL_INTERIM',claims=claims))
    limitations='''# 局限、反例与不能得出的结论

1. 本包是阶段快照。SELECT/保护/反向干预正在运行，不读取或挑选其部分结果；文件08和10的占位不意味着模型返回0、也不意味着副作用为0。I3与跨规模内部验证尚不具备门槛。
2. 所有world是已有发现材料，新60/40仅是本轮干预选择分割，不能称完全未曝光confirmation/test。同world两序列不能当独立样本。
3. B02独立读对S0不证明B01内部已编码正确S0。B05强救援不能直接定位到视觉编码器、某层或特定token。
4. 历史B07是S1、位置在动作1之后，与B05的S0/动作前插入不匹配。新S0 sham明确同值同区域，但语义角色和token长度仍不同，未按成绩做padding搜索。
5. I1 LOCALIZE共6144计划项，5088真实返回，704缺少合格成功donor、352未通过引擎等价。缺项按原计划逐条保留，不能算模型错误，也不能静默缩成全覆盖面板。Type A配对分析只剩25序列/20world；原LOCALIZE Type A为30序列。
6. LOCALIZE从8深度×4锚点中按正均值选最多2个窗口，其95%区间是描述性、未按窗口选择校正。第二个候选区间跨0。任何正向结论均须等待SELECT和保护；不能因局部化弱就扩大层、anchor或pair扫描。
7. donor复用使样本相关。主informative-sham是同world配对；成功donor描述指标按donor/recipient连通分量聚类，小于2分量时不报告置信区间。未采集的效应不能当0。
8. I2原384主干预仍无CF命中；16项缓存/非缓存不等价复核后仍未运行。240个历史记录没有可用于同primary-CF的候选概率（包括未运行/未保存目标），只在实际保存且目标一致时计算匹配差。这个负结果仅限该mapping，不排除其他分布式机制。
9. B2状态语义控制恢复S1，但4B/9B部分S2条件仍失败；保留所有条件和退化数值。96程序来自16家族，置信区间按家族，不按96程序独立抽样。
10. 全对/全错时经验bootstrap会零宽，不代表总体概率确定。除SELECT预冻结的规则外，本包区间为探索性95% percentile cluster bootstrap（5000次、seed20260911），非普遍多重检验校正。
11. 非计数47world只含34水平、6垂直、7深度，执行单轴坐标反射后identity。它是二元关系行为控制，不验证复杂动作组合、真实多视图必要性、containment、身份跟踪或一般空间机制。坐标问法理解仍是竞争解释。
12. 研究者已豁免人工审核门槛；自动processor验收不等于代理自签人工VERIFIED。本包不含原图，GPT不能仅凭本包重新核实视觉gold；需要原图时按媒体路径/hash另行取证。
13. 外部GPT不能直接访问IU绝对路径。包内已保留逐样本预测原文、gold、实际提示与关键概率；绝对路径/hash是追溯索引，不是声称文件已完整上传。大型tensor只索引不打包。
14. 保留Type D（独立S0错但完整任务对）、4B显式S0不救援的Type E，以及所有负/零效应、null、invalid、技术不等价，不能仅叙述支持主故事的病例。
'''
    save(dest/'16_LIMITATIONS_AND_COUNTEREVIDENCE.md',limitations,'text')

    def b1(m,cond):return next(r for r in b1summary if r['model']==m and r['condition']==cond)
    def bg(batch,m,cond):
        r=next(r for r in bsummaries[batch] if r['model']==m and r['condition']==cond)
        return {k:(float(r[k]) if r.get(k) not in ['',None] else None) for k in ['mean','ci_low','ci_high']}
    def count_behavior(batch,m,cond):
        rr=[r for r in behavior[batch] if r['model']==m and r['condition']==cond]
        return f'{sum(r["correct"] for r in rr)}/{len(rr)}'
    def conditional_for(m,metric):
        r=next(r for r in conditional if r['model']==m and r['metric']==metric)
        return {k:float(r[k]) for k in ['mean','ci_low','ci_high']}
    report=['# SpaceConflict SSM NextStage v2：阶段审阅报告（非最终）','',f'快照时间（UTC）：{captured}。运行：`{RUN}`。',
        '', '**重要：文件名01_FINAL沿用指南清单，但本次是研究者要求的阶段交付，整阶段尚未完成。SELECT/保护正在运行，本包不提前读取其结果。**',
        '', '## 摘要与结论边界','', '当前最稳固的结论是两条行为发现：可报告初值不保证完整状态任务成功；原B2极端S1错误对目标问法高度敏感。I2冻结mapping未获支持；I1有探索性候选，但尚不能宣称找到选择性内部接口。',
        '', '完成：W0、三模型W1、W2重分析和固定一次技术复核、三模型非计数行为、I1 LOCALIZE。待完成：SELECT/保护/反向验证、条件性I3与机制锁后跨规模内部验证。',
        '', '## RQ1：模型能否独立获得正确初始空间事实？','', '条件B02；每模型160序列，80个world。下表以全部序列为分母，区间按world聚类。','',
        '| 模型 | B02正确 | 准确率与95% CI |','| --- | --- | --- |']
    for m in MODELS:report.append(f'| {m} | {b1(m,"B02")["correct"]}/160 | {ci_text(b1(m,"B02"))} |')
    report += ['', '事实提取并非全部成功，且这些是独立请求，不能把正确回答等同于B01内部使用了正确状态。证据：02、02b与18。',
        '', '## RQ2：独立可报告时，完整两步任务是否仍失败？','', '是。9B中B02正确的100条序列里，50条B01错误，并都被B05救回；它们构成Type A。',
        '三模型的病例与条件概率如下（Type A世界数不是总世界数）：','', '| 模型 | Type A序列/world | P(B01错｜B02对)，95% CI |','| --- | --- | --- |']
    for m in MODELS:
        cc=next(r for r in cohorts if r['model']==m and r['cohort']=='A')
        report.append(f'| {m} | {cc["sequences"]}/{cc["worlds"]} | {ci_text(conditional_for(m,"B01_WRONG_GIVEN_B02_CORRECT"))} |')
    report += ['', 'Type B、C、D、E和数值碰撞全部保留；不强行把预测值归为某个内部状态。证据：02、02a、02c、03。',
        '', '## RQ3：显式S0为何救援，是否超过同值无关sham？','', '行为上，9B B01=56/160，B05=160/160，B08纯符号=160/160，B09后缀=160/160；B06仅104/160。它说明初值条件强烈影响任务，不说明是哪一个内部模块失效。',
        '**不能直接用旧B07证明S0角色特异性**：旧B07含S1且位于A1后，本轮已新建动作前的S0同值sham。非计数中的角色匹配行为对照见RQ9；I1特异性与副作用仍待SELECT。证据：02b、20、09、14a。',
        '', '## RQ4：能否局部因果干预这个差距？','', f'尚未验证。9B LOCALIZE：64个Type A/B序列、{len({r["world_cluster_id"] for r in local})}个world，8深度×4锚点×3donor，6144计划项；5088返回，704缺合格成功donor，352引擎等价未通过。主Type A配对分析为25序列/20world。',
        '预冻结选择规则在32个窗口中选出以下两个候选。**这些区间来自用于选择窗口的LOCALIZE，不是独立确认。**','',
        '| block索引（从0开始） | 语义位置 | informative−sham Δlog P(correct) | 95%描述性CI | 序列/world |','| --- | --- | --- | --- | --- |']
    actual=readjson(i1/'raw/localize/shard_000/ENGINE.json')['actual_layers']
    for w in lock['windows']:
        s=w['localize'];report.append(f'| {actual[w["depth"]]} | {w["anchor"]} | {s["mean"]:.6f} | [{s["ci_low"]:.6f}, {s["ci_high"]:.6f}] | {s["sequence_pairs"]}/{s["worlds"]} |')
    report += ['', '效应单位是完整JSON候选的自然对数概率差（nats），不是准确率百分点。第二候选区间跨0；不按后续结果改窗口。每个窗口的自由生成救援、harm、复制、null/invalid及适用分母见09c，完整零/负窗口见09。',
        '', '## RQ5：修复是否选择性，是否复制答案或损害其他事实？','', '目前不能回答。独立S0、protected、原成功病例、反向B01→B05正在两个冻结窗口上运行（8210757，统计8210758）。局部概率改善不能代替自由生成救援，更不能代替保护验证。',
        '08和10保留RUNNING占位，不将未完成指标填0。若缺控制、世界不足或副作用大，不能判GO。证据：06、09c、10、17、20。',
        '', '## RQ6：B2是目标问法问题还是稳定状态读出失效？','', '这组冻结控制更支持目标问法/语义解释。每条件96程序、16程序家族；三模型同一批程序。S1结果如下：','',
        '| 模型 | T1索引 | T2时间语义 | T3状态定义 | T4重复目标 |','| --- | --- | --- | --- | --- |']
    for m in MODELS:report.append('| '+m+' | '+' | '.join(count_behavior('W1_TARGET',m,f'T{i}_S1') for i in range(1,5))+' |')
    report += ['', 'T2/T3/T4的S1全部正确，经验bootstrap区间退化为[1,1]，并不意味着总体成功率没有不确定性。4B/9B的S2条件仍有错误，不能只展示S1救援；全目标和非退化子集、配对差区间见04/04a/04b。此证据不能继续被当作内部Wrong-State Selection的充分证据。',
        '', '## RQ7：为什么I2单token互换没产生CF？概率证据如何？','',
        f'冻结主面板384干预、16pair、10家族：CF命中0/384。Δlog P(CF)均值{i2["primary_delta_cf_lp"]["mean"]:.6f}，95%家族聚类CI [{i2["primary_delta_cf_lp"]["ci_low"]:.6f}, {i2["primary_delta_cf_lp"]["ci_high"]:.6f}]。',
        '已有同目标匹配控制没有稳定正向对比；结论限于此单token mapping未获支持。不能证明S1不存在，也不能定位失败原因。固定一次技术复核仍有1个上下文缓存/非缓存输出不一致，原16条控制未补齐。未保存目标概率不补造。证据：05–05d、18。',
        '', '## RQ8：4B/27B有相同内部功能预测吗？','', '尚未测量。三模型W1与非计数行为已全部评分，但它们不等于机制跨规模验证；没有正式机制锁，故13为NOT_RUN/NOT_ELIGIBLE。只有SELECT和必要I3通过后才能按冻结功能预测验证，不按9B错题挑27B。',
        '', '## RQ9：是否超出count？','', '本轮存在非count行为差距，但结论必须限定为简单二元坐标变换。47个来源world（34水平、6垂直、7深度），每模型4条件共188条；动作是单轴反射后identity，不是复杂连续物理运动。','',
        '| 模型 | DIRECT_S0 | FULL_TRANSITION | EXPLICIT_S0 | MATCHED_SHAM |','| --- | --- | --- | --- | --- |']
    for m in MODELS:report.append('| '+m+' | '+' | '.join(count_behavior('NONCOUNT',m,c) for c in ['DIRECT_S0','FULL_TRANSITION','EXPLICIT_S0','MATCHED_SHAM'])+' |')
    report += ['', '配对特异性（EXPLICIT_S0−MATCHED_SHAM，单位为准确率差）：','']
    for m in MODELS:
        r=next(r for r in nmatched if r['model']==m and r['contrast']=='EXPLICIT_S0 - MATCHED_SHAM')
        report.append(f'- {m}：{ci_text(r)}，47个world，按world配对bootstrap。')
    report += ['', '不能据此称“一般3D空间世界状态机制”；坐标变换问法理解、二元接口与数字之外的状态绑定仍需区分。证据：14/14a/20。',
        '', '## 给GPT的下一步分析任务','', '先审查实验接口、分母、世界相关性与控制完整性，再讨论机制故事。当前应等待冻结SELECT/保护结果，不能根据LOCALIZE改提示或扩大扫描。',
        '请明确分开：已有行为证据、探索性局部概率线索、尚未运行/未完成的因果验证；指出哪些竞争解释仍未排除。不要把缺失当0、把正向LOCALIZE区间当确认、把跨模型行为当跨模型机制。',
        '', '## 追溯与复现','', f'原目录：`{ROOT}`；代码：`{HERE}`。完整sbatch命令与资源见17；提示、分区、预冻结门槛见20。计分复用既有gold-blind解析器，typed exact match；512 token上限，截断按保留内容计分，不自动判无效。',
        '18含原始文本、gold/预测、关键候选log-prob与原路径/hash；19仅激活索引。20包含真实英文题目和媒体引用；本包不上传原图和大型tensor，所以不能让GPT假称看过原图。',
        '本包所有CSV完整保留相应阶段计划项；大型表gzip压缩。先读00/01/15/16，再按证据索引抽查逐样本表，不必把所有行塞入上下文。']
    reporttext='\n'.join(report)+'\n';save(dest/'01_FINAL_SSM_REPORT_CN.md',reporttext,'text')
    start='''# 给GPT的阅读入口

这是SpaceConflict Phase7 / SSM NextStage v2的阶段审阅包，不是整阶段最终结果。01的FINAL文件名沿用指南；SELECT/保护还在运行。本包不含部分SELECT成绩，不能据此调整候选。

推荐顺序：

1. 01_FINAL_SSM_REPORT_CN.md：RQ1–RQ9、实际结果、关键分母与不确定性。
2. 15_CLAIM_EVIDENCE_MATRIX.json、16_LIMITATIONS_AND_COUNTEREVIDENCE.md：每条论断的证据和不可越过的边界。
3. 04、09、09c、14及其SUMMARY/配对表：行为控制、LOCALIZE与非计数。
4. 按需解压02/07/18/19/20的gzip，以request_id/trial_id定位具体原始响应、gold、英文提示、概率和来源；不要因为压缩就当数据缺失。

必须保留的尚未完成栏目：08/10=RUNNING，11/12/13=NOT_RUN或NOT_ELIGIBLE。它们不是0分、0副作用或否定结果。I1全计划6144条中有1056条未运行，原因逐行保留。

不提供模型权重、媒体图片、完整激活tensor、重复环境日志。18已含真实响应文本与关键候选概率；19只含路径/hash。外部GPT无法访问IU路径，不得假称查阅了未上传资产。

可以直接复制给GPT的指令：

> 请审阅这个SpaceConflict SSM v2阶段包。先读00、01、15、16，必要时用代码解压CSV.gz/JSONL.gz并按证据ID复核。严格区分独立S0事实报告、完整任务初值利用、目标问法、探索性局部干预和真正的留出验证。不要预设Wrong-State Selection或S1 carry-loss存在；不要把LOCALIZE选择后的区间当确认；不要用尚未完成的SELECT/保护占位推断效应。请给出：目前最稳固的发现、未排除的竞争解释、实现/统计风险、应等待哪些既定结果、以及不改冻结实验前提下的下一阶段决策建议。每个主要结论引用包内具体表和条件，附样本/world数、指标和不确定性。保留负结果与反例，不建议全层无界搜索或按成绩调提示。
'''
    save(dest/'00_START_HERE_CN.md',start,'text')
    save(dest/'22_SOURCE_MANIFEST.json',dict(snapshot_utc=captured,sources=list(sources.values()),packaging_code=entry(__file__),
        extraction_policy='Finalized W0/W1/W2/NONCOUNT/LOCALIZE only; full counters retained; no partial SELECT response reads.'))
    # Per-file integrity, required slots, decompression checks, ZIP roundtrip.
    required=['00_START_HERE_CN.md','01_FINAL_SSM_REPORT_CN.md','02_W0_B1_CASE_MATRIX.csv.gz','03_B01_B06_ERROR_PATTERNS.csv','04_B2_TARGET_CONTRACT_RESULTS.csv',
        '05_I2_LOGPROB_REANALYSIS.csv','06_I1_TECH_ACCEPTANCE.json','07_I1_LOCALIZE_ALL.csv.gz','08_I1_SELECT_ALL.csv.gz','09_I1_MATCHED_EFFECTS.csv',
        '10_I1_PROTECTION_COST.csv','11_I3_COMPONENT_RESULTS.csv','12_MECHANISM_LOCK.json','13_CROSS_SCALE_VALIDATION.csv','14_NONCOUNT_REPLICATION.csv',
        '15_CLAIM_EVIDENCE_MATRIX.json','16_LIMITATIONS_AND_COUNTEREVIDENCE.md','17_EXECUTION_AND_SLURM.json','18_RAW_RESPONSE_INDEX.jsonl.gz','19_ACTIVATION_INDEX.jsonl.gz']
    assert all((dest/f).is_file() for f in required)
    assert len(list(csv.DictReader(io.StringIO(gzip.decompress((dest/'07_I1_LOCALIZE_ALL.csv.gz').read_bytes()).decode()))))==6144
    assert len(list(csv.DictReader(io.StringIO(gzip.decompress((dest/'02_W0_B1_CASE_MATRIX.csv.gz').read_bytes()).decode()))))==480
    assert len(behavior['W1_TARGET'])==3456 and len(behavior['NONCOUNT'])==564
    for p in dest.glob('*.gz'):gzip.decompress(p.read_bytes())
    save(dest/'23_PACKAGE_ACCEPTANCE.json',dict(status='PASS_INTERIM_PACKAGE',guide_required_slots_present=True,W0_rows=480,W1_rows=3456,noncount_rows=564,
        I1_localize_counts=accept['counts'],raw_records=len(raw_index),activation_records=len(activation_index),
        partial_SELECT_responses_read=False,missing_and_counterexamples_retained=True,original_results_modified=False))
    save(dest/'SHA256SUMS.txt',''.join(f'{sha(p)}  {p.name}\n' for p in sorted(dest.iterdir()) if p.is_file()),'text')
    name=f'SpaceConflict_SSM_v2_20260911_phase7_{stamp}_REVIEW.zip';zpath=ROOT/'review_packages'/name
    with zipfile.ZipFile(zpath,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(dest.iterdir()):z.write(p,arcname=p.name)
    with zipfile.ZipFile(zpath) as z:
        assert z.testzip() is None
        for line in z.read('SHA256SUMS.txt').decode().splitlines():
            h,name2=line.split('  ',1);assert hashlib.sha256(z.read(name2)).hexdigest()==h
    shutil.copytree(dest,mirror)
    target=HERE.parent/name;shutil.copyfile(zpath,target);assert sha(target)==sha(zpath)
    report_target=HERE.parent/f'SpaceConflict_SSM_v2_阶段结果报告_{stamp}_CN.md';shutil.copyfile(dest/'01_FINAL_SSM_REPORT_CN.md',report_target)
    artifact=dict(status='PACKAGED_INTERIM_NOT_FINAL',zip=entry(target),persistent_zip=entry(zpath),report=entry(report_target),folder=str(mirror),snapshot_utc=captured)
    save(ROOT/'review_packages'/('ARTIFACT_'+stamp+'.json'),artifact);print(json.dumps(artifact,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
