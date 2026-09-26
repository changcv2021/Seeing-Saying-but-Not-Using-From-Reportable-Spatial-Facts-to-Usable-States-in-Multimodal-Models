"""Reuse immutable SWS processor, model worker, and both scoring views."""
import importlib
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from common_auto_v2 import *
from real_processor_v1 import verify

def main():
    p=arguments(__doc__);p.add_argument('--stage',required=True,choices=['processor','infer','freeze_score','canonicalize','score'])
    p.add_argument('--batch',required=True);p.add_argument('--model');p.add_argument('--shard',type=int)
    a=p.parse_args();c,root=setup(a)
    if a.batch not in ('native_e8_breadth_v1_20260910','noncount_breadth_v1_20260910','breadth_setup_v1_20260910'):raise ValueError('NEW_BATCH_ONLY')
    lock=load(root/'batches'/a.batch/'manifest/REQUEST_LOCK.json');verify(lock['code']+lock['public_inputs'])
    if a.dry_run:print(json.dumps(dict(batch=a.batch,stage=a.stage,model=a.model)));return
    import real_design_v1
    real_design_v1.BATCH=a.batch
    if a.stage in ('processor','infer'):
        m=importlib.import_module('real_processor_v1' if a.stage=='processor' else 'real_worker_v1');m.BATCH=a.batch
        sys.argv=[m.__name__,'--config',str(a.config),'--run-id',a.run_id,'--seed',str(a.seed),'--resume','--model',a.model]
        if a.stage=='infer' and a.shard is not None:sys.argv+=['--shard',str(a.shard)]
        m.main();return
    sys.path.insert(0,str(HERE.parent/'interface_repair_v2'))
    import rescore,real_score_v1
    rescore.CASES={a.batch:dict(batch=a.batch,scorer='real_score_v1',table='all_physical_request_scores.csv',statistics='primary_statistics.csv',correct='content_correct')}
    rescore.base=lambda r:r/'rescoring/breadth_interface_v2'/a.batch
    real_score_v1.BATCH=a.batch
    if a.stage=='freeze_score':rescore.freeze(c,root)
    elif a.stage=='canonicalize':rescore.canonicalize(c,root,a)
    else:
        rescore.score(c,root,a)
        from analysis import analyze
        analyze(c,root,a.batch,a.model,rescore.snapshot(root,a.batch,a.model))

if __name__=='__main__':main()
