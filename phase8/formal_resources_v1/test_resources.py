import unittest
from pathlib import Path
from resource_tools import load,read,HERE,scheduler_profile_command

class Resources(unittest.TestCase):
    def test_ten_runs(self):
        p,r=load();self.assertEqual(len(r),10)
        self.assertEqual({x['seed'] for x in r},{20260922,20260923})
        for m in {x['method'] for x in r}:self.assertEqual(len([x for x in r if x['method']==m]),2)
    def test_independent(self):
        p,r=load();text=(HERE/'train_array.sbatch').read_text()
        self.assertIn('#SBATCH --array=0-9\n',text)
        self.assertNotIn('#SBATCH --dependency',text)
        self.assertEqual(p['concurrency']['inter_run_dependencies'],[])
    def test_resources(self):
        p,r=load()
        self.assertEqual(p['resources']['gpus_per_node'],1)
        self.assertEqual(p['resources']['walltime_seconds'],48*3600)
        self.assertIsNone(p['budget']['global_walltime_cap'])
        self.assertFalse(p['resources']['exclusive'])
    def test_cot_pool(self):
        _,r=load()
        for run in r:
            c=read(run['config'])
            if c['method']=='cot_partial':self.assertIn('/partial_cot_approved_v1/',c['target_file'])
    def test_no_training_during_scheduler_check(self):
        p,_=load();cmd=scheduler_profile_command(p)
        self.assertIn('--test-only',cmd);self.assertIn('--wrap=/bin/true',cmd)
    def test_no_output_collision(self):
        _,r=load();self.assertEqual(len({x['output_dir'] for x in r}),10)
    def test_unchanged_test_scope(self):
        _,r=load()
        for x in r:
            c=read(x['config']);self.assertEqual(c['test_input_count'],5608)
            self.assertEqual(c['evaluation_scope'],'held_out_test')
    def test_versioned_state_interface_selected(self):
        p,_=load();i=p['state_interface']
        self.assertEqual(i['version'],'state_interface_v2')
        self.assertEqual(i['encoder'],'encode_state_v2')
        self.assertEqual(i['scorer'],'score_state_response')
        self.assertTrue(Path(i['module']).is_file())

if __name__=='__main__':unittest.main()
