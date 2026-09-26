"""Exact historical processor/generation implementation under new SSM locks."""
import importlib
from ssm_common import *
def main():
    p=argparse.ArgumentParser(add_help=False);p.add_argument('--stage',choices=['processor','infer'],required=True);p.add_argument('--batch',choices=['B1','B2'],required=True)
    a,rest=p.parse_known_args();module=importlib.import_module('real_processor_v1' if a.stage=='processor' else 'real_worker_v1')
    def setup(args):
        c,root=context(args)
        if a.stage=='infer':
            gate=load(root/'technical'/args.model/'BEHAVIOR_PREFLIGHT.json')
            if gate['behavior_execution_status']!='PASS':raise ValueError('BEHAVIOR_PREFLIGHT_NOT_PASS')
            check(gate['runner']);check(gate['request_lock_B1']);check(gate['request_lock_B2'])
        return c,root
    module.BATCH=a.batch;module.arguments=cli;module.setup=setup;sys.argv=[sys.argv[0],*rest];module.main()
if __name__=='__main__':main()
