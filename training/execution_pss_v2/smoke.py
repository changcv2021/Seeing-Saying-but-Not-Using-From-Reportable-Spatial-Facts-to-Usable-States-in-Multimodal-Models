"""Actual 9B forward/backward, save-reload, and dev-only generation; no formal test."""
import sys,time,traceback
from common import *
from model_io import HP,answer_target,encode,load_engine,loss_for,PROTOCOL_DIR

def main():
    a=cli(__doc__).parse_args();root=a.run_root;out=root/'engineering_smoke_v1'
    if a.dry_run:print(str(out));return
    compute();gate=read(root/'SPLIT_AUDIT.json')
    if not gate['status'].startswith('PASS'):raise ValueError('SPLIT_GATE_FAILED')
    if (out/'ACCEPTANCE.json').exists():
        if a.resume:print((out/'ACCEPTANCE.json').read_text());return
        raise FileExistsError(out)
    out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(REPO/'scripts/full_multimodel_split_v5'))
    from gpu_health import check
    check(out)
    # Register frozen scorer under its expected name, without shadowing pss common.
    from model_io import old_module
    original_common=old_module('common');saved=sys.modules.get('common');sys.modules['common']=original_common
    policy=old_module('output_policy');sys.modules['common']=saved
    train=list(rows(root/'data/train/requests.jsonl'));tg={r['sample_id']:r for r in rows(root/'data/train/private_gold.jsonl')}
    dev=list(rows(root/'data/dev/requests.jsonl'));dg={r['sample_id']:r for r in rows(root/'data/dev/private_gold.jsonl')}
    chosen=[]
    for level in ('L1','L2','L3','L4'):
        candidates=[r for r in train if r['level']==level and r.get('media')]
        chosen.append(min(candidates,key=lambda r:digest([a.seed,r['sample_id']])))
    chosen.append(max(train,key=lambda r:(len(r.get('media',[])),digest(r['sample_id']))))
    eval_rows=[min((r for r in dev if r['level']==level),key=lambda r:digest([a.seed,'dev_smoke',r['sample_id']])) for level in ('L1','L2','L3','L4')]
    write(out/'FROZEN_SMOKE_PANEL.json',dict(train_ids=[r['sample_id'] for r in chosen],dev_ids=[r['sample_id'] for r in eval_rows],
        source_selection='Hash per level plus maximum-media training stress input; never selected by model errors',scope='ENGINEERING_NOT_METHOD_RESULT'))
    import torch
    model,processor,config=load_engine(root,a.seed)
    write(out/'ENGINE.json',dict(config,job_id=os.environ['SLURM_JOB_ID'],seed=a.seed,code_sha256=sha(__file__)))
    optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=HP['learning_rate'],weight_decay=HP['weight_decay'])
    receipts=[]
    model.train();before={n:p.detach().cpu().clone() for n,p in model.named_parameters() if p.requires_grad}
    for index,sample in enumerate(chosen):
        begin=time.monotonic();torch.cuda.reset_peak_memory_stats()
        batch,receipt=encode(processor,sample,answer_target(tg[sample['sample_id']]['gold']))
        optimizer.zero_grad(set_to_none=True);loss=loss_for(model,batch,receipt)
        if not torch.isfinite(loss):raise ValueError('NONFINITE_LOSS')
        loss.backward();norm=torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],HP['max_grad_norm'])
        if not torch.isfinite(norm) or float(norm)==0:raise ValueError('INVALID_GRADIENT')
        optimizer.step();torch.cuda.synchronize()
        row=dict(receipt,index=index,sample_id=sample['sample_id'],level=sample['level'],loss=float(loss.detach()),grad_norm=float(norm),
                 seconds=time.monotonic()-begin,peak_allocated_bytes=torch.cuda.max_memory_allocated(),peak_reserved_bytes=torch.cuda.max_memory_reserved())
        write(out/f'train_step_{index:03d}.json',row);receipts.append(row);print(json.dumps({k:row[k] for k in ('index','sample_id','loss','seconds','peak_allocated_bytes')}),flush=True)
        del batch,loss
    changed=sum(not torch.equal(before[n],p.detach().cpu()) for n,p in model.named_parameters() if p.requires_grad)
    if not changed:raise ValueError('NO_ADAPTER_UPDATE')
    del before,optimizer
    checkpoint=out/'adapter';model.save_pretrained(checkpoint,safe_serialization=True)
    from safetensors.torch import load_file
    from peft import get_peft_model_state_dict,set_peft_model_state_dict
    saved_state={k:v.detach().cpu().clone() for k,v in get_peft_model_state_dict(model).items()}
    with torch.no_grad():
        for n,p in model.named_parameters():
            if p.requires_grad:p.zero_()
    set_peft_model_state_dict(model,load_file(checkpoint/'adapter_model.safetensors'))
    restored=get_peft_model_state_dict(model)
    if any(not torch.equal(v,restored[k].detach().cpu()) for k,v in saved_state.items()):raise ValueError('ADAPTER_RELOAD_MISMATCH')
    model.eval();model.gradient_checkpointing_disable();predictions=[]
    for sample in eval_rows:
        batch,receipt=encode(processor,sample)
        with torch.inference_mode(): generated=model.generate(**batch.to(model.device),do_sample=False,max_new_tokens=512,use_cache=True)
        ids=generated[0,receipt['prompt_tokens']:receipt['prompt_tokens']+512].tolist()
        text=processor.decode(ids,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip()
        eos=model.generation_config.eos_token_id; eos=[eos] if isinstance(eos,int) else eos
        pred=dict(sample_id=sample['sample_id'],raw_response=text,generated_token_ids=ids,error=None,
                  **policy.generation_metadata(len(ids),ids[-1] if ids else None,eos,len(ids)))
        pred['prediction']=policy.parse_prediction(pred);predictions.append(pred)
        write(out/(sample['level']+'_dev_raw.json'),pred)
        del batch,generated
    scored=[dict(dg[r['sample_id']],label=r['prediction'].get('label')) for r in predictions]
    result=dict(status='PASS_ENGINEERING' if all(r['prediction'].get('label') is not None for r in predictions) else 'INTERFACE_REVIEW_REQUIRED',
        training_updates=len(receipts),adapter_tensors_changed=changed,checkpoint_save_reload_exact=True,
        dev_samples=len(predictions),dev_metrics_descriptive_only=original_common.metrics(scored),
        peak_allocated_bytes=max(r['peak_allocated_bytes'] for r in receipts),step_seconds=[r['seconds'] for r in receipts],
        raw_responses_preserved=True,formal_test_started=False,formal_training_started=False,
        only_answer_target_engineering_verified=True,job_id=os.environ['SLURM_JOB_ID'])
    write(out/'ACCEPTANCE.json',result);print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':
    try:main()
    except BaseException:
        print(traceback.format_exc(),flush=True);raise
