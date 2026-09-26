"""Spawned CPU workers prepare and hash inputs ahead of GPU work, with bounded LRU."""
from collections import OrderedDict
from pathlib import Path
import sys
from plan import *


def source_records(plan, catalog):
    wanted = {}
    for key, m in catalog.items(): wanted.setdefault(m['source'], {})[m['line']] = key
    result = {}
    for path, mapping in wanted.items():
        if sha(path) != plan['source_hashes'][path]: raise ValueError('SOURCE_CHANGED:'+path)
        with Path(path).open() as f:
            for index, line in enumerate(f):
                if index in mapping: result[mapping[index]] = json.loads(line)
    if set(result) != set(catalog): raise ValueError('MISSING_RECORDS')
    return result


def collate_encoded(items, pad_token_id):
    import torch
    seqkeys = {'input_ids', 'attention_mask', 'mm_token_type_ids', 'token_type_ids'}
    mediakeys = {'pixel_values', 'image_grid_thw', 'pixel_values_videos', 'video_grid_thw'}
    length = max(item['batch']['input_ids'].shape[-1] for item in items)
    keys = set().union(*(item['batch'].keys() for item in items))
    if keys - seqkeys - mediakeys: raise ValueError('UNSUPPORTED_PROCESSOR_KEYS:'+str(keys-seqkeys-mediakeys))
    batch = {}
    for key in keys & seqkeys:
        values = []
        for item in items:
            n = item['batch']['input_ids'].shape[-1]
            value = item['batch'].get(key, torch.zeros_like(item['batch']['input_ids']))
            fill = pad_token_id if key == 'input_ids' else 0
            values.append(torch.nn.functional.pad(value, (length-n, 0), value=fill))
        batch[key] = torch.cat(values, dim=0)
    for key in keys & mediakeys:
        batch[key] = torch.cat([item['batch'][key] for item in items if key in item['batch']], dim=0)
    return dict(batch=batch, target_lengths=torch.tensor([i['receipt']['target_tokens'] for i in items]),
        weights=torch.tensor([i['weight'] for i in items]),
        receipts=[dict(key=i['key'], sample_id=i['sid'], index=i['index'], weight=i['weight'],
            cache_hit=i['cache_hit'], **i['receipt']) for i in items])


class StepDataset:
    def __init__(self, output, method, seed, rank, start=0, stop=None, fixed_ids=None):
        self.output = Path(output); self.plan = read(self.output/'PLAN.json')
        self.samples = read(self.output/'samples.json'); self.catalog = read(self.output/'catalog.json')
        self.method=method; self.seed=seed; self.rank=rank; self.start=start
        self.stop = stop if stop is not None else self.plan['optimizer_updates']
        self.fixed_ids=fixed_ids; self.processor=None; self.cache=OrderedDict(); self.cache_bytes=0

    def __len__(self): return self.stop-self.start

    def initialize(self):
        import torch
        torch.set_num_threads(1)
        sys.path.insert(0,str(ENGINE))
        from transformers import AutoProcessor
        from common import MODEL
        self.processor=AutoProcessor.from_pretrained(MODEL,local_files_only=True,use_fast=True)
        self.records=source_records(self.plan,self.catalog)
        self.schedule=ExampleSchedule(self.samples,self.seed,self.method!='answer_natural')

    def encoded(self,key):
        if key in self.cache:
            value=self.cache.pop(key);self.cache[key]=value;return value[0],value[1],True
        from model_io_verified import encode
        from state_interface_v2 import encode_state_v2
        row=self.records[key]
        if self.catalog[key]['pool']=='state':
            batch,receipt=encode_state_v2(self.processor,row['request'],task_prompt=row['task_prompt'],
                target=row['target'],end_turn=row['end_turn'])
        else:
            batch,receipt=encode(self.processor,row['request'],row['target'],
                task_prompt=row.get('task_prompt'),end_turn=row['end_turn'])
        if receipt['target_tokens'] != self.catalog[key]['target_tokens']: raise ValueError('TARGET_CHANGED')
        batch=dict(batch); size=sum(v.numel()*v.element_size() for v in batch.values())
        budget=self.plan['cache_bytes_per_worker']
        while self.cache and self.cache_bytes+size>budget:
            _,old=self.cache.popitem(last=False);self.cache_bytes-=old[2]
        if size<=budget:
            self.cache[key]=(batch,receipt,size);self.cache_bytes+=size
        return batch,receipt,False

    def __getitem__(self, item):
        if self.processor is None: self.initialize()
        step=self.start+item;items=[];ids=[]
        for index in rank_indices(step,self.plan['effective_batch_size'],self.rank):
            sid=self.fixed_ids[index % len(self.fixed_ids)] if self.fixed_ids else self.schedule.at(index)
            ids.append(sid)
            for key,weight in unit_records(self.samples,sid,self.method,self.seed,index):
                batch,receipt,hit=self.encoded(key)
                items.append(dict(batch=batch,receipt=receipt,weight=weight,key=key,sid=sid,index=index,cache_hit=hit))
        size=self.plan['micro_batch_size']
        microbatches=[collate_encoded(items[i:i+size],self.processor.tokenizer.pad_token_id) for i in range(0,len(items),size)]
        return dict(step=step, sample_ids=ids, microbatches=microbatches)


def loader(dataset):
    import torch
    # Dedicated generator prevents worker initialization from consuming model/dropout RNG.
    generator=torch.Generator().manual_seed(dataset.seed+1000+dataset.rank)
    return torch.utils.data.DataLoader(dataset,batch_size=None,shuffle=False,
        num_workers=dataset.plan['loader_workers'],multiprocessing_context='spawn',
        prefetch_factor=dataset.plan['prefetch_factor'],persistent_workers=True,
        pin_memory=True,generator=generator)
