"""Explicit frozen additive units; unchanged v4 processor, batching and loss."""
import importlib.util
from plan import *

spec = importlib.util.spec_from_file_location('preserved_legacy_data', V4 / 'data.py')
legacy_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy_data)
loader = legacy_data.loader


class StepDataset(legacy_data.StepDataset):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.units = read(self.output / ('SMOKE_UNITS.json' if self.fixed_ids else 'units.json'))
        self.expected = read(self.output / 'processor_receipts.json')

    def encoded(self, key):
        batch, receipt, hit = super().encoded(key)
        from audit import signature
        if signature(receipt) != self.expected[key]:
            raise ValueError('ACTUAL_PROCESSOR_RECEIPT_CHANGED:' + key)
        return batch, receipt, hit

    def __getitem__(self, item):
        if self.processor is None:
            self.initialize()
        step = self.start + item
        items, ids = [], []
        for index in rank_indices(step, self.plan['effective_batch_size'], self.rank):
            unit = self.units[index]
            sid = unit['sample_id']; ids.append(sid)
            for key, weight in unit['records']:
                batch, receipt, hit = self.encoded(key)
                items.append(dict(batch=batch, receipt=receipt, weight=weight, key=key,
                                  sid=sid, index=index, cache_hit=hit))
        size = self.plan['micro_batch_size']
        microbatches = [legacy_data.collate_encoded(items[i:i+size], self.processor.tokenizer.pad_token_id)
                        for i in range(0, len(items), size)]
        for micro in microbatches:
            for receipt in micro['receipts']:
                unit = self.units[receipt['index']]
                receipt.update(source_index=unit['source_index'], stream=unit['stream'])
        return dict(step=step, sample_ids=ids, microbatches=microbatches)
