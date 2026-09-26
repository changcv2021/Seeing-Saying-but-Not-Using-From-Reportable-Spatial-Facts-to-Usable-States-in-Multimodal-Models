"""Versioned adapter for multiview batch; original and breadth runners stay frozen."""
import importlib
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from common_auto_v2 import *
from real_processor_v1 import verify
BATCH='multiview_breadth_v1_20260910'

def main():
    p=arguments(__doc__);p.add_argument('--stage',required=True,choices=['processor','infer','freeze_score','canonicalize','score'])
    p.add_argument('--batch',default=BATCH);p.add_argument('--model');p.add_argument('--shard',type=int)
    a=p.parse_args();c,root=setup(a)
    if a.batch!=BATCH:raise ValueError('NEW_MULTIVIEW_BATCH_ONLY')
    lock=load(root/'batches'/BATCH/'manifest/REQUEST_LOCK.json');verify(lock['code']+lock['public_inputs'])
    if a.dry_run:print(json.dumps(dict(batch=BATCH,stage=a.stage)));return
    import real_design_v1
    real_design_v1.BATCH=BATCH
    if a.stage in ('processor','infer'):
        m=importlib.import_module('real_processor_v1' if a.stage=='processor' else 'real_worker_v1');m.BATCH=BATCH
        sys.argv=[m.__name__,'--config',str(a.config),'--run-id',a.run_id,'--seed',str(a.seed),'--resume','--model',a.model]
        if a.stage=='infer' and a.shard is not None:sys.argv+=['--shard',str(a.shard)]
        m.main();return
    sys.path.insert(0,str(HERE.parent/'interface_repair_v2'))
    import rescore,real_score_v1
    rescore.CASES={BATCH:dict(batch=BATCH,scorer='real_score_v1',table='all_physical_request_scores.csv',statistics='primary_statistics.csv',correct='content_correct')}
    rescore.base=lambda r:r/'rescoring/breadth_interface_v2'/BATCH
    real_score_v1.BATCH=BATCH
    if a.stage=='freeze_score':rescore.freeze(c,root)
    elif a.stage=='canonicalize':rescore.canonicalize(c,root,a)
    else:
        rescore.score(c,root,a)
        from analysis_mv import analyze
        analyze(c,root,BATCH,a.model,rescore.snapshot(root,BATCH,a.model))

if __name__=='__main__':main()
