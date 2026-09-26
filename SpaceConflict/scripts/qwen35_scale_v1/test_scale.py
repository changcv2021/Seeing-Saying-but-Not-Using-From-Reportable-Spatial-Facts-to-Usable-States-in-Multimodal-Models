import json
import unittest
from common import parse, metrics, judgment_valid
from protocol import messages_for, selected_rows

B=dict(min_pixels=100352,max_pixels=401408,video_max_pixels=200704,video_frames=16)

class Tests(unittest.TestCase):
    def test_blind_prompt(self):
        row=dict(level='L1',claim_text='The cup is left of the plate.',media=[dict(kind='image',path='/visible.jpg')],gold='PRIVATE_GOLD',proof='PRIVATE_PROOF',withheld='SECRET_PATH')
        msg=json.dumps(messages_for(row,B))
        for text in ('PRIVATE_GOLD','PRIVATE_PROOF','SECRET_PATH'):self.assertNotIn(text,msg)
        self.assertIn('/visible.jpg',msg)
    def test_l4_intervention(self):
        row=dict(level='L4',claim_text='A cup remains.',intervention_text='Remove the cup.',media=[])
        self.assertIn('Remove the cup.',json.dumps(messages_for(row,B)))
    def test_video_paths(self):
        row=dict(level='L3',claim_text='A appears first.',media=[dict(kind='video_frames',paths=['a.jpg','b.jpg'],sample_fps=2)])
        media=messages_for(row,B)[1]['content'][1]
        self.assertEqual(media['video'],['a.jpg','b.jpg']);self.assertEqual(media['sample_fps'],2)
    def test_native_video(self):
        row=dict(level='L3',claim_text='A appears first.',media=[dict(kind='video',path='a.mp4')])
        self.assertEqual(messages_for(row,B)[1]['content'][1]['nframes'],16)
    def test_shards(self):
        rows=list(range(24196));parts=[selected_rows(rows,16,i) for i in range(16)]
        self.assertEqual(sorted(x for p in parts for x in p),rows)
        with self.assertRaises(ValueError):selected_rows(rows,0,0)
    def test_strict_parse(self):
        self.assertTrue(parse('{"label":"UNKNOWN","confidence":0.5,"reason":"The view is missing."}')['schema_valid'])
        self.assertFalse(parse('```json\n{}\n```')['schema_valid'])
        self.assertFalse(parse('{"label":"UNKNOWN","confidence":true,"reason":"a"}')['schema_valid'])
    def test_pair_metrics(self):
        rows=[dict(gold='SUPPORTED',label='SUPPORTED',pair_id='p',component='binary'),dict(gold='CONTRADICTORY',label=None,pair_id='p',component='binary')]
        self.assertEqual(metrics(rows)['pair_accuracy'],0)
        self.assertEqual(metrics(rows)['claim_accuracy'],.5)
    def test_judge_quote(self):
        self.assertTrue(judgment_valid(dict(criterion_id='R1',met=True,evidence='cup'),'R1','The cup is left.'))
        self.assertFalse(judgment_valid(dict(criterion_id='R1',met=True,evidence='plate'),'R1','The cup is left.'))

if __name__=='__main__':unittest.main()
