"""Reuse original scoring mathematics, correcting split metadata for symbolic batches."""
from common_auto_v2 import *
from contracts import parse
import real_score_v1 as original
BATCH=None


def main():
    original.BATCH=BATCH
    original.parse=parse
    original.save=save
    original.entry=entry
    split='symbolic_control' if BATCH.startswith(('e9c_', 'typed_supplement_setup_')) else 'discovery'
    def routed_csv(path,records,fields=None):
        records=[dict(r,split=split) if 'split' in r else r for r in records]
        return csvsave(path,records,fields)
    original.csvsave=routed_csv
    original.main()
