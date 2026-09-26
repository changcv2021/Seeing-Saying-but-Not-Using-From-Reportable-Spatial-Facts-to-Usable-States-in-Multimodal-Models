"""Resource-only configuration and safe admission for ten independent training runs.

This is not a trainer. Missing GPU acceptance or formal runtime/budget is a hard
preflight failure, not an excuse to launch empty allocations.
"""
import argparse,hashlib,json,os,re,shlex,subprocess,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
PYTHON='python'
AVOIDANCE=HERE.parent.parent/'dataset/GPU_NODE_AVOIDANCE.md'

def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load():
    plan=read(HERE/'resource_plan.json');runs=read(HERE/'runs.json')['runs']
    if len(runs)!=10 or {r['array_index'] for r in runs}!=set(range(10)):raise ValueError('TEN_DISTINCT_ARRAY_ELEMENTS_REQUIRED')
    if len({r['run_id'] for r in runs})!=10 or len({r['output_dir'] for r in runs})!=10:raise ValueError('RUN_OR_OUTPUT_COLLISION')
    if plan['concurrency']['inter_run_dependencies'] or plan['concurrency']['array_throttle'] is not None:raise ValueError('UNNECESSARY_SERIALIZATION')
    match=re.search(r'--exclude=(nid[0-9,\-a-z]+)',AVOIDANCE.read_text())
    if not match or not set(match[1].split(','))<=set(plan['resources']['exclude_nodes']):raise ValueError('GPU_AVOIDANCE_OUTDATED')
    for r in runs:
        c=read(r['config'])
        if c['resources']!=plan['resources'] or c['seed'] not in plan['seeds'] or c['other_training_run_dependencies']:raise ValueError('RUN_CONFIGURATION_MISMATCH')
        if c['test_input_count']!=5608 or c['evaluation_scope']!='held_out_test':raise ValueError('TEST_SCOPE_CHANGED')
    return plan,runs

def prerequisites(plan):
    gates=plan['admission_gates'];blocked=[]
    expected={'split_audit':'PASS','prepared_data':'PASS_PREPARED_SUPERVISION',
        'processor_probe':'MEASURED_TRAIN_PROCESSOR_NO_MODEL_WEIGHTS',
        'base_engineering':'PASS_ENGINEERING','aux_engineering':'PASS_AUXILIARY_TRAINING_ENGINEERING'}
    for key,status in expected.items():
        p=Path(gates[key])
        if not p.is_file():blocked.append(key+':NOT_COMPLETED');continue
        actual=read(p).get('status','')
        accepted=actual.startswith('PASS') if key=='split_audit' else actual==status
        if not accepted:blocked.append(key+':'+actual)
    rp=Path(gates['runtime_manifest'])
    if not rp.is_file():blocked.append('formal_trainer_and_matched_budget:NOT_FROZEN')
    else:
        runtime=read(rp)
        if runtime.get('status')!=gates['required_runtime_status']:blocked.append('formal_runtime:NOT_VALIDATED')
        ep=Path(runtime.get('entrypoint','/nonexistent_phase8_entrypoint'))
        if not ep.is_file() or sha(ep)!=runtime.get('entrypoint_sha256'):blocked.append('formal_runtime:ENTRYPOINT_MISSING_OR_CHANGED')
        bp=Path(runtime.get('budget_plan','/nonexistent_phase8_budget'))
        if not bp.is_file() or sha(bp)!=runtime.get('budget_plan_sha256'):blocked.append('training_budget:NOT_FROZEN_OR_CHANGED')
        if runtime.get('resources_sha256')!=sha(HERE/'resource_plan.json'):blocked.append('formal_runtime:RESOURCE_PLAN_NOT_VALIDATED')
        interface=plan['state_interface']
        if (runtime.get('state_interface_version')!=interface['version'] or
            runtime.get('state_interface_sha256')!=sha(interface['module'])):
            blocked.append('formal_runtime:STATE_INTERFACE_NOT_INTEGRATED')
        if not runtime.get('resume_and_signal_handlers_validated'):blocked.append('checkpoint_resume:NOT_VALIDATED')
    return blocked

def scheduler_profile_command(plan):
    r=plan['resources'];logs=Path(plan['output_root'])/'logs'
    return ['sbatch','--test-only','--job-name=sc_pss_resource_check','--partition='+r['partition'],
        '--account='+r['account'],'--qos='+r['qos'],'--nodes=1','--ntasks=1',
        '--cpus-per-task='+str(r['cpus_per_task']),'--mem='+str(r['memory_gib'])+'G',
        '--gpus-per-node='+str(r['gpus_per_node']),'--time='+r['walltime'],
        '--exclude='+','.join(r['exclude_nodes']),'--output='+str(logs/'resource_check_%j.out'),
        '--error='+str(logs/'resource_check_%j.err'),'--wrap=/bin/true']

def main():
    p=argparse.ArgumentParser(__doc__)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run',action='store_true');group.add_argument('--scheduler-test-only',action='store_true')
    group.add_argument('--submit',action='store_true');group.add_argument('--run-index',type=int)
    a=p.parse_args();plan,runs=load()
    if a.scheduler_test_only:
        command=scheduler_profile_command(plan);print(shlex.join(command),flush=True)
        # --test-only does not allocate or execute a compute job. It tests the
        # common per-element profile, not ten training processes.
        result=subprocess.run(command,check=False);raise SystemExit(result.returncode)
    blocked=prerequisites(plan)
    if a.dry_run:
        print(json.dumps(dict(run_count=len(runs),resources=plan['resources'],array='0-9',
            inter_run_dependencies=[],blocked=blocked,formal_submission_command=['sbatch',str(HERE/'train_array.sbatch')],
            formal_jobs_submitted=False,runs=runs),ensure_ascii=False,indent=2));return
    if blocked:raise SystemExit('FORMAL_ADMISSION_NOT_READY: '+', '.join(blocked))
    if a.submit:
        Path(plan['output_root'],'logs').mkdir(parents=True,exist_ok=True)
        subprocess.run(['sbatch',str(HERE/'train_array.sbatch')],check=True);return
    if not os.environ.get('SLURM_JOB_ID'):raise SystemExit('SLURM_REQUIRED')
    if a.run_index not in range(10):raise SystemExit('INVALID_RUN_INDEX')
    run=runs[a.run_index];runtime=read(plan['admission_gates']['runtime_manifest'])
    Path(run['output_dir']).mkdir(parents=True,exist_ok=True)
    os.execv(PYTHON,[PYTHON,runtime['entrypoint'],'--run-config',run['config'],
        '--runtime-manifest',plan['admission_gates']['runtime_manifest'],'--resume'])

if __name__=='__main__':main()
