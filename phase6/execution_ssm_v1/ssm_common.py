"""Isolated SSM B1/B2 execution; historical modules are read-only imports."""
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
SWS_CODE=HERE.parents[1]/'phase4/execution_sws_v1'
sys.path.insert(0,str(SWS_CODE))
from common import *
RUN='ssm_b1b2_20260911_v1'
ROOT=Path('artifacts/model_results/sequential_state_mechanism')/RUN
PACKAGE=HERE.parent/'SpaceConflict_SSM_v1_Codex_Package'
sys.path.insert(0,str(PACKAGE/'tools'))
MODELS=['qwen35_4b','qwen35_9b','qwen35_27b']
def cli(description):
    p=argparse.ArgumentParser(description=description)
    p.add_argument('--run-id',default=RUN);p.add_argument('--seed',type=int,default=20260911)
    p.add_argument('--resume',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--limit',type=int)
    return p
def context(a):
    if a.run_id!=RUN or a.seed!=20260911 or a.limit is not None:raise ValueError('FROZEN_SCOPE')
    if not a.dry_run and (not os.environ.get('SLURM_JOB_ID') or socket.gethostname().startswith('login')):raise ValueError('COMPUTE_ALLOCATION_REQUIRED')
    c=load(SWS_CODE/'config_auto_v2.json');c.update(root=str(ROOT),run_id=RUN,seed=20260911)
    c['generation']['joint_large_map_max_new_tokens']=512
    return c,ROOT
def check(ref):
    if sha(ref['path'])!=ref['sha256'].removeprefix('sha256:'):raise ValueError('FROZEN_HASH_CHANGED:'+ref['path'])
def csvrows(path):
    with Path(path).open() as f:return list(csv.DictReader(f))
