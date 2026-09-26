"""Native completion wrapper around unchanged SWS actual processor/inference."""
from bc_common import *
BATCH='native_e8_measurement_v1'

def main():
    p=argparse.ArgumentParser(add_help=False);p.add_argument('--stage',choices=['processor','infer'],required=True)
    p.add_argument('--batch',choices=[BATCH],required=True);a,rest=p.parse_known_args()
    import importlib
    module=importlib.import_module('real_processor_v1' if a.stage=='processor' else 'real_worker_v1')
    def adapted(args):
        c,sws,out=context(args)
        extra=load(out/'batches'/BATCH/'manifest/NATIVE_EXTENSION_LOCK.json')
        for ref in extra['code']+[extra['request_lock']]:check(ref)
        return dict(c,root=str(out),run_id=RUN),out
    module.BATCH=BATCH;module.arguments=cli;module.setup=adapted;sys.argv=[sys.argv[0],*rest];module.main()

if __name__=='__main__':main()
