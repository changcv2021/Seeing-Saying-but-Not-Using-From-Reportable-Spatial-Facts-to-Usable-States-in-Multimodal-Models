"""Technical -> measured LOCALIZE -> frozen candidate -> SELECT/protection, genuine dependencies only."""
import subprocess,fcntl
from v2_common import *
sys.path.insert(0,str(HERE))
from launch import submit
def main():
    p=cli(__doc__);p.add_argument('--stage',choices=['technical','localize','selected'],required=True);a=p.parse_args();i1=ROOT/'I1'
    # Lightweight launcher: no model construction / data processing on login.
    live=subprocess.run(['sinfo','-h','-p','gpu','-o','%P|%a|%l|%G'],capture_output=True,text=True,check=True,timeout=30).stdout
    assert 'gpu|up|2-00:00:00|gpu:4' in live
    assoc=subprocess.run(['sacctmgr','-nP','show','assoc','where','user=anonymous','format=User,Account,Partition,QOS'],capture_output=True,text=True,check=True,timeout=30).stdout
    assert 'anonymous|YOUR_ACCOUNT||allocated' in assoc
    own=(ROOT/'scheduler/i1_launcher.lock').open('a');fcntl.flock(own,fcntl.LOCK_EX|fcntl.LOCK_NB)
    gpu=['--partition=gpu','--gpus-per-node=1','--cpus-per-task=4','--mem=64G','--exclude='+EXCLUSIONS]
    cpu=['--partition=general','--cpus-per-task=1','--mem=8G','--time=00:30:00']
    if a.stage=='technical':
        if not (i1/'manifest/RUNTIME_LOCK.json').exists():
            old=SPACE/'experiments/sequential_state';code=[entry(HERE/n) for n in ['i1_engine.py','i1_worker.py','i1_analyze.py','launch_i1.py','v2_common.py','job.sh']]
            code += [entry(old/'execution_ssm_i2_v1'/n) for n in ['engine.py','common_i2.py']]
            code += [entry(old/'execution_ssm_internal_v1'/n) for n in ['representations.py','internal_common.py']]
            code += runtime_refs()
            save(i1/'manifest/RUNTIME_LOCK.json',dict(status='FROZEN_BEFORE_I1_FORWARDS',code=code,input_lock=entry(i1/'manifest/INPUT_LOCK.json'),
                no_global_gpu_hour_cap=True,relative_window_mapping='Declared before forward; no R1/I2 score-selected layers',
                selection_policy='LOCALIZE chooses <=2; SELECT one pass; no automatic component expansion without passing gate'))
        j=submit('I1_technical',gpu+['--time=01:00:00'],['i1_worker','--stage','technical'])
        submit('I1_dispatch_localize',cpu+['--dependency=afterok:'+j],['launch_i1','--stage','localize']);return
    tech=load(i1/'technical/qwen35_9b/TECHNICAL_ACCEPTANCE.json');assert tech['status']=='PASS';check(tech['runtime_lock'])
    if a.stage=='localize':
        n=len(load(i1/'manifest/shards.json'));build=load(i1/'manifest/BUILD_ACCEPTANCE.json')
        estimate=max(tech['baseline_seconds'])*build['localize_primary_patch_upper']*4/8
        save(i1/'manifest/MEASURED_RESOURCE_PLAN.json',dict(measurements=entry(i1/'technical/qwen35_9b/TECHNICAL_ACCEPTANCE.json'),
            heuristic_mean_shard_seconds=estimate,assumptions='4 generation-equivalents per trial for full candidate scoring; not a hard compute budget',
            shard_gpu=1,shards=n,concurrency=4,requested_wall='24:00:00',site_wall='48:00:00',no_six_hour_restriction=True))
        j=submit('I1_localize',gpu+['--time=24:00:00',f'--array=0-{n-1}%4'],['i1_worker','--stage','localize'])
        sc=submit('I1_localize_analysis',cpu+['--dependency=afterany:'+j],['i1_analyze','--stage','localize'])
        submit('I1_dispatch_selected',cpu+['--dependency=afterok:'+sc],['launch_i1','--stage','selected']);return
    lock=load(i1/'selection/CANDIDATE_LOCK.json')
    if lock['status']!='CANDIDATES_FROZEN':print('STOP_NO_LOCALIZE_CANDIDATES; no selected jobs');return
    check(lock['runtime_lock']);check(lock['source'])
    j=submit('I1_selected_protection',gpu+['--time=24:00:00','--array=0-7%4'],['i1_worker','--stage','selected'])
    submit('I1_selected_analysis',cpu+['--dependency=afterany:'+j],['i1_analyze','--stage','selected'])
if __name__=='__main__':main()
