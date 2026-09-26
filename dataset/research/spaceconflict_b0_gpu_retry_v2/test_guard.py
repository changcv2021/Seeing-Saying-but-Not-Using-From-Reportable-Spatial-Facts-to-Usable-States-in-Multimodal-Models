"""CPU engineering fixtures for a read-only GPU-health and progress supervisor."""
import unittest
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


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('GPU health/deadline engineering fixtures only; no model calls.'); return
    compute()
    import ast
    for path in GUARD_CODE.glob('*.py'): ast.parse(path.read_text(),filename=str(path))
    results=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GuardTests))
    record=dict(status='PASS' if results.wasSuccessful() else 'FAIL',tests=results.testsRun,model_calls=0,
        guard_files=[entry(path) for path in sorted(GUARD_CODE.glob('*')) if path.suffix in ['.py','.sh']],
        unchanged_core_lock_sha256=sha(root/'manifest/core_lock.json'),
        authority='User explicitly requested 重新提交这个27; retry only the interrupted 27B on a healthy node.',
        request_limit=1424,excluded_nodes=['nid0688'],automatic_retries=0,
        startup_seconds=STARTUP_SECONDS,no_progress_seconds=NO_PROGRESS_SECONDS,health_check_seconds=HEALTH_SECONDS)
    save(root/'resources/gpu_retry_v2_protocol.json',record)
    if not results.wasSuccessful(): raise SystemExit(1)


if __name__=='__main__': main()
