"""Add a safe between-response checkpoint to the unchanged scientific runner."""
import argparse, builtins, json, os, runpy, signal, sys
from orchestration import ORIGINAL, ROOT, RUN_ID, SEED, registry, write
CHECKPOINT_EXIT=77

def is_committed_progress(source,stage,text):
    expected=ORIGINAL/('infer.py' if stage=='candidate' else 'judge.py')
    if source!=str(expected):return False
    try:row=json.loads(text)
    except (ValueError,TypeError):return False
    return ('completed' in row and 'model' in row) if stage=='candidate' else ('sample_id' in row and 'fallbacks' in row)

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('stage',choices=['candidate','judge'])
    p.add_argument('--model',required=True);p.add_argument('--num-shards',type=int,required=True)
    p.add_argument('--shard-index',type=int,required=True);p.add_argument('--run-id',default=RUN_ID)
    p.add_argument('--seed',type=int,default=SEED);p.add_argument('--resume',action='store_true')
    p.add_argument('--dry-run',action='store_true');p.add_argument('--limit',type=int)
    a=p.parse_args()
    if a.run_id!=RUN_ID or a.seed!=SEED or a.limit is not None:raise ValueError('PROTOCOL_MISMATCH')
    cfg=registry()[a.model];root=ROOT/a.model
    program=ORIGINAL/('infer.py' if a.stage=='candidate' else 'judge.py')
    arguments=[str(program),'--run-root',str(root),'--run-id',cfg['run_id'],'--scope','full',
               '--num-shards',str(a.num_shards),'--shard-index',str(a.shard_index),'--seed',str(SEED),'--resume']
    if a.dry_run:print(json.dumps(arguments));return
    job=os.environ['SLURM_JOB_ID'];requested=False;original_print=builtins.print
    def request(signum,frame):
        nonlocal requested
        requested=True
    signal.signal(signal.SIGUSR1,request)
    def checkpoint_print(*values,**kwargs):
        original_print(*values,**kwargs)
        source=sys._getframe(1).f_code.co_filename
        if requested and values and is_committed_progress(source,a.stage,values[0]):
            # Both original runners print this only after stream.flush and fsync.
            directory=root/('full' if a.stage=='candidate' else 'full_judge')
            write(directory/f'checkpoint_{job}_{a.shard_index:03d}.json',
                  dict(status='COMMITTED_RESPONSE_BOUNDARY',job=job,index=a.shard_index,
                       original_program=str(program),completed_outputs_unchanged=True))
            raise SystemExit(CHECKPOINT_EXIT)
    builtins.print=checkpoint_print
    try:
        sys.argv=arguments
        runpy.run_path(str(program),run_name='__main__')
    finally:builtins.print=original_print

if __name__=='__main__':main()
