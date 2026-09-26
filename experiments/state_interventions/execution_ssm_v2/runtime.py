"""Reuse historical processor and cached inference without changing their code."""
import importlib
from v2_common import *
def main():
    p=argparse.ArgumentParser(add_help=False);p.add_argument('--stage',choices=['processor','infer'],required=True);p.add_argument('--batch',required=True)
    a,rest=p.parse_known_args();mod=importlib.import_module('real_processor_v1' if a.stage=='processor' else 'real_worker_v1')
    def setup(args):
        c,root=context(args)
        gate=load(OLD_ROOT/'technical'/args.model/'BEHAVIOR_PREFLIGHT.json')
        if gate['behavior_execution_status']!='PASS':raise ValueError('HISTORICAL_UNCHANGED_BEHAVIOR_ENGINE_NOT_PASS')
        check(gate['runner'])
        return c,root
    mod.BATCH=a.batch;mod.arguments=cli;mod.setup=setup;sys.argv=[sys.argv[0],*rest];mod.main()
if __name__=='__main__':main()
