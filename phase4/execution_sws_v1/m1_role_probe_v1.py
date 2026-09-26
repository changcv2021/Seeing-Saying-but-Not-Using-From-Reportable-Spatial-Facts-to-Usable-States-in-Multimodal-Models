"""Bounded held-world-out role readability on existing M1 tensors, not a causal claim."""
import re
from collections import defaultdict
from common_auto_v2 import *
from real_processor_v1 import verify
from e0_snapshot import interval


def main():
    a=arguments(__doc__).parse_args();c,root=setup(a)
    src=root/'whitebox/M1_structural_d01_v1';dest=root/'whitebox/M1_role_probe_v1_20260910'
    locked=load(src/'manifest/M1_LOCK.json');verify(locked['code']+locked['public_inputs']+locked['private_inputs'])
    if load(src/'measurements/M1_ACCEPTANCE.json')['status']!='COLLECTION_COMPLETE':raise ValueError('M1_COLLECTION_INCOMPLETE')
    eligibility=load(src/'analysis/snapshot_8188410/probe_eligibility.json')
    if next(x for x in eligibility if x['variable']=='information_role')['status']!='PROBE_ELIGIBLE_NOT_YET_FIT':raise ValueError('ROLE_PROBE_NOT_ELIGIBLE')
    pairs=list(rows(src/'private_gold/neutral_candidate_sham_pairs.jsonl'))
    labels={r['request_id']:r for r in rows(src/'private_gold/measurement_labels.jsonl')}
    req={r['request_id']:r for r in rows(src/'public_inputs/requests.jsonl')}
    records=[]
    for pair in pairs:
        for key,role in [('neutral','NEUTRAL'),('false','CANDIDATE'),('sham','SHAM')]:
            rid=pair[key];lab=labels[rid];raw=load(src/'measurements/records'/(rid+'.json'))
            if lab['information_role']!=role or raw['status']!='MEASUREMENT_RECORDED' or not raw['hook_noop_pass']:raise ValueError('UNQUALIFIED_READOUT')
            verify([raw['hidden']])
            records.append(dict(label=lab,measurement=raw,request=req[rid],measurement_ref=entry(src/'measurements/records'/(rid+'.json'))))
    assert len(records)==60 and len({r['label']['world_cluster_id'] for r in records})==20
    train=[i for i,r in enumerate(records) if r['label']['internal_group_fold']!=0]
    val=[i for i,r in enumerate(records) if r['label']['internal_group_fold']==0]
    tw={records[i]['label']['world_cluster_id'] for i in train};vw={records[i]['label']['world_cluster_id'] for i in val}
    assert not(tw&vw) and len(tw)==14 and len(vw)==6
    positions=['observation_end','target_end','query_end','answer_start']
    env=load(src/'measurements/environment_8188409.json');n_layers=len(env['modules'])
    selected_layers=[0,(n_layers-1)//2,n_layers-1]
    protocol=dict(status='FROZEN_BEFORE_PROBE_FIT',model='qwen35_9b',variable='information_role',
        worlds=20,train_worlds=14,validation_worlds=6,requests=60,train_requests=len(train),validation_requests=len(val),
        positions=positions,layers=selected_layers,linear_algorithm='CENTERED_L2_NORMALIZED_DUAL_RIDGE_ONE_HOT',
        ridge_alpha=1.0,hyperparameter_search=False,random_label_repeats=5,seed=c['seed'],
        source_lock=entry(src/'manifest/M1_LOCK.json'),sources=[r['measurement_ref'] for r in records],
        selected_inputs=[entry(src/n) for n in ('public_inputs/requests.jsonl','private_gold/measurement_labels.jsonl','private_gold/neutral_candidate_sham_pairs.jsonl')],
        code=entry(__file__),claim_boundary='ROLE_READABILITY_NOT_SPATIAL_FACT_READABILITY_OR_CAUSAL_UTILIZATION',
        other_five_variables='PROBE_UNDERPOWERED_UNCHANGED',selection='ALL_SOURCE_FROZEN_E2_TRIPLETS_NOT_ERRORS',
        baselines=['RANDOM_TRAIN_LABELS_5_FIXED','TEXT_BAG_OF_WORDS','CANDIDATE_VALUE_AND_PRESENCE','POSITION_ONLY','FULL_INPUT_LENGTH_ONLY'],
        prefix_invariance='SAME_WORLD_OBSERVATION_END_AND_TARGET_END_NO_FUTURE_CLAIM_EFFECT_EXPECTED',
        human_gate=False,scientific_grade='AUTO_ONLY_PROVISIONAL',no_new_model_inference=True)
    save(dest/'PROBE_LOCK.json',protocol)
    import numpy as np
    import torch
    roles=['NEUTRAL','CANDIDATE','SHAM'];y=np.array([roles.index(r['label']['information_role']) for r in records])
    hidden=defaultdict(list);position_features=defaultdict(list);source_refs=[]
    for r in records:
        raw=r['measurement'];obj=torch.load(raw['hidden']['path'],map_location='cpu',weights_only=True)
        pos={p['name']:i for i,p in enumerate(obj['positions'])}
        if not set(positions)<=set(pos):raise ValueError('MISSING_COMMON_SEMANTIC_POSITION')
        for name in positions:
            position_features[name].append([obj['positions'][pos[name]]['token_index']])
            for layer in selected_layers:hidden[(layer,name)].append(obj['hidden'][layer,pos[name]].float().numpy())
        source_refs.append(raw['hidden'])
    def ridge_predict(x,targets):
        x=np.asarray(x,dtype=np.float64);xx=x[train];xt=x[val]
        mu=xx.mean(0);xx=xx-mu;xt=xt-mu
        xx=xx/np.maximum(np.linalg.norm(xx,axis=1,keepdims=True),1e-12)
        xt=xt/np.maximum(np.linalg.norm(xt,axis=1,keepdims=True),1e-12)
        yy=np.eye(3)[targets[train]];prior=yy.mean(0)
        coefficients=np.linalg.solve(xx@xx.T+np.eye(len(train)),yy-prior)
        return (xt@xx.T@coefficients+prior).argmax(1)
    predrows=[];stats=[]
    def evaluate(name,x,layer=None,position=None,repeat=None,targets=None):
        pred=ridge_predict(x,y if targets is None else targets)
        perworld=defaultdict(list)
        for i,got in zip(val,pred):
            lab=records[i]['label'];correct=int(got==y[i]);perworld[lab['world_cluster_id']].append(correct)
            predrows.append(dict(analysis=name,layer=layer,position=position,random_repeat=repeat,request_id=lab['request_id'],
                world_cluster_id=lab['world_cluster_id'],actual_role=roles[y[i]],predicted_role=roles[int(got)],correct=correct,
                measurement_ref=records[i]['measurement_ref'],split='WITHIN_DISCOVERY_WORLD_HELDOUT_NOT_C1'))
        vals=[(w,sum(v)/len(v),1) for w,v in perworld.items()];lo,hi=interval(vals,c['seed'],5000)
        stats.append(dict(analysis=name,layer=layer,position=position,random_repeat=repeat,validation_worlds=len(vals),
            validation_requests=len(val),accuracy=sum(v[1] for v in vals)/len(vals),ci95_low=lo,ci95_high=hi,
            classes=roles,claim='ROLE_READABILITY_ONLY',not_confirmatory=True))
    # Closed-form regression sanity check independent of representations and truth labels.
    test=ridge_predict(np.eye(3)[y],y)
    assert np.array_equal(test,y[val])
    random_targets=[]
    for repeat in range(5):
        shuffled=y.copy()
        for w in sorted(tw):
            inds=[i for i in train if records[i]['label']['world_cluster_id']==w]
            order=sorted(range(3),key=lambda k:digest([c['seed'],'ROLE_RANDOM_LABEL_V1',repeat,w,k]))
            for i,k in zip(inds,order):shuffled[i]=k
        random_targets.append(shuffled)
    for (layer,position),values in sorted(hidden.items()):
        x=np.stack(values);evaluate('HIDDEN_ROLE_PROBE',x,layer,position)
        for repeat,shuffled in enumerate(random_targets):evaluate('RANDOM_LABEL_PROBE',x,layer,position,repeat,shuffled)
    texts=[re.findall(r'[a-z_]+',r['request']['payload']['text'].lower()) for r in records]
    vocab=sorted({t for i in train for t in texts[i]});index={t:i for i,t in enumerate(vocab)}
    xx=np.zeros((len(records),len(vocab)))
    for i,ts in enumerate(texts):
        for t in ts:
            if t in index:xx[i,index[t]]+=1
    evaluate('TEXT_BAG_OF_WORDS',xx)
    candidates=[r['label']['candidate_value'] for r in records]
    # Canonical discrete candidate value and presence; enum values never converted into numeric gold.
    keys=sorted({json.dumps(candidates[i]) for i in train});xx=np.zeros((len(records),len(keys)+1))
    for i,v in enumerate(candidates):
        if json.dumps(v) in keys:xx[i,keys.index(json.dumps(v))]=1
        xx[i,-1]=int(v is not None)
    evaluate('CANDIDATE_VALUE_AND_PRESENCE',xx)
    for position,xx in position_features.items():evaluate('POSITION_ONLY',xx,position=position)
    evaluate('FULL_INPUT_LENGTH_ONLY',[[len(r['measurement']['input_token_ids'])] for r in records])
    invariance=[]
    for w in sorted(tw|vw):
        inds=[i for i,r in enumerate(records) if r['label']['world_cluster_id']==w]
        for position in ('observation_end','target_end'):
            for layer in selected_layers:
                x=np.stack(hidden[(layer,position)])[inds]
                delta=float(np.abs(x-x[0]).max())
                invariance.append(dict(world_cluster_id=w,layer=layer,position=position,max_abs_difference=delta,
                    prefix_hashes_equal=len({next(p['prefix_token_sha256'] for p in records[i]['measurement']['positions'] if p['name']==position) for i in inds})==1,
                    interpretation='ENGINEERING_POSITIVE_CONTROL_NOT_FACT_PRESERVATION_EVIDENCE'))
    csvsave(dest/'heldout_predictions.csv',predrows);csvsave(dest/'world_paired_statistics.csv',stats);csvsave(dest/'prefix_invariance.csv',invariance)
    verify(locked['code']+locked['public_inputs']+locked['private_inputs']+source_refs)
    save(dest/'ACCEPTANCE.json',dict(status='COMPLETE',job_id=os.environ['SLURM_JOB_ID'],worlds=20,train_worlds=14,validation_worlds=6,
        heldout_requests=18,groups=len(stats),predictions=len(predrows),source_hashes_unchanged=True,
        conclusion='ONLY_INFORMATION_ROLE_TESTED_WITH_BASELINES_NOT_A_SPATIAL_MECHANISM_RESULT',
        no_hyperparameter_or_layer_selection=True,other_variables='PROBE_UNDERPOWERED',M2='NOT_RUN_BY_THIS_ANALYSIS'))
    text='# M1 information_role 有限读出补充\n\n'
    text+='仅复用已采集的 9B 表征：20 world，14 train / 6 world-heldout，留出 18 条。使用首层、中层、末层 × 4 个共同语义位置；固定线性 ridge，无调参或挑层。\n\n'
    text+='同时保留 5 组随机训练标签、文本词袋、候选值、位置和全输入长度基线，以及前缀不变性工程正控。全部结果含 world 聚类 95% CI，详见 world_paired_statistics.csv。\n\n'
    text+='此分析只能测 information_role 可读性。即使准确率高，文本中角色标签本来就显式存在，不能证明空间事实表示正确、被实际使用，或错误候选改写了状态。其他五个变量仍因类别/world 覆盖不足标记 PROBE_UNDERPOWERED；未执行因果干预或 C1/C2。\n'
    save(dest/'role_probe_report_cn.md',text,'text');print(json.dumps(dict(status='ROLE_PROBE_COMPLETE',groups=len(stats),path=str(dest))),flush=True)


if __name__=='__main__':main()
