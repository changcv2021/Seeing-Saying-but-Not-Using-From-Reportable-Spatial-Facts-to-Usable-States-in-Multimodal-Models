"""Small deterministic tests; dataset-wide checks run in the CPU audit."""
import ast
import unittest
from plan import *


def unit(i,stream):
    return dict(sample_id=str(i),source_index=i,records=[('answer:'+str(i),.5),('state:'+str(i),.5)],stream=stream)


class PreservedTests(unittest.TestCase):
    def test_original_order_and_weight_preserved(self):
        base=[unit(i,'preserved_l4') for i in range(48)]
        extra=[unit(i+100,'added_l1_l3_alignment') for i in range(19)]
        result,padding=interleave(base,extra)
        self.assertEqual(padding,13)
        self.assertEqual([u for u in result if u['stream']=='preserved_l4'],base)
        self.assertEqual(len(result),80)
        self.assertEqual([u for u in result if u['stream']=='added_l1_l3_alignment'][:19],extra)
        for index in range(0,len(result),16):
            self.assertEqual(len({u['stream'] for u in result[index:index+16]}),1)

    def test_more_additions_than_base(self):
        base=[unit(i,'preserved_l4') for i in range(16)]
        extra=[unit(i+100,'added_l1_l3_alignment') for i in range(99)]
        result,padding=interleave(base,extra)
        self.assertEqual(len(result),128)
        self.assertEqual(padding,13)

    def test_cannot_silently_drop_alignment(self):
        with self.assertRaises(ValueError):interleave([unit(i,'preserved_l4') for i in range(16)],[])

    def test_shared_hyperparameters(self):
        candidate=dict(DEFAULTS,optimizer_updates=4000)
        validate_plan(candidate)
        for key in ('learning_rate','weight_decay','lora_rank','lora_alpha','lora_dropout','max_grad_norm'):
            wrong=dict(candidate);wrong[key]+=1
            with self.assertRaises(ValueError):validate_plan(wrong)

    def test_rank_unit_accounting(self):
        a=rank_indices(3,16,0);b=rank_indices(3,16,1)
        self.assertEqual(sorted(a+b),list(range(48,64)))
        self.assertFalse(set(a)&set(b))

    def test_all_local_python_syntax(self):
        for path in HERE.glob('*.py'):ast.parse(path.read_text(),filename=str(path))

    def test_real_audit_if_present(self):
        path=OUTPUT/'audit/EXPOSURE_AUDIT.json'
        if not path.exists():self.skipTest('CPU audit not yet complete')
        audit=read(path)
        for seed in SEEDS:
            olde=audit['audits'][f'pss_l4__seed_{seed}']['exposure']
            new=audit['audits'][f'{METHOD}__seed_{seed}']
            self.assertEqual(new['l4_before'],new['l4_after'])
            self.assertGreater(new['exposure']['optimizer_updates'],olde['optimizer_updates'])
            self.assertGreater(new['l1_l3_alignment_exposures']['L1'],0)
            self.assertGreater(new['l1_l3_alignment_exposures']['L3'],0)


if __name__=='__main__':unittest.main()
