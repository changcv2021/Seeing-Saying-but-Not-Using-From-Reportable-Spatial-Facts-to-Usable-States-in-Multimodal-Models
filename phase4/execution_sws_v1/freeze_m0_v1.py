"""Freeze the bounded M0 technical requests, hooks and tolerances before outputs."""
import ast
from common import *

def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('M0 freeze, no GPU model load'); return
    ast.parse((CODE/'m0_v1.py').read_text())
    from m0_v1 import CANONICAL,TOLERANCE
    impl=Path('external/scratch/industbench_qwen_family/venv/lib/python3.12/site-packages/transformers')
    parent=load(root/'manifest/gpu_runtime_lock_v1.json')
    code=parent['code']+[entry(CODE/x) for x in ('m0_v1.py','job_m0_v1.sh','freeze_m0_v1.py')]
    code += [entry(impl/x) for x in ('models/qwen3_5/modeling_qwen3_5.py','cache_utils.py')]
    lock=dict(run_id=c['run_id'],status='FROZEN_TECHNICAL_EQUIVALENCE_NOT_LOCALIZATION',code=code,inputs=parent['inputs'],
        requests=4,source='UNCHANGED_PREVIOUSLY_REVIEWED_B0_A_TASKS_IN_FIXED_SMOKE',model='qwen35_9b',
        canonical_answers=CANONICAL,tolerances=TOLERANCE,selected_modules='DECODER_0_MIDDLE_LAST_NOOP_ONLY',
        no_actual_causal_patch_or_training=True,no_model_error_selection=True,created_at=now())
    save(root/'manifest/M0_LOCK_V1.json',lock); print(json.dumps(dict(status='PASS',lock=entry(root/'manifest/M0_LOCK_V1.json'))),flush=True)

if __name__=='__main__': main()
