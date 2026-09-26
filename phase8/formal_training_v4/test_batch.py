import unittest
import torch
from data import collate_encoded
from engine import LossModule


class TestBatch(unittest.TestCase):
    def test_padding_and_media_order(self):
        items=[]
        for n,t in ((7,2),(5,3)):
            items.append(dict(batch={'input_ids':torch.arange(n)[None], 'attention_mask':torch.ones((1,n),dtype=torch.long),
                'mm_token_type_ids':torch.zeros((1,n),dtype=torch.long),'pixel_values':torch.full((1,3),float(n)),
                'image_grid_thw':torch.tensor([[1,1,1]])},receipt={'target_tokens':t},
                weight=1.,key=str(n),sid=str(n),index=n,cache_hit=False))
        result=collate_encoded(items,99)
        self.assertEqual(result['batch']['input_ids'].tolist(),[[0,1,2,3,4,5,6],[99,99,0,1,2,3,4]])
        self.assertEqual(result['batch']['attention_mask'].tolist(),[[1]*7,[0,0,1,1,1,1,1]])
        self.assertEqual(result['batch']['pixel_values'][:,0].tolist(),[7.,5.])
        self.assertEqual(result['target_lengths'].tolist(),[2,3])

    def test_target_mask_excludes_prompt(self):
        class Fake(torch.nn.Module):
            def forward(self,input_ids,logits_to_keep,**kwargs):
                from types import SimpleNamespace
                logits=torch.arange(8,dtype=torch.float32).repeat(input_ids.shape[0],len(logits_to_keep),1)
                return SimpleNamespace(logits=logits)
        model=LossModule(Fake());ids=torch.tensor([[7,7,7,1,2],[0,0,3,4,5]])
        result=model({'input_ids':ids},torch.tensor([2,3]))
        expected=torch.stack([torch.nn.functional.cross_entropy(torch.arange(8,dtype=torch.float32).repeat(len(x),1),torch.tensor(x)) for x in ([1,2],[3,4,5])])
        torch.testing.assert_close(result,expected)


if __name__=='__main__':unittest.main()
