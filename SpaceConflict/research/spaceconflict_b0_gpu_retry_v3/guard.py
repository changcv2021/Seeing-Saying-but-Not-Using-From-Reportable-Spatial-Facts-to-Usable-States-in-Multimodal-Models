"""One explicit infrastructure retry of 27B; unchanged frozen inference and scoring."""
import sys
from pathlib import Path
GUARD_CODE=Path(__file__).resolve().parent
sys.path.insert(0,str(GUARD_CODE.parent/'spaceconflict_b0_launchfix_v1'))
from b0common import *
import subprocess
import signal
import time
import xml.etree.ElementTree as ET
import re

STARTUP_SECONDS=900
NO_PROGRESS_SECONDS=300
POLL_SECONDS=10
HEALTH_SECONDS=30


def parse_health(xml_text):
    root=ET.fromstring(xml_text); result=[]
    for gpu in root.findall('gpu'):
        actions=[(el.text or '').strip() for el in gpu.iter() if el.tag in ['gpu_recovery_action','recovery_action']]
        reset_strings=any('requires reset' in (el.text or '').lower() for el in gpu.iter())
        # Fail closed when this driver does not provide a readable recovery flag.
        healthy=bool(actions) and all(v.lower()=='none' for v in actions) and not reset_strings
        result.append(dict(uuid=gpu.findtext('uuid'),pci=gpu.get('id'),recovery_actions=actions,
            reset_required_text=reset_strings,healthy=healthy))
    return dict(healthy=len(result)==2 and all(r['healthy'] for r in result),gpus=result,
                driver=root.findtext('driver_version'),status='READ_ONLY_DEVICE_HEALTH')


def allocated_gpu_ids(environ):
    # SLURM_JOB_GPUS uses global NVML IDs, unlike potentially remapped CUDA IDs.
    devices=environ.get('SLURM_JOB_GPUS','').split(',')
    if len(devices)!=2 or len(set(devices))!=2 or any(not re.fullmatch(r'(?:[0-9]+|GPU-[a-fA-F0-9-]+)',v) for v in devices):
        raise ValueError('EXPECTED_TWO_EXPLICIT_SLURM_JOB_GPU_IDS')
    return ','.join(devices)


def stall_reason(elapsed,since_progress,loaded):
    if not loaded: return 'MODEL_STARTUP_TIMEOUT' if elapsed>STARTUP_SECONDS else None
    return 'NO_RESPONSE_PROGRESS_TIMEOUT' if since_progress>NO_PROGRESS_SECONDS else None


