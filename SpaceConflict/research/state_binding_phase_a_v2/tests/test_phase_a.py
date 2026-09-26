import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metrics import parse, observed_object, estimate, conditional_estimate
from base import cluster
from build import public, local_action_arguments
from analysis_outputs import matched_rows, original_statistics, supplemental
from request_identity import execution_identity
from preflight import media_paths
from decision import decide
from design_audit import near_balanced, inspect_design
from accounting import summarize

D={'type':'nonnegative_integer','binary_degenerate':False}
def raw(text,cut=False): return {'raw_response':text,'truncated':cut}

class PhaseATests(unittest.TestCase):
    def test_value(self):
        self.assertTrue(parse(raw('{"status":"VALUE","value":4}'),{'kind':'value','value':4,'domain':D})['correct'])
    def test_bool_is_not_count(self):
        self.assertEqual(parse(raw('{"status":"VALUE","value":true}'),{'kind':'value','value':1,'domain':D})['status'],'INVALID')
    def test_undetermined_not_unknown_label(self):
        self.assertEqual(parse(raw('{"status":"UNDETERMINED","value":null}'),{'kind':'value','value':0,'domain':D})['status'],'UNDETERMINED')
    def test_complete_prefix_retained(self):
        self.assertTrue(parse(raw('{"status":"VALUE","value":4,"reason":"unfinished',True),{'kind':'value','value':4,'domain':D})['correct'])
    def test_cut_integer_not_completed(self):
        self.assertEqual(parse(raw('{"status":"VALUE","value":4',True),{'kind':'value','value':4,'domain':D})['status'],'INVALID')
    def test_duplicate_rejected(self):
        for cut in [True,False]: self.assertEqual(observed_object('{"value":4,"value":7}',cut),{})
    def test_multiple_json_rejected(self):
        self.assertEqual(observed_object('{"value":4}{"value":7}',True),{})
    def test_joint_binding_swap(self):
        pred=parse(raw('{"X":{"status":"VALUE","value":3},"Y":{"status":"VALUE","value":2}}'),{'kind':'joint','gold_by_state':{'X':2,'Y':3},'domain':D})
        self.assertEqual(pred['classifier'],'VALUES_RIGHT_BINDING_WRONG')
        self.assertFalse(pred['correct'])
    def test_missing_not_zero(self):
        self.assertIsNone(parse(None,{'kind':'value'})['correct'])
        self.assertIsNone(estimate([])['estimate'])
    def test_conditional_empty_worlds_stay_in_bootstrap(self):
        e=conditional_estimate([{'cluster_id':'a','correct':True,'eligible':True},{'cluster_id':'b','correct':False,'eligible':False}],predicate='eligible',repetitions=100)
        self.assertEqual(e['cohort_clusters'],2)
        self.assertEqual(e['clusters'],1)
        self.assertEqual(e['estimate'],1)
        self.assertGreater(e['zero_denominator_bootstrap_fraction'],0)
    def test_infrastructure_not_unknown(self):
        self.assertEqual(parse({'infrastructure_error':'OOM'},{'kind':'verdict'})['status'],'INVALID')
    def test_label_mapping(self):
        self.assertTrue(parse(raw('{"label_code":"B"}'),{'kind':'verdict','label':'SUPPORTED','field':'label_code','mapping':{'B':'SUPPORTED','A':'CONTRADICTORY','C':'UNKNOWN'}})['correct'])
    def test_bad_mapped_type_stays_failure(self):
        self.assertEqual(parse(raw('{"label_code":[]}',True),{'kind':'verdict','label':'SUPPORTED','field':'label_code','mapping':{'A':'SUPPORTED'}})['status'],'INVALID')
    def test_joint_extra_state_rejected(self):
        self.assertEqual(parse(raw('{"X":{"status":"VALUE","value":2},"Y":{"status":"VALUE","value":3},"Z":4}'),{'kind':'joint','gold_by_state':{'X':2,'Y':3},'domain':D})['status'],'INVALID')
    def test_joint_undetermined_placeholder_never_scores_as_gold(self):
        p=parse(raw('{"X":{"status":"UNDETERMINED","value":0},"Y":{"status":"VALUE","value":1}}'),{'kind':'joint','gold_by_state':{'X':0,'Y':1},'domain':D})
        self.assertFalse(p['correct'])
        self.assertIsNone(p['values']['X'])
        self.assertEqual(p['state_statuses']['X'],'UNDETERMINED')
        self.assertTrue(p['schema_warnings'])
    def test_v24_explicit_null_contract_is_strict(self):
        p=parse(raw('{"X":{"status":"UNDETERMINED","value":0}}'),{'kind':'joint','gold_by_state':{'X':0},'domain':D,'require_null_for_undetermined':True})
        self.assertEqual(p['status'],'INVALID')
        self.assertFalse(p['correct'])
    def test_action_target_word_boundary(self):
        g={'kind':'action','operation':'REMOVE','scope':'whole_scene','target_terms':['chair']}
        self.assertFalse(parse(raw('{"status":"RESOLVED","operation":"REMOVE","target":"armchair","scope":"whole_scene"}'),g)['correct'])
    def test_replacement_both_categories(self):
        g={'kind':'action','operation':'REPLACE','scope':'whole_scene','target_terms':['chair','table']}
        self.assertFalse(parse(raw('{"status":"RESOLVED","operation":"REPLACE","target":"chair","scope":"whole_scene"}'),g)['correct'])
    def test_public_removes_truth(self):
        self.assertNotIn('private',public({'private':{'values':{'X':5}},'group_id':'g'}))
    def test_local_excludes_computed_poststate(self):
        self.assertEqual(local_action_arguments({'post_predicate':'RIGHT_OF','pre_predicate':'LEFT_OF','count_deltas':{'chair':-1},'target_id':'object1','category':'chair'}),{'target_id':'object1','category':'chair'})
    def test_known_scene_alias(self):
        self.assertEqual(cluster('hypo3d:scene0012_00'),'scannet:scene0012_00')
        self.assertEqual(cluster('hypo3d:unknown_alias'),'hypo3d:unknown_alias')
    def sample(self, correct=True, rid='a', label='SUPPORTED'):
        return dict(model='m',group_id='g',target='X',claim_id='c',cluster_id='world',
            condition='A',variant='base',request_id=rid,raw_path=rid,source='source',level='L4',state_dimension='PRE_POST',
            provenance_type='DERIVED',is_oracle=False,correct=correct,gold={'kind':'verdict','label':label,'pair_id':'pair'},
            prediction={'status':'VALID' if correct else 'INVALID','label':label if correct else 'INVALID'})
    def test_matched_rescue_keeps_invalid_denominator(self):
        a,b=self.sample(False),self.sample(True,'b')
        rows=matched_rows([a],[b],'contrast')
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['rescue']); self.assertFalse(rows[0]['harm'])
        self.assertEqual(rows[0]['net'],1)
    def test_matched_duplicate_hard_failure(self):
        a=self.sample()
        with self.assertRaises(ValueError): matched_rows([a,a],[a],'duplicate')
    def test_matched_unequal_truth_hard_failure(self):
        with self.assertRaises(ValueError): matched_rows([self.sample()],[self.sample(label='CONTRADICTORY')],'truth')
    def test_unrun_member_never_scored_zero(self):
        a=self.sample(); a['correct']=None
        with self.assertRaises(ValueError): matched_rows([a],[self.sample()],'unrun')
    def test_original_pair_all_members_required(self):
        with self.assertRaises(ValueError): original_statistics([self.sample()],{'bootstrap_repetitions':10})
        a=self.sample(); b=self.sample(False,'b','CONTRADICTORY')
        e=original_statistics([a,b],{'bootstrap_repetitions':10})
        self.assertEqual(e['OriginalClaimAcc']['denominator'],2)
        self.assertEqual(e['OriginalPairAcc']['estimate'],0)
        self.assertIsNone(e['UnknownRecall']['estimate'])
    def test_cache_identity_all_query_axes(self):
        cfg={'seed':20260907,'max_new_tokens':512}
        r={'condition':'SELECT_VALUE','target':'X','claim_id':'claim1','group_id':'g','cluster_id':'w','variant':'base','alias_map':{'X':'K'},'label_map':{'A':'SUPPORTED'},'prompt_version':'v24'}
        original=execution_identity('revision',r,cfg,'pixels','prompt')
        for field in r:
            self.assertNotEqual(original,execution_identity('revision',{**r,field:'changed'},cfg,'pixels','prompt'))
        self.assertNotEqual(original,execution_identity('revision',r,cfg,'other_pixels','prompt'))
        self.assertNotEqual(original,execution_identity('revision',r,cfg,'pixels','other_prompt'))
        self.assertNotEqual(original,execution_identity('other_revision',r,cfg,'pixels','prompt'))
        self.assertNotEqual(original,execution_identity('revision',r,{**cfg,'max_new_tokens':256},'pixels','prompt'))
    def test_media_preflight_supports_existing_frame_lists(self):
        self.assertEqual(media_paths({'kind':'image','path':'a.png'}),['a.png'])
        self.assertEqual(media_paths({'kind':'video','path':'clip.mp4'}),['clip.mp4'])
        self.assertEqual(media_paths({'kind':'video_frames','paths':['1.png','2.png']}),['1.png','2.png'])
        with self.assertRaises(ValueError): media_paths({'kind':'video_frames','paths':[]})
        with self.assertRaises(ValueError): media_paths({'kind':'unrecognized','path':'x'})
    def test_decision_no_nonprimary_cherry_picking(self):
        comparisons=[{'model':'qwen35_4b','contrast':name,'ci95':[.2,.6],'n_clusters':5} for name in ['IntrusionExcess','AccuracyCost']]
        decision=decide(True,[],{'interventions':[]},comparisons)
        self.assertEqual(decision['candidate'],'MIXED_OR_UNRESOLVED')
        self.assertFalse(decision['auto_execute'])
    def test_positive_decision_remains_oracle_candidate_only(self):
        comparisons=[{'model':'qwen35_9b','contrast':name,'ci95':[.2,.6],'n_clusters':5} for name in ['IntrusionExcess','AccuracyCost']]
        decision=decide(True,[],{'interventions':[]},comparisons)
        self.assertEqual(decision['candidate'],'ORACLE_TEXT_NON_TARGET_INTERFERENCE_CANDIDATE')
        self.assertFalse(decision['allow_whitebox'])
        self.assertFalse(decision['allow_training'])
    def test_one_world_not_replicated_evidence(self):
        comparisons=[{'model':'qwen35_9b','contrast':name,'ci95':[1,1],'n_clusters':1} for name in ['IntrusionExcess','AccuracyCost']]
        self.assertEqual(decide(True,[],{'interventions':[]},comparisons)['candidate'],'MIXED_OR_UNRESOLVED')
    def test_counterbalance_counts_include_missing_levels(self):
        self.assertFalse(near_balanced({'PRE':11}, ['PRE','POST']))
        self.assertTrue(near_balanced({'PRE':6,'POST':5}, ['PRE','POST']))
        self.assertFalse(near_balanced({}, ['PRE','POST']))
    def test_random_alias_is_not_semantic_output_order_balance(self):
        groups=[{'group_id':'g'+str(i),'states':[{'alias':x,'role':'PRE'},{'alias':y,'role':'POST'}]} for i,(x,y) in enumerate([('X','Y'),('Y','X')])]
        requests=[dict(group_id=g['group_id'],cluster_id=g['group_id'],request_id=g['group_id'],condition='FACT_JOINT',state_dimension='PRE_POST',
            payload={'text':'REPORT ORDER: '+', '.join(s['alias'] for s in g['states'])+'.'}) for g in groups]
        audit=inspect_design(requests,groups)
        self.assertEqual(audit['checks'][0]['first_role_counts'],{'PRE':2})
        self.assertEqual(audit['checks'][0]['status'],'FAIL')
        self.assertFalse(audit['inspected_model_outputs'])
    def test_accounting_gpu_total_not_double_counted(self):
        a=summarize('1|COMPLETED|0:0|3600|4|cpu=4,gres/gpu=2,gres/gpu:a100=2|n1|\n',['1'])
        self.assertEqual(a['allocated_gpu_hours_to_query'],2)
        self.assertTrue(a['all_listed_jobs_terminal'])
    def test_accounting_pending_not_completed_or_future_zero(self):
        a=summarize('1|PENDING|0:0|0|4||None|\n',['1'])
        self.assertEqual(a['allocated_gpu_hours_to_query'],0)
        self.assertFalse(a['all_listed_jobs_terminal'])
    def test_accounting_failed_allocations_count(self):
        a=summarize('1|FAILED|1:0|1800|4|gres/gpu=1|n1|\n',['1'])
        self.assertEqual(a['allocated_gpu_hours_to_query'],.5)
        self.assertTrue(a['all_listed_jobs_terminal'])
    def test_accounting_missing_or_duplicate_jobs_not_hidden(self):
        line='1|COMPLETED|0:0|1|4|gres/gpu=1|n1|\n'
        self.assertEqual(summarize(line,['1','2'])['status'],'FAIL')
        with self.assertRaises(ValueError): summarize(line+line,['1'])
    def test_supplemental_perfect_synthetic_fixture(self):
        # Synthetic unit fixture only: never a model run or benchmark result.
        import tempfile
        from base import write
        models=['qwen35_4b','qwen35_9b','qwen35_27b']
        cfg={'models':models,'bootstrap_repetitions':20,'seed':20260907}
        per=[]; fm=[]
        for model in models:
            def row(condition,rid,target=None,kind='value',value=2,label='SUPPORTED'):
                return dict(model=model,group_id='g',cluster_id='w',request_id=model+rid,condition=condition,variant='base',
                    target=target,claim_id=None,source='synthetic',level='L4',state_dimension='PRE_POST',provenance_type='SYNTHETIC_TEST_ONLY',
                    is_oracle=False,correct=True,raw_path='SYNTHETIC_NOT_A_FILE',label_evidence=[],
                    gold={'kind':kind,'value':value,'label':label},prediction={'status':'VALUE' if kind=='value' else 'VALID','value':value,'label':label})
            for target,val in [('X',2),('Y',3)]:
                for cond in ['FACT_SEPARATE','SELECT_VALUE']:
                    per.append(row(cond,cond+target,target,value=val))
            j=row('FACT_JOINT','j',kind='joint'); j['prediction']['classifier']='EXACT'; per.append(j)
            for lab in ['SUPPORTED','CONTRADICTORY']:
                r=row('D_ORIG','orig'+lab,kind='verdict',label=lab)
                r['gold']['pair_id']='p'; per.append(r)
            fm.append(dict(model=model,group_id='g',SeparateAllStatesCorrect=True,JointStateMapExact=True))
        with tempfile.TemporaryDirectory(prefix='synthetic_stats_',dir=Path(__file__).resolve().parent) as temp:
            root=Path(temp)
            write(root/'manifest/discovery/state_group_manifest.jsonl',[{'group_id':'g','cluster_id':'w','states':[{'alias':'X','role':'PRE'},{'alias':'Y','role':'POST'}]}],'jsonl')
            summary,_=supplemental(cfg,root,per,fm,[],models)
            self.assertEqual(summary['common_fact_groups'],1)
            self.assertEqual(summary['common_joint_groups'],1)
            for model in models:
                self.assertEqual(summary['original'][model]['OriginalPairAcc']['estimate'],1)
                self.assertEqual(summary['value_switch'][model]['correct']['estimate'],1)
                self.assertEqual(summary['joint'][model]['binding_swap']['estimate'],0)

if __name__=='__main__': unittest.main()
