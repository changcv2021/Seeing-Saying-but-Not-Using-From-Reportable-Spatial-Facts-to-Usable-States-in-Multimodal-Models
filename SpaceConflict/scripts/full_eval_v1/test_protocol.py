import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from common import parse, metrics, judgment_valid, unique
from prepare import unknown_metadata, MediaVerifier, merge_splits, media_audit_records
from PIL import Image

class Tests(unittest.TestCase):
    def test_schema(self):
        self.assertTrue(parse('{"label":"SUPPORTED","confidence":0.5,"reason":"The cup is left of the plate."}')['schema_valid'])
        self.assertFalse(parse('{"label":"SUPPORTED"}')['schema_valid'])
        for raw in ['{"label":"SUPPORTED","label":"UNKNOWN"}', '{"label":"SUPPORTED","confidence":NaN}', 'SUPPORTED', '```json\n{}\n```']:
            self.assertIsNone(parse(raw)['label'])
        self.assertFalse(parse('{"label":"SUPPORTED","confidence":true,"reason":"x"}')['schema_valid'])
    def test_metrics(self):
        rows=[dict(gold='SUPPORTED',label='SUPPORTED',pair_id='a',component='binary'),
              dict(gold='CONTRADICTORY',label=None,pair_id='a',component='binary'),
              dict(gold='UNKNOWN',label='UNKNOWN',pair_id=None,component='unknown')]
        m=metrics(rows)
        self.assertEqual(m['claim_accuracy'],2/3)
        self.assertEqual(m['pair_accuracy'],0)
        self.assertEqual(m['unknown_f1'],1)
        rows[1]['label']='CONTRADICTORY'
        self.assertEqual(metrics(rows)['macro_f1'],1)
        self.assertEqual(metrics(rows)['pair_accuracy'],1)
        self.assertIsNone(metrics([])['claim_accuracy'])
    def test_ids(self):
        with self.assertRaises(ValueError): unique([dict(sample_id='a'),dict(sample_id='a')])
    def test_judge(self):
        reason='The cup is to the left of the plate.'
        self.assertTrue(judgment_valid(dict(criterion_id='R1',met=True,evidence='cup is to the left'),'R1',reason))
        self.assertFalse(judgment_valid(dict(criterion_id='R1',met=True,evidence='to the right'),'R1',reason))
        self.assertFalse(judgment_valid(dict(criterion_id='R1',met='true',evidence='cup'),'R1',reason))
        self.assertFalse(judgment_valid(dict(criterion_id='R1',met=False,evidence='cup'),'R1',reason))

    def test_unknown_without_selected_parent(self):
        row = dict(sample_id='u', pair_id='unselected', claim='The cup is left of the plate.', media={})
        candidate = dict(unknown_id='u', parent_pair_id='unselected', label='UNKNOWN', status='AUTO_ACCEPTED_UNKNOWN',
                         claim=dict(natural_text=row['claim']), media={}, split='test', global_world_id='w', source_dataset='ca_vqa')
        cert = dict(parent_pair_id='unselected', label='UNKNOWN', would_be_level_if_resolved='L1')
        result = unknown_metadata(row, candidate, cert, None, {'w':'test'})
        self.assertEqual(result['level'], 'L1')
        self.assertEqual(result['track'], 'Not annotated in released pair')
        self.assertFalse(result['parent_in_binary_release'])
        with self.assertRaisesRegex(ValueError, 'PROVENANCE_MISMATCH'):
            unknown_metadata(row, dict(candidate, media={'withheld': 'changed'}), cert, None, {'w':'test'})
        with self.assertRaisesRegex(ValueError, 'SPLIT_MISMATCH'):
            unknown_metadata(row, candidate, cert, None, {'w':'train'})

    def test_media_checkpoint_and_invalidation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            path=root/'x.png'; checkpoint=root/'cache.jsonl'
            Image.new('RGB',(2,2)).save(path)
            first=MediaVerifier(root,checkpoint,False)
            first.verify(str(path)); first.verify(str(path)); first.close()
            self.assertEqual(first.new_checks,1)
            second=MediaVerifier(root,checkpoint,True)
            with patch.object(Path,'read_bytes',side_effect=AssertionError('cached image was reread')):
                second.verify(str(path))
            second.close()
            self.assertEqual(second.reused_checks,1)
            audit=media_audit_records(second.cache)
            self.assertEqual(len(audit),1)
            self.assertEqual(audit[0]['path'],str(path))
            self.assertEqual(audit[0]['status'],'PASS')
            path.write_bytes(b'broken')
            third=MediaVerifier(root,checkpoint,True)
            try:
                with self.assertRaisesRegex(ValueError,'DECODE_FAILED'):
                    third.verify(str(path))
                with self.assertRaisesRegex(ValueError,'OUTSIDE_PERSISTENT_BUNDLE'):
                    third.verify('/etc/passwd')
            finally: third.close()

    def test_split_union_and_conflicts(self):
        first=[dict(global_world_id='a',split='train')]
        second=[dict(global_world_id='a',split='train'),dict(global_world_id='b',split='test')]
        self.assertEqual(merge_splits([first,second]), {'a':'train','b':'test'})
        with self.assertRaisesRegex(ValueError,'CONFLICTING_WORLD_SPLIT'):
            merge_splits([first,[dict(global_world_id='a',split='test')]])

if __name__=='__main__': unittest.main()
