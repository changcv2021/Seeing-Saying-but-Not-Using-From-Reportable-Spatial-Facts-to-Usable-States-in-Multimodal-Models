import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from common import write, sha, RUBRIC, metrics, judgment_valid
from output_policy import parse_prediction, generation_metadata, gate_usable
import base_score

class PrefixTests(unittest.TestCase):
    def row(self, text):
        return dict(raw_response=text,finish_reason='length',generated_tokens=512,error=None)

    def test_partial_reason_retains_label(self):
        p=parse_prediction(self.row('{"label":"SUPPORTED","confidence":0.8,"reason":"The cup is left of'))
        self.assertEqual(p['label'],'SUPPORTED')
        self.assertEqual(p['reason'],'The cup is left of')
        self.assertEqual(p['confidence'],0.8)
        self.assertFalse(p['strict_json_valid']);self.assertTrue(p['partial_reason'])
        self.assertTrue(gate_usable(p,self.row('')))

    def test_incomplete_label_not_guessed(self):
        self.assertIsNone(parse_prediction(self.row('{"label":"SUPPOR'))['label'])

    def test_label_inside_reason_not_extracted(self):
        p=parse_prediction(self.row('{"reason":"Use label SUPPORTED'))
        self.assertIsNone(p['label']);self.assertEqual(p['reason'],'Use label SUPPORTED')

    def test_missing_reason_does_not_erase_label(self):
        p=parse_prediction(self.row('{"label":"UNKNOWN",'))
        self.assertEqual(p['label'],'UNKNOWN');self.assertIsNone(p['reason'])

    def test_nontruncated_malformed_stays_invalid(self):
        row=self.row('{"label":"SUPPORTED",');row['finish_reason']='eos'
        self.assertIsNone(parse_prediction(row)['label'])

    def test_duplicate_key_rejected(self):
        p=parse_prediction(self.row('{"label":"SUPPORTED","label":"UNKNOWN","reason":"a'))
        self.assertIsNone(p['label']);self.assertIsNone(p['reason'])

    def test_invalid_prefix_syntax_rejected(self):
        p=parse_prediction(self.row('{"label":"SUPPORTED" xyz'))
        self.assertIsNone(p['label'])

    def test_complete_json_at_limit_scores(self):
        p=parse_prediction(self.row('{"label":"UNKNOWN","confidence":0.5,"reason":"Missing view."}'))
        self.assertTrue(p['schema_valid']);self.assertEqual(p['label'],'UNKNOWN')

    def test_incomplete_escape_not_completed(self):
        p=parse_prediction(self.row('{"reason":"left\\u00'))
        self.assertEqual(p['reason'],'left')
        p=parse_prediction(self.row('{"reason":"left'+'\\'))
        self.assertEqual(p['reason'],'left')

    def test_emitted_escape_decoded_only(self):
        p=parse_prediction(self.row('{"reason":"left\\nright\\u0020of'))
        self.assertEqual(p['reason'],'left\nright of')

    def test_unfinished_confidence_not_guessed(self):
        p=parse_prediction(self.row('{"label":"SUPPORTED","confidence":0.'))
        self.assertEqual(p['label'],'SUPPORTED');self.assertIsNone(p['confidence'])

    def test_token_boundary_eos(self):
        self.assertEqual(generation_metadata(511,2,[2])['finish_reason'],'eos')
        self.assertEqual(generation_metadata(512,2,[2])['finish_reason'],'eos')
        self.assertEqual(generation_metadata(512,3,[2])['finish_reason'],'length')

    def test_beyond_cap_discard_accounting(self):
        meta=generation_metadata(512,3,[2],600)
        self.assertEqual(meta['discarded_tokens'],88);self.assertEqual(meta['generated_tokens'],512)
        with self.assertRaises(ValueError):generation_metadata(513,3,[2])

    def test_unbounded_text_cannot_be_scored(self):
        row=self.row('{}');row['generated_tokens']=513
        with self.assertRaises(ValueError):parse_prediction(row)

    def test_rubric_cannot_quote_unwritten_suffix(self):
        p=parse_prediction(self.row('{"reason":"The cup is'))
        self.assertFalse(judgment_valid(dict(criterion_id='R2',met=True,evidence='left of the plate'),'R2',p['reason']))

    def test_integrated_truncated_label_and_explanation_can_score(self):
        with tempfile.TemporaryDirectory(prefix='sc512_score_') as tmp:
            root=Path(tmp);pred=dict(self.row('{"label":"SUPPORTED","confidence":0.8,"reason":"The cup is left of the plate.'),sample_id='s')
            gold=dict(sample_id='s',level='L1',dataset='synthetic',track='GEO-TOPO',split='test',origin='synthetic',dependency_type='CORE',gold='SUPPORTED',component='binary',pair_id='p')
            write(root/'smoke.jsonl',[dict(sample_id='s')],jsonl=True)
            write(root/'private_gold.jsonl',[gold],jsonl=True);write(root/'rubric.json',RUBRIC)
            write(root/'smoke/predictions_000.jsonl',[pred],jsonl=True)
            judgment=dict(sample_id='s',prediction_sha256=hashlib.sha256(json.dumps(pred,sort_keys=True).encode()).hexdigest(),
                          criteria={k:dict(criterion_id=k,met=True,evidence='The cup is left of the plate.') for k in RUBRIC['criteria']})
            write(root/'smoke_judge/judgments_000.jsonl',[judgment],jsonl=True)
            base_score.score(argparse.Namespace(run_root=root,run_id='test',scope='smoke',gate=True))
            report=json.loads((root/'smoke_score.json').read_text())
            self.assertEqual(report['overall']['n'],1);self.assertEqual(report['overall']['claim_accuracy'],1)
            self.assertEqual(report['explanation_rubric_score'],100);self.assertEqual(report['status'],'PASS')
            diag=json.loads((root/'smoke_diagnostics.json').read_text())
            self.assertEqual(diag['complete_schema_valid'],0);self.assertEqual(diag['scoring_usable'],1)

if __name__=='__main__':unittest.main()
