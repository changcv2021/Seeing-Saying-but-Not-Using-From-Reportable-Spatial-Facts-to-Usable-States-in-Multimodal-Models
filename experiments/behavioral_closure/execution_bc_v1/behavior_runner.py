"""Reuse frozen SWS processor/inference with an isolated Phase5 output namespace."""
from bc_common import *

def main():
    p=argparse.ArgumentParser(add_help=False);p.add_argument('--stage',choices=['processor','infer'],required=True)
    p.add_argument('--batch',choices=['c1_count_v1','e5_measurement_v1'],required=True);a,rest=p.parse_known_args()
    import importlib
    module=importlib.import_module('real_processor_v1' if a.stage=='processor' else 'real_worker_v1')
    def adapted_setup(args):
        c,sws,out=context(args)
        return dict(c,root=str(out),run_id=RUN),out
    module.BATCH=a.batch;module.arguments=cli;module.setup=adapted_setup
    sys.argv=[sys.argv[0],*rest];module.main()

if __name__=='__main__':main()
