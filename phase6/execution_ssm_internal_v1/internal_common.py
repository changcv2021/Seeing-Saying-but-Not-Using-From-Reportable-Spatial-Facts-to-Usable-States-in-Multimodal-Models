"""First independent SSM representation wave; never mutate B1/B2 locks."""
import sys
from pathlib import Path
WAVE_CODE=Path(__file__).resolve().parent
sys.path.insert(0,str(WAVE_CODE.parent/'execution_ssm_v1'))
from ssm_common import *
OUT=ROOT/'independent_wave1'
def setup(a):
    c,root=context(a);return c,OUT
def verify_lock(include_private=True):
    lock=load(OUT/'manifest/INDEPENDENT_WAVE_LOCK.json')
    for ref in lock['code']+lock['inputs']:
        if include_private or '/private_gold/' not in ref['path']:check(ref)
    return lock
