"""Frozen lightweight diagnostic probes; SELECT chooses regularization, no layer cherry-picking."""
import re
from collections import Counter,defaultdict
from internal_common import *
def main():
    p=cli(__doc__);p.add_argument('--model',required=True);a=p.parse_args();c,out=setup(a)
    if a.dry_run:print('Small ridge probes plus majority/word-number baselines; no backbone training.');return
    verify_lock();src=out/'representations'/a.model;acc=load(src/'EXTRACTION_ACCEPTANCE.json');check(acc['activations']);check(acc['index'])
    import numpy as np,torch
    data=torch.load(acc['activations']['path'],map_location='cpu',weights_only=True);features=data['features'].float().numpy()
    records={r['request_id']:r for r in rows(acc['index']['path'])};labels={r['request_id']:r for r in rows(out/'private_gold/r1_labels.jsonl')}
    ids=data['request_ids'];protocol=load(out/'manifest/R1_PROTOCOL.json')['probes'];dest=out/'probes'/a.model
    # Read only LOCALIZE/SELECT target labels during fitting; evaluation target lookup occurs after the selection lock is written.
    groups=defaultdict(list)
    for i,rid in enumerate(ids):groups[(labels[rid]['batch'],labels[rid]['condition'])].append(i)
    pending=[];unmeasured=[]
    for group,inds in sorted(groups.items()):
        train=[i for i in inds if labels[ids[i]]['split']=='LOCALIZE'];sel=[i for i in inds if labels[ids[i]]['split']=='SELECT'];test=[i for i in inds if labels[ids[i]]['split']=='LOCKED_EVAL']
        cluster=lambda ii:len({labels[ids[i]]['cluster_id'] for i in ii})
        if cluster(train)<8 or cluster(sel)<3 or cluster(test)<3:
            unmeasured.append(dict(group=group,status='PROBE_UNDERPOWERED',train_clusters=cluster(train),select_clusters=cluster(sel),eval_clusters=cluster(test)));continue
        tokens={i:re.findall(r'[A-Za-z_]+|\d+',records[ids[i]]['text'].lower()) for i in inds}
        vocab=sorted({t for i in train for t in tokens[i]});vmap={v:j for j,v in enumerate(vocab)}
        bag=np.zeros((len(ids),len(vocab)+2),dtype=np.float64)
        for i in inds:
            for t,n in Counter(tokens[i]).items():
                if t in vmap:bag[i,vmap[t]]=n
            bag[i,-2:]=[records[ids[i]]['input_tokens'],len(records[ids[i]]['text'])]
        setups=[('WORD_NUMBER_BAG_PLUS_LENGTH',None,None,bag)]
        for li,layer in enumerate(data['layers']):
            for anchor in protocol['anchors']:
                ai=data['anchors'].index(anchor);setups.append(('RESIDUAL_LINEAR_RIDGE',layer,anchor,features[:,li,ai,:].astype(np.float64)))
        for variable in protocol['variables']:
            tv=[labels[ids[i]]['targets'].get(variable) for i in train];sv=[labels[ids[i]]['targets'].get(variable) for i in sel]
            meta=dict(model=a.model,batch=group[0],condition=group[1],variable=variable,train_clusters=cluster(train),select_clusters=cluster(sel),eval_clusters=cluster(test),
                oracle_positive_control=group[1]=='B06',exploratory_not_mechanism_proof=True)
            if any(v is None for v in tv+sv):
                unmeasured.append(dict(meta,status='VARIABLE_NOT_SUPPLIED_IN_THIS_PANEL'));continue
            classes=sorted(set(tv),key=lambda v:str(v));cmap={v:j for j,v in enumerate(classes)}
            if len(classes)<2:
                unmeasured.append(dict(meta,status='STATE_VARIABLE_NOT_IDENTIFIABLE_CONSTANT_TRAIN_LABEL'));continue
            targets=np.eye(len(classes))[[cmap[v] for v in tv]]
            majority=max(classes,key=lambda v:(tv.count(v),-cmap[v]))
            pending.append(dict(meta,method='MAJORITY',layer=None,anchor=None,alpha=None,classes=classes,eval_indices=test,
                eval_predictions=[majority]*len(test),selection_accuracy=sum(v==majority for v in sv)/len(sv)))
            class_clusters={str(v):len({labels[ids[i]]['cluster_id'] for i,x in zip(train,tv) if x==v}) for v in classes}
            for method,layer,anchor,x in setups:
                mean=x[train].mean(0);scale=x[train].std(0);scale[scale<1e-8]=1.
                xt=(x[train]-mean)/scale;xs=(x[sel]-mean)/scale;xe=(x[test]-mean)/scale
                # Centered feature scaling and regularized intercept; all statistics fit on LOCALIZE only.
                xt=np.column_stack((xt,np.ones(len(train))));xs=np.column_stack((xs,np.ones(len(sel))));xe=np.column_stack((xe,np.ones(len(test))))
                gram=xt@xt.T;best=None
                for alpha in protocol['ridge_alphas']:
                    dual=np.linalg.solve(gram+alpha*np.eye(len(train)),targets)
                    pred=np.argmax((xs@xt.T)@dual,axis=1);score=sum(classes[j]==v for j,v in zip(pred,sv))/len(sel)
                    if best is None or score>best[0]:best=(score,alpha,dual)
                score,alpha,dual=best;prediction=[classes[j] for j in np.argmax((xe@xt.T)@dual,axis=1)]
                pending.append(dict(meta,method=method,layer=layer,anchor=anchor,alpha=alpha,classes=classes,train_class_clusters=class_clusters,
                    eval_indices=test,eval_predictions=prediction,selection_accuracy=score))
    selection=[{k:v for k,v in r.items() if k not in ('eval_predictions','eval_indices')} for r in pending]
    save(dest/'PROBE_SELECTION_LOCK.json',dict(created_at=now(),status='LOCKED_BEFORE_EVAL_TARGET_COMPARISON',choices=selection,
        source=entry(src/'EXTRACTION_ACCEPTANCE.json'),labels=entry(out/'private_gold/r1_labels.jsonl'),protocol=entry(out/'manifest/R1_PROTOCOL.json'),
        no_layer_selection=True,all_fixed_layers_reported=True,backbone_training=False))
    result=list(unmeasured);predictions=[]
    for r in pending:
        truth=[labels[ids[i]]['targets'].get(r['variable']) for i in r['eval_indices']]
        eligible=[(i,p,y) for i,p,y in zip(r['eval_indices'],r['eval_predictions'],truth) if y is not None]
        if not eligible:continue
        ww=defaultdict(list)
        for i,p,y in eligible:
            w=labels[ids[i]]['cluster_id'];ww[w].append(float(type(p) is type(y) and p==y))
            predictions.append(dict(model=a.model,request_id=ids[i],cluster_id=w,batch=r['batch'],condition=r['condition'],variable=r['variable'],
                method=r['method'],layer=r['layer'],anchor=r['anchor'],alpha=r['alpha'],gold=y,prediction=p,correct=p==y,split='LOCKED_EVAL'))
        x=np.array([[sum(v),len(v)] for _,v in sorted(ww.items())]);rng=np.random.default_rng(20260911);ix=rng.integers(0,len(x),size=(5000,len(x)));bs=x[ix].sum(1);bb=bs[:,0]/bs[:,1];lo,hi=map(float,np.quantile(bb,[.025,.975]))
        unseen=sum(y not in r['classes'] for _,_,y in eligible)
        result.append(dict(**{k:v for k,v in r.items() if k not in ('eval_indices','eval_predictions')},status='ESTIMATED_WITH_CLASS_COVERAGE_LIMIT' if unseen else 'ESTIMATED',
            numerator=sum(map(sum,ww.values())),denominator=len(eligible),worlds=len(ww),accuracy=sum(map(sum,ww.values()))/len(eligible),ci95_low=lo,ci95_high=hi,
            eval_unseen_class_rows=unseen,uncertainty='SOURCE_COMPONENT_CLUSTER_BOOTSTRAP_5000; NO_MULTIPLICITY_ADJUSTMENT_EXPLORATORY',
            zero_width_ci_warning=lo==hi))
    csvsave(dest/'PROBE_RESULTS_AND_BASELINES.csv',result);csvsave(dest/'ALL_EVAL_PREDICTIONS.csv',predictions)
    save(dest/'PROBE_ACCEPTANCE.json',dict(status='COMPLETE_DIAGNOSTIC_PROBES_NOT_CAUSAL_PROOF',model=a.model,rows=len(result),predictions=len(predictions),
        lock=entry(dest/'PROBE_SELECTION_LOCK.json'),results=entry(dest/'PROBE_RESULTS_AND_BASELINES.csv'),eval_predictions=entry(dest/'ALL_EVAL_PREDICTIONS.csv'),
        backbone_updated=False,interventions=0,missing_identifiability_retained=True,job_id=os.environ['SLURM_JOB_ID']))
    print(json.dumps(dict(model=a.model,status='PROBES_COMPLETE',rows=len(result))),flush=True)
if __name__=='__main__':main()
