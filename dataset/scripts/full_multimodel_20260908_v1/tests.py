"""Synthetic output-interface fixtures, no benchmark labels used for parser design."""
import ast, json, unittest
from campaign import ROOT,CODE,args,frozen
from common import parse,metrics
from output_policy import parse_prediction
from infer import final_text
from judge import _decode_judge,_valid_raw

class Tests(unittest.TestCase):
    def test_fences_and_prefix(self):
        for label in ['SUPPORTED','CONTRADICTORY','UNKNOWN']:
            obj=dict(label=label,confidence=.75,reason='Explicit fixture reason.')
            for raw in [json.dumps(obj),'```json\n'+json.dumps(obj)+'\n```']:
                self.assertEqual(parse_prediction(dict(raw_response=raw))['label'],label)
            raw='{"label":"'+label+'","confidence":0.75,"reason":"unfinished'
            parsed=parse_prediction(dict(raw_response=raw,generated_tokens=512,finish_reason='length'))
            self.assertEqual(parsed['label'],label);self.assertEqual(parsed['reason'],'unfinished')
    def test_no_guessing(self):
        for text in ['{"reason":"The answer is SUPPORTED"}','{"label":"SUPPORT','{"label":"SUPPORTED","label":"UNKNOWN"}',
                     'Example {"label":"SUPPORTED"}. Actual answer unknown.', '{"label":"SUPPORTED","confidence":NaN}']:
            self.assertIsNone(parse_prediction(dict(raw_response=text))['label'])
    def test_truncation_is_not_automatic_zero(self):
        raw='{"label":"SUPPORTED","reason":"visible","confidence":0.8}'
        self.assertEqual(parse_prediction(dict(raw_response=raw,generated_tokens=512,finish_reason='length'))['label'],'SUPPORTED')
    def test_think_final_separation(self):
        final='{"label":"UNKNOWN","confidence":0.4,"reason":"gap"}'
        self.assertEqual(final_text('reason </think>'+final,'','thinking')[0],final)
        self.assertEqual(final_text('{"label":"SUPPORTED"}','<think>{"label":"SUPPORTED"}','thinking')[0],'')
        self.assertEqual(final_text(final,final,'direct')[0],final)
        self.assertEqual(final_text('','<|channel>thought\nreason\n<channel|>'+final+'<end_of_turn>','direct')[0],final)
    def test_primary_scoring(self):
        r=[dict(gold='SUPPORTED',label='SUPPORTED',component='binary',pair_id='p'),dict(gold='CONTRADICTORY',label='CONTRADICTORY',component='binary',pair_id='p')]
        self.assertEqual(metrics(r)['pair_accuracy'],1);r[1]['label']=None
        self.assertEqual(metrics(r)['claim_accuracy'],.5);self.assertEqual(metrics(r)['pair_accuracy'],0)
    def test_judge_outer_fence(self):
        raw='{"criterion_id":"R1","met":true,"evidence":"visible object"}'
        self.assertTrue(_valid_raw('```json\n'+raw+'\n```','R1','The visible object is present.'))
        self.assertIsNone(_decode_judge('{"criterion_id":"R1","met":false,"met":true,"evidence":"visible object"}'))
        self.assertFalse(_valid_raw(raw,'R1','No matching quote.'))

if __name__=='__main__':
    a=args()
    if not a.dry_run:
        for path in CODE.glob('*.py'):ast.parse(path.read_text())
        results=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
        frozen(ROOT/'parser_tests_with_judge.json',dict(status='PASS' if results.wasSuccessful() else 'FAIL',tests=results.testsRun,model_calls=0))
        if not results.wasSuccessful():raise SystemExit(1)
