import unittest
from contracts import count_label,legal_count_update,parse
from common import load,CODE
from compile_symbolic import compile_requests

S={'kind':'value','domain':'count','nullable':True}
class ContractTests(unittest.TestCase):
    def test_duplicate_rejected(self): self.assertEqual(parse('{"value":1,"value":2}',S)['status'],'INVALID')
    def test_nan_rejected(self): self.assertEqual(parse('{"value":NaN}',S)['status'],'INVALID')
    def test_bool_not_integer(self): self.assertEqual(parse('{"value":true}',S)['status'],'INVALID')
    def test_zero_retained(self): self.assertEqual(parse('{"value":0}',S)['component_values']['value'],0)
    def test_null_not_zero(self): self.assertIsNone(parse('{"value":null}',S)['component_values']['value'])
    def test_alias(self): self.assertEqual(parse('{"query_value":3}',S)['component_values']['value'],3)
    def test_ambiguous_alias(self): self.assertEqual(parse('{"value":3,"query_value":4}',S)['status'],'INVALID')
    def test_order_separate_from_content(self):
        s=dict(S,kind='joint',order=['value','verdict']); r=parse('{"verdict":"SUPPORTED","value":3}',s)
        self.assertEqual(r['status'],'VALID'); self.assertFalse(r['order_compliant'])
    def test_joint_query_set(self):
        s=dict(S,kind='facts',query_ids=['q1','q2'])
        self.assertEqual(parse('{"facts":[{"query_id":"q1","value":2},{"query_id":"q2","value":null}]}',s)['status'],'VALID')
        self.assertEqual(parse('{"facts":[{"query_id":"q1","value":2},{"query_id":"q1","value":2}]}',s)['status'],'INVALID')
    def test_lower_bound_refutes(self): self.assertEqual(count_label(2,None,1),'CONTRADICTORY')
    def test_lower_bound_allows(self): self.assertEqual(count_label(2,None,4),'UNKNOWN')
    def test_exact(self): self.assertEqual(count_label(2,2,2),'SUPPORTED')
    def test_inconsistent_not_unknown(self):
        with self.assertRaises(ValueError): count_label(3,2,2)
    def test_noop_and_nonzero_remove(self):
        self.assertEqual(legal_count_update(3,0,'NOOP'),3); self.assertEqual(legal_count_update(3,1,'REMOVE'),2)
    def test_illegal_remove(self):
        with self.assertRaises(ValueError): legal_count_update(0,1,'REMOVE')
    def test_symbolic_panel(self):
        c=load(CODE/'config.json'); r,g,m=compile_requests(c)
        self.assertEqual(len(r),768); self.assertEqual(len(g),768); self.assertEqual(len({x['world_cluster_id'] for x in r}),24)
        self.assertTrue(all(x['models']==c['models'] for x in r)); self.assertTrue(all(not x['payload']['media'] for x in r))
        self.assertTrue(all(set(x['payload'])=={'system','text','media'} for x in r))

if __name__=='__main__': unittest.main()
