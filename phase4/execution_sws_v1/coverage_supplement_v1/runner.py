"""New locked batches reuse the original processor/model/scorers; no historical edits."""
import importlib
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from common_auto_v2 import *
from real_processor_v1 import verify
from compile import BATCHES


def v3_engine(batch, kind):
    sys.path.insert(0,str(HERE.parent/'interface_repair_v3'))
    import rescore
    rescore.engine.CASES={batch:dict(batch=batch,scorer='e7_score_v1' if kind=='E7' else 'scorer_adapter',
        table='per_request_diagnostics.csv' if kind=='E7' else 'all_physical_request_scores.csv',
        statistics='grouped_statistics.csv' if kind=='E7' else 'primary_statistics.csv',
        correct='correct' if kind=='E7' else 'content_correct')}
    rescore.engine.base=lambda r:r/'rescoring/coverage_supplement_interface_v3'/batch
    module=importlib.import_module(rescore.engine.CASES[batch]['scorer']);module.BATCH=batch
    return rescore


def check_setup(c,root,model):
    from contracts import parse
    sys.path.insert(0,str(HERE.parent/'interface_repair_v3'))
    from adapter import normalize
    src=root/'batches'/BATCHES['SETUP']; rr=list(rows(src/'public_inputs/requests.jsonl')); items=[]
    for r in rr:
        path=src/'raw'/model/'shard_000/records'/(r['request_id']+'.json')
        raw=load(path)
        if raw['request_hash']!=r['model_independent_request_hash']:raise ValueError('SETUP_RAW_MISMATCH')
        view=normalize(raw['raw_response'],r['schema'])
        items.append(dict(request_id=r['request_id'],raw=entry(path),strict_status=view['strict']['status'],normalized_status=view['normalized']['status']))
    if len(items)!=4 or any(r['normalized_status']!='VALID' for r in items):raise ValueError('FIXED_SETUP_INTERFACE_FAILED_NO_AUTOMATIC_PROMPT_TUNING')
    return items


def main():
    p=arguments(__doc__);p.add_argument('--batch',required=True,choices=list(BATCHES.values()))
    p.add_argument('--stage',required=True,choices=['processor','infer','freeze_score','canonicalize','score'])
    p.add_argument('--model');p.add_argument('--shard',type=int)
    a=p.parse_args();c,root=setup(a);kind=next(k for k,v in BATCHES.items() if v==a.batch)
    lock=load(root/'batches'/a.batch/'manifest/REQUEST_LOCK.json');verify(lock['code']+lock['public_inputs'])
    if a.stage in ('processor','infer'):
        if a.stage=='infer' and kind!='SETUP':
            checks=check_setup(c,root,a.model)
            save(root/'batches'/a.batch/'setup_bridge'/a.model/(os.environ['SLURM_JOB_ID']+'.json'),dict(status='PASS_INTERFACE_ONLY',checks=checks,semantic_accuracy_not_a_gate=True))
        name=('e7_processor_v1' if a.stage=='processor' else 'e7_worker_v1') if kind=='E7' else ('real_processor_v1' if a.stage=='processor' else 'real_worker_v1')
        m=importlib.import_module(name);m.BATCH=a.batch
        sys.argv=[name,'--config',str(a.config),'--run-id',a.run_id,'--seed',str(a.seed),'--resume','--model',a.model]
        if a.stage=='infer' and a.shard is not None:sys.argv+=['--shard',str(a.shard)]
        m.main();return
    v3=v3_engine(a.batch,kind)
    if a.stage=='freeze_score':v3.freeze(c,root)
    elif a.stage=='canonicalize':v3.engine.canonicalize(c,root,a)
    else:
        v3.engine.score(c,root,a);v3.compare_v2(c,root,a)
        from analysis import analyze
        analyze(c,root,a.batch,a.model,v3.engine.snapshot(root,a.batch,a.model))


if __name__=='__main__':main()
