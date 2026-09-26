"""Engineering fixtures only; never loads model predictions."""
import unittest
from b0common import *
from b0score import parse,score
from build import construct


class ParserTests(unittest.TestCase):
    def test_orders(self):
        gold=dict(schema=dict(kind='fact_verdict',order=['target_value','verdict']),fact_gold=2,claim_value=3,gold_verdict='CONTRADICTORY')
        a=score(dict(raw_response='{"target_value":2,"verdict":"SUPPORTED"}'),gold)
        self.assertTrue(a['same_run_fact_correct_verdict_wrong']); self.assertTrue(a['self_consistency_violation'])
        b=score(dict(raw_response='{"verdict":"CONTRADICTORY","target_value":2}'),gold)
        self.assertTrue(b['correct']); self.assertFalse(b['order_compliant'])
    def test_retained_prefix(self):
        g=dict(schema=dict(kind='fact_verdict',order=['target_value','verdict']),fact_gold=2,claim_value=3,gold_verdict='CONTRADICTORY')
        p=score(dict(raw_response='{"target_value":2,',truncated=True),g)
        self.assertTrue(p['fact_correct']); self.assertFalse(p['verdict_present']); self.assertIsNone(p['same_run_fact_correct_verdict_wrong'])
        p=score(dict(raw_response='{"target_value":2,"verdict":"CONTRADICTORY",',truncated=True),g)
        self.assertTrue(p['correct']); self.assertFalse(p['json_complete'])
    def test_no_invented_fields(self):
        sch=dict(kind='value',domain='count',nullable=True)
        for text in ['{"value":true}','{"value":"2"}','{"value":-1}','{"value":2,"value":3}','```json\n{"value":2}\n```','{"value":2e']:
            self.assertEqual(parse(dict(raw_response=text,truncated=False),sch)['status'],'INVALID')
        self.assertEqual(parse(dict(raw_response='{"value":2',truncated=True),sch)['status'],'INVALID')
    def test_null_and_unrun(self):
        g=dict(schema=dict(kind='value'),fact_gold=None,claim_value=None,gold_verdict=None)
        self.assertTrue(score(dict(raw_response='{"value":null}'),g)['correct'])
        self.assertEqual(score(None,g)['status'],'NOT_RUN')
        self.assertEqual(score(dict(raw_response='',infrastructure_error='OOM'),g)['status'],'INFRA_FAILURE')
    def test_schema_independent_components(self):
        g=dict(schema=dict(kind='fact_verdict',order=['target_value','verdict']),fact_gold=2,claim_value=3,gold_verdict='CONTRADICTORY')
        p=score(dict(raw_response='{"target_value":2,"verdict":"garbage"}'),g)
        self.assertTrue(p['fact_correct']); self.assertFalse(p['verdict_correct']); self.assertIsNone(p['self_consistency_violation'])
    def test_reused_gold_blind_scalar_alias(self):
        g=dict(schema=dict(kind='value'),fact_gold=2)
        raw=dict(raw_response='{"query_value":2}')
        before=dict(raw); p=score(raw,g)
        self.assertTrue(p['correct']); self.assertFalse(p['strict_contract_ok'])
        self.assertEqual(p['normalization'],'ALIAS_QUERY_VALUE_TO_VALUE'); self.assertEqual(raw,before)
        self.assertTrue(score(dict(raw_response='{"query_value":null}'),dict(g,fact_gold=None))['correct'])
        for text in ['{"value":2,"query_value":2}','{"query_value":2,"reason":"x"}']:
            p=score(dict(raw_response=text),g)
            self.assertEqual(p['status'],'INVALID'); self.assertFalse(p['fact_present'])


