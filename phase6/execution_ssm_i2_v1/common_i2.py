"""Isolated I2 LOCALIZE experiment; frozen B1/B2 and R1 remain read-only."""
import sys
from pathlib import Path
CODE_I2=Path(__file__).resolve().parent
sys.path.insert(0,str(CODE_I2.parent/'execution_ssm_internal_v1'))
from internal_common import *
I2=ROOT/'i2_interchange_v1'
def setup_i2(a):
    c,_=context(a);return c,I2
def verify():
    lock=load(I2/'manifest/LOCK.json')
    for r in lock['code']+lock['public_inputs']:check(r)
    return lock