def inference_command(key='qwen35_27b', script=None):
    # Reading a shell script via Bash does not require executable file mode.
    return ['/bin/bash',str(script if script is not None else CODE/'job.sh'),
            'infer','--stage','core','--model',key]


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run:
        print(json.dumps(dict(model='qwen35_27b',unchanged_inference=True,one_explicit_retry=True,
            startup_timeout=STARTUP_SECONDS,no_progress_timeout=NO_PROGRESS_SECONDS,automatic_retries=0))); return
    compute()
    if socket.gethostname().split('.')[0]=='nid0688': raise ValueError('KNOWN_RESET_REQUIRED_NODE_EXCLUDED')
    protocol=load(root/'resources/gpu_retry_v3_protocol.json'); check_entries(protocol['guard_files'])
    if protocol['status']!='PASS': raise ValueError('ENGINEERING_GUARD_TESTS_NOT_PASSED')
    gpu_ids=allocated_gpu_ids(os.environ)
    lock=load(root/'manifest/core_lock.json'); check_entries(lock['code'])
    if sha(root/'manifest/core_lock.json')!=protocol['unchanged_core_lock_sha256']: raise ValueError('CORE_LOCK_CHANGED')
    key='qwen35_27b'; out=root/'raw/core'/key
    if (out/'completion.json').exists() or (out/'progress.json').exists():
        raise ValueError('PRIOR_27B_OUTPUT_FOUND_NO_AUTOMATIC_OVERWRITE_OR_SELECTION')
    if out.exists() and any(out.glob('*.json')): raise ValueError('PRIOR_RESPONSE_FOUND')
    for model in ['qwen35_4b','qwen35_9b']:
        comp=load(root/'raw/core'/model/'completion.json')
        if comp['status']!='GENERATED' or comp['requests']!=lock['requests_per_model']: raise ValueError('PRESERVED_MODEL_NOT_COMPLETE')
    job=os.environ['SLURM_JOB_ID']; directory=root/'resources/gpu_retry_v3'/job
    directory.mkdir(parents=True,exist_ok=True)
    child=None; initial=time.monotonic(); last_progress=initial; loaded=False; previous=0
    class SupervisorStop(Exception): pass
    def stop(signum,frame): raise SupervisorStop('SUPERVISOR_SIGNAL_'+str(signum))
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    def terminate_child():
        if child is None or child.poll() is not None: return
        os.killpg(child.pid,signal.SIGTERM)
        try: child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGKILL)
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired: pass
    def health(first=False):
        command=['nvidia-smi','-i',gpu_ids,'-q','-x']
        result=subprocess.run(command,capture_output=True,text=True,timeout=12)
        if result.returncode: raise SupervisorStop('GPU_HEALTH_QUERY_FAILED:'+result.stderr[:300])
        observation=parse_health(result.stdout); observation.update(timestamp_utc=now(),node=socket.gethostname(),command=command)
        with (directory/'health_checks.jsonl').open('a') as f: f.write(json.dumps(observation)+'\n')
        if first or not observation['healthy']:
            save(directory/('initial_health.xml' if first else 'failed_health.xml'),result.stdout,'text')
        if not observation['healthy']: raise SupervisorStop('GPU_RECOVERY_ACTION_NOT_HEALTHY')
    try:
        health(first=True)
        command=inference_command(key)
        save(directory/'attempt.json',dict(status='EXPLICIT_INFRASTRUCTURE_RETRY_STARTED',job_id=job,
            node=socket.gethostname(),command=command,previous_incomplete_job='8173736',
            previous_launch_error='PermissionError: job.sh mode 0644 executed without Bash',
            previous_gpu_fault_job='8173347',previous_device_fault='GPU_RECOVERY_ACTION_RESET',previous_retained_27b_responses=0,
            logical_first_retained_response_attempt=1,physical_execution_attempt=3,
            core_lock=entry(root/'manifest/core_lock.json'),protocol=entry(root/'resources/gpu_retry_v3_protocol.json'),
            no_answer_based_retries=True,automatic_retries=0))
        child=subprocess.Popen(command,start_new_session=True)
        next_health=time.monotonic()+HEALTH_SECONDS
        while child.poll() is None:
            current=time.monotonic()
            if current>=next_health:
                health(); next_health=current+HEALTH_SECONDS
            if not loaded and (root/'environments/core'/key/(job+'.json')).exists():
                loaded=True; last_progress=current
            if (out/'progress.json').exists():
                progress=load(out/'progress.json'); count=progress['completed']
                if count<previous: raise SupervisorStop('PROGRESS_WENT_BACKWARDS')
                if count>previous: previous=count; last_progress=current; loaded=True
            reason=stall_reason(current-initial,current-last_progress,loaded)
            if reason: raise SupervisorStop(reason)
            save(directory/'supervisor_status.json',dict(status='RUNNING',completed=previous,expected=lock['requests_per_model'],
                model_loaded=loaded,seconds_since_progress=current-last_progress,elapsed_seconds=current-initial),frozen=False)
            time.sleep(POLL_SECONDS)
        if child.returncode: raise SupervisorStop('INFERENCE_EXIT_'+str(child.returncode))
        comp=load(out/'completion.json'); check_entries([comp['responses_file']])
        if comp['status']!='GENERATED' or comp['requests']!=lock['requests_per_model']: raise SupervisorStop('INCOMPLETE_OUTPUT')
        save(directory/'supervisor_status.json',dict(status='COMPLETE',completed=comp['requests'],expected=comp['requests'],
            physical_execution_attempt=3,no_answer_based_retries=True,automatic_retries=0),frozen=False)
        print('GUARDED_27B_COMPLETE',flush=True)
    except BaseException as exc:
        terminate_child()
        save(directory/'supervisor_failure.json',dict(status='STOPPED_NO_AUTOMATIC_RETRY',error=type(exc).__name__+': '+str(exc),
            completed=previous,model_loaded=loaded,timestamp_utc=now(),previous_outputs_preserved=True))
        print('GUARDED_27B_STOPPED: '+str(exc),flush=True)
        raise


if __name__=='__main__': main()
