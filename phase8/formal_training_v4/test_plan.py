import ast
from pathlib import Path
import unittest
from plan import *


def tiny():
    return {f'{level}_{world}_{sample}':dict(level=level,world=f'w{world}',
        answer=f'a{level}{world}{sample}',cot=f'c{level}{world}{sample}',
        pss_l4=['s4'] if world==0 else [],pss_full=['s0','s1'])
        for level in ('L1','L2','L3','L4') for world in range(3) for sample in range(2)}


class TestPlan(unittest.TestCase):
    def test_defaults_and_no_token_budget(self):
        validate_plan(DEFAULTS)
        for key in ('tokens_per_update','supervised_tokens'):
            with self.assertRaises(ValueError):validate_plan(dict(DEFAULTS,**{key:1024}))
        with self.assertRaises(ValueError):validate_plan(dict(DEFAULTS,attention_backend='math'))

    def test_shared_balanced_stream_and_resume(self):
        samples=tiny();a=ExampleSchedule(samples,SEEDS[0]);b=ExampleSchedule(samples,SEEDS[0])
        full=[a.at(i) for i in range(128)]
        self.assertEqual(full[64:],[b.at(i) for i in range(64,128)])
        self.assertEqual({samples[s]['world'] for s in full},{'w0','w1','w2'})
        self.assertEqual([samples[s]['level'] for s in full[:4]],['L1','L2','L3','L4'])

    def test_natural_complete_pool(self):
        samples=tiny();a=ExampleSchedule(samples,SEEDS[0],False)
        self.assertEqual(set(a.at(i) for i in range(len(samples))),set(samples))

    def test_rank_partition_no_overlap(self):
        for step in range(10):
            a=rank_indices(step,16,0);b=rank_indices(step,16,1)
            self.assertFalse(set(a)&set(b));self.assertEqual(sorted(a+b),list(range(step*16,(step+1)*16)))

    def test_equal_primary_weight_and_partial_cot(self):
        samples=tiny()
        for sid in samples:
            for method in METHODS:
                records=unit_records(samples,sid,method,SEEDS[0],3)
                self.assertEqual(sum(w for k,w in records),1)
                if method=='cot_partial':self.assertEqual(records,[(samples[sid]['cot'],1)])
                if method=='pss_l4' and not samples[sid]['pss_l4']:
                    self.assertEqual(records,[(samples[sid]['answer'],1)])

    def test_syntax_and_two_gpu_resources(self):
        for p in HERE.glob('*.py'):ast.parse(p.read_text())
        s=(HERE/'train_array.sbatch').read_text()
        for text in ('--gpus-per-node=2','--nproc_per_node=2','--array=0-9\n','--cpu-bind=none'):
            self.assertIn(text,s)
        self.assertNotIn('#SBATCH --dependency',s)
        self.assertNotIn('--exclusive',s)


if __name__=='__main__':unittest.main()