class DesignTests(unittest.TestCase):
    def test_fixed_structural_design(self):
        c=load(CODE/'config.json')
        ps=[]
        for n,(pre,post,op) in enumerate([(1,0,'REMOVE'),(3,2,'REMOVE'),(2,4,'ADD')]):
            ps.append(dict(group_id=str(n),world_id=str(n),underlying_world_id=str(n),cohort='ENGINEERING',values=dict(PRE=pre,POST=post),
                amount=abs(post-pre),operation=op,category='chair',full_media_context='PRE IMAGE. ACTION.',local_pre_context='PRE IMAGE.',
                media=[],source='FIXTURE',source_proof_sha256='fixture',source_truth_sha256='fixture'))
        req,gold,matches,unavailable=construct(c,ps); g={x['request_id']:x for x in gold}; rr={x['request_id']:x for x in req}
        self.assertEqual(len(req),len(rr)); self.assertTrue(any(x['delta']<0 for x in gold if x['delta'] is not None))
        self.assertTrue(unavailable)
        for r in req:
            self.assertEqual(set(r['payload']),{'system','text','media'})
            self.assertNotIn('fact_gold',r); self.assertNotIn('gold_verdict',r)
            if r['claim_value'] is not None: self.assertGreaterEqual(r['claim_value'],0)
            if r['condition']=='MISSING_FACTORIAL' and r['evidence']=='MISSING': self.assertIsNone(g[r['request_id']]['fact_gold'])
        for m in matches:
            x,y=rr[m['base_request_id']],rr[m['control_request_id']]
            self.assertEqual(x['underlying_world_id'],y['underlying_world_id'])
            self.assertEqual(x['payload']['media'],y['payload']['media'])
            if m['comparison']=='NEUTRAL_RECOUNT_REPEAT': self.assertEqual(x['payload'],y['payload'])
            if m['comparison']=='NO_INTERVENTION_TO_INTERVENTION':
                self.assertEqual(x['target'],'PRE'); self.assertEqual(g[x['request_id']]['fact_gold'],g[y['request_id']]['fact_gold'])
    def test_reproducible(self):
        self.assertEqual(load(CODE/'config.json')['offsets'],[-2,-1,0,1,2])
        from build import smoke
        self.assertEqual(smoke(load(CODE/'config.json')),smoke(load(CODE/'config.json')))


class AnalysisTests(unittest.TestCase):
    def test_csv_resume_preserves_existing_bytes(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix='b0_engineering_') as directory:
            path=Path(directory)/'fixture.csv'
            path.write_bytes(b'a,b\r\n1,2\r\n')
            before=path.read_bytes(); union_csv(path,[dict(a=1,b=2)])
            self.assertEqual(path.read_bytes(),before)
            with self.assertRaises(ValueError): union_csv(path,[dict(a=1,b=3)])
    def test_cluster_and_unavailable(self):
        from analyze import aggregate,stats
        c=dict(seed=20260908,bootstrap_repetitions=50)
        data=[dict(underlying_world_id='a',metric=True),dict(underlying_world_id='a',metric=False),
              dict(underlying_world_id='b',metric=None)]
        result=aggregate(data,[],['metric'],c)[0]
        self.assertEqual(result['estimate'],.5); self.assertEqual(result['cohort_worlds'],2)
        self.assertEqual(result['contributing_worlds'],1)
        signed=stats.estimate([('a',-1,1),('b',0,1)],['a','b'],repetitions=50)
        self.assertEqual(signed['estimate'],-.5)
        from decision import finalized_metric
        self.assertEqual(finalized_metric(data,'metric',c,{'a','b'})['estimate'],.5)
    def test_full_analysis_keeps_not_run(self):
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        import analyze
        c=load(CODE/'config.json'); c=dict(c,bootstrap_repetitions=30)
        panel=dict(group_id='engineering',world_id='engineering',underlying_world_id='engineering',cohort='B0_B',
            values=dict(PRE=2,POST=3),amount=1,operation='ADD',category='chair',full_media_context='FIXTURE ONLY',
            local_pre_context='FIXTURE ONLY',media=[],source='FIXTURE',source_proof_sha256='fixture',source_truth_sha256='fixture')
        req,gold,matches,_=construct(c,[panel])
        with tempfile.TemporaryDirectory(prefix='b0_analysis_engineering_') as directory:
            root=Path(directory)
            save(root/'inputs/core/requests.jsonl',req,'jsonl'); save(root/'private_gold/core.jsonl',gold,'jsonl')
            save(root/'02_B0_PANEL_MANIFEST.jsonl',[panel],'jsonl'); save(root/'manifest/matched_pairs.jsonl',matches,'jsonl')
            save(root/'manifest/core_lock.json',dict(code=[],inputs_sha256=sha(root/'inputs/core/requests.jsonl'),
                 private_gold_sha256=sha(root/'private_gold/core.jsonl')))
            args=SimpleNamespace(parse_args=lambda:SimpleNamespace(dry_run=False))
            with patch.object(analyze,'arguments',return_value=args),patch.object(analyze,'setup',return_value=(c,root)):
                analyze.main()
            decision=load(root/'B0_NEXT_STAGE_DECISION.json')
            self.assertEqual(decision['execution_status'],'PARTIAL_RETAIN_UNRUN')
            self.assertEqual(decision['recommended_whitebox'],'NONE')
            self.assertTrue(all(r['status']=='NOT_RUN' for r in csvrows(root/'03_B0_RAW_RESPONSES_WITH_PROMPTS.csv')))


if __name__=='__main__': unittest.main()
