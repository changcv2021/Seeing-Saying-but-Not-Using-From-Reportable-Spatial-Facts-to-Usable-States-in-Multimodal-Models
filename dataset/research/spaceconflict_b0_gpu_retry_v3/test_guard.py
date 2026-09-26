"""CPU engineering fixtures for a read-only GPU-health and progress supervisor."""
import unittest
import tempfile
import stat
import subprocess
from guard import *


class GuardTests(unittest.TestCase):
    def xml(self,action='None',extra=''):
        return '<nvidia_smi_log><driver_version>fixture</driver_version>'+''.join(
            '<gpu id="'+str(i)+'"><uuid>fixture'+str(i)+'</uuid><gpu_recovery_action>'+action+'</gpu_recovery_action>'+extra+'</gpu>' for i in [0,1])+'</nvidia_smi_log>'
    def test_device_health(self):
        self.assertTrue(parse_health(self.xml())['healthy'])
        for action in ['Reset','Reboot','Drain and Reset','N/A','']:
            self.assertFalse(parse_health(self.xml(action))['healthy'])
        self.assertFalse(parse_health(self.xml(extra='<pstate>GPU requires reset</pstate>'))['healthy'])
        self.assertFalse(parse_health('<nvidia_smi_log><gpu><uuid>fixture</uuid></gpu></nvidia_smi_log>')['healthy'])
    def test_deadlines(self):
        self.assertIsNone(stall_reason(400,400,False))
        self.assertEqual(stall_reason(901,901,False),'MODEL_STARTUP_TIMEOUT')
        self.assertIsNone(stall_reason(9000,20,True))
        self.assertEqual(stall_reason(1000,301,True),'NO_RESPONSE_PROGRESS_TIMEOUT')
    def test_allocation_scope(self):
        self.assertEqual(allocated_gpu_ids({'SLURM_JOB_GPUS':'1,3','CUDA_VISIBLE_DEVICES':'0,1'}),'1,3')
        for value in ['', '0', '0,0', '0-1', '0,1,2,3']:
            with self.assertRaises(ValueError): allocated_gpu_ids({'SLURM_JOB_GPUS':value})

    def test_explicit_bash_for_nonexecutable_script_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='b0 nonexecutable fixture ') as directory:
            path=Path(directory)/'job with spaces.sh'
            path.write_text('#!/bin/bash\nprintf "%s\\n" "$@"\n')
            path.chmod(0o644)
            self.assertFalse(path.stat().st_mode & stat.S_IXUSR)
            cmd=inference_command(script=path)
            self.assertEqual(cmd[:2],['/bin/bash',str(path)])
            result=subprocess.run(cmd,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.splitlines(),['infer','--stage','core','--model','qwen35_27b'])
    def test_real_frozen_launcher_cpu_dry_run(self):
        command=inference_command()+['--dry-run']
        result=subprocess.run(command,capture_output=True,text=True,timeout=240)
        self.assertEqual(result.returncode,0,result.stderr[-3000:])
        messages=[]
        for line in result.stdout.splitlines():
            try: messages.append(json.loads(line))
            except ValueError: pass
        self.assertIn(dict(stage='core',model='qwen35_27b',requests=1424,status='PLANNED_NOT_GENERATED'),messages)
        args=arguments(__doc__).parse_args(); _,root=setup(args)
        save(root/'resources/gpu_retry_v3_launcher_dry_run.json',dict(status='PASS',job=os.environ['SLURM_JOB_ID'],
             command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,model_calls=0))


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('GPU health/deadline engineering fixtures only; no model calls.'); return
    compute()
    old=load(root/'resources/gpu_retry_v2_protocol.json'); check_entries(old['guard_files'])
    lock=load(root/'manifest/core_lock.json'); check_entries(lock['code'])
    if sha(root/'manifest/core_lock.json')!=old['unchanged_core_lock_sha256']: raise ValueError('CORE_LOCK_CHANGED')
    for key in ['qwen35_4b','qwen35_9b']:
        comp=load(root/'raw/core'/key/'completion.json'); check_entries([comp['responses_file']])
        if comp['status']!='GENERATED' or comp['requests']!=1424: raise ValueError('PRESERVED_MODEL_INCOMPLETE')
    if (root/'raw/core/qwen35_27b').exists() and any((root/'raw/core/qwen35_27b').glob('*.json')):
        raise ValueError('27B_RAW_OUTPUT_FOUND_PRESERVE_BEFORE_RETRY')
    subprocess.run(['/bin/bash','-n',str(CODE/'job.sh')],check=True)
    import ast
    for path in GUARD_CODE.glob('*.py'): ast.parse(path.read_text(),filename=str(path))
    results=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GuardTests))
    record=dict(status='PASS' if results.wasSuccessful() else 'FAIL',tests=results.testsRun,model_calls=0,
        guard_files=[entry(path) for path in sorted(GUARD_CODE.glob('*')) if path.suffix in ['.py','.sh']],
        unchanged_core_lock_sha256=sha(root/'manifest/core_lock.json'),
        authority='2026-09-08 user explicitly requested fix PermissionError then resubmit B0 27B; no answer-based retry.',
        request_limit=1424,excluded_nodes=['nid0688'],automatic_retries=0,
        launcher_fix='EXPLICIT_BASH_NO_EXECUTABLE_PERMISSION_REQUIRED',physical_execution_attempt=3,
        preserved_prior_failed_jobs=['8173347','8173736'],runtime_walltime='48:00:00',
        timing_scope='Site per-allocation maximum; frozen config resource metadata superseded by user scheduling instruction.',
        startup_seconds=STARTUP_SECONDS,no_progress_seconds=NO_PROGRESS_SECONDS,health_check_seconds=HEALTH_SECONDS)
    save(root/'resources/gpu_retry_v3_protocol.json',record)
    if not results.wasSuccessful(): raise SystemExit(1)


if __name__=='__main__': main()
