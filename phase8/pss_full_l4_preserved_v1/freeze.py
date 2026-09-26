"""Freeze audited per-seed plans and all experiment code before training."""
import os
import shutil
from plan import *


def main():
    if not os.environ.get('SLURM_JOB_ID'):
        raise ValueError('SLURM_REQUIRED')
    audit = OUTPUT / 'audit'
    complete = read(audit / 'AUDIT_COMPLETE.json')
    if complete['status'] != 'PASS':
        raise ValueError('AUDIT_NOT_PASS')
    for path, expected in complete['files'].items():
        if sha(path) != expected:
            raise ValueError('AUDIT_CHANGED:' + path)
    report = read(audit / 'EXPOSURE_AUDIT.json')
    original = read(OLD_OUTPUT / 'PLAN.json')
    hashes = code_hashes()
    for seed in SEEDS:
        dest = seed_output(seed)
        if dest.exists():
            raise FileExistsError('DO_NOT_OVERWRITE_SEED_PLAN')
        dest.mkdir(); (dest / 'logs').mkdir()
        name = f'{METHOD}__seed_{seed}'
        entry = report['audits'][name]; e = entry['exposure']
        if entry['l4_preservation'] != 'PASS_EXACT_PER_KEY_COUNTS_AND_WEIGHTS':
            raise ValueError('L4_NOT_PRESERVED')
        units = read(audit / f'units_{seed}.json')
        for name, source in [('samples.json', OLD_OUTPUT / 'samples.json'),
                             ('catalog.json', OLD_OUTPUT / 'catalog.json'),
                             ('units.json', audit / f'units_{seed}.json'),
                             ('processor_receipts.json', audit / 'processor_receipts.json')]:
            shutil.copy2(source, dest / name)
        catalog = read(dest / 'catalog.json')
        # Fixed engineering ingress covers L4 S0/S1/S2 and each added level.
        buckets = {}
        for unit in units:
            for key, weight in unit['records']:
                meta = catalog[key]
                if meta['pool'] == 'state':
                    tag = (unit['stream'], meta['level'], meta['stage'])
                    buckets.setdefault(tag, unit)
        if not any(tag[1:] == ('L4', 'S2') for tag in buckets):
            raise ValueError('NO_S2_ENGINEERING_CASE')
        panel = [buckets[k] for k in sorted(buckets)]
        smoke = [panel[i % len(panel)] for i in range(32)]
        write(dest / 'SMOKE_UNITS.json', smoke)
        write(dest / 'SMOKE_PANEL.json', dict(sample_ids=['USE_FROZEN_SMOKE_UNITS'], model_errors_used=False))
        plan = dict(original, optimizer_updates=e['optimizer_updates'], methods=[METHOD], seeds=[seed],
                    output=str(dest), code_hashes=hashes,
                    expected_exposure={f'{METHOD}__seed_{seed}': dict(base_examples=e['primary_units'],
                        supervised_tokens=e['target_tokens'], forward_records=e['forward_records'],
                        input_tokens=e['input_tokens'], processed_tokens=e['non_padding_tokens'])},
                    schedule='explicit preserved PSS-L4 whole batches plus evenly interleaved additional L1/L3 batches',
                    matched=['backbone','LoRA','optimizer','base_learning_rate','effective_batch_size','loss','split','serialization'],
                    measured_not_matched=['optimizer_updates','target_tokens','input_tokens','total_compute','walltime'],
                    additive_experiment=METHOD, exposure_audit_sha256=sha(audit / 'EXPOSURE_AUDIT.json'),
                    additive_artifacts={n: sha(dest / n) for n in ('units.json','SMOKE_UNITS.json','SMOKE_PANEL.json','processor_receipts.json')})
        validate_plan(plan)
        write(dest / 'PLAN.json', plan)
    for path, value in hashes.items():
        source=Path(path); target=OUTPUT/'source_snapshot'/digest(str(source))[:12]/source.name
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    write(OUTPUT / 'FREEZE.json', dict(status='FROZEN_BEFORE_TRAINING', run_id=RUN_ID,
        audit_complete_sha256=sha(audit / 'AUDIT_COMPLETE.json'), code_hashes=hashes,
        plans={str(seed): sha(seed_output(seed) / 'PLAN.json') for seed in SEEDS},
        test_policy='unchanged 5608 inputs; observed_first_label_v2; no outcome-based prompt/scoring/checkpoint selection'))
    print('FROZEN_TWO_SEEDS', flush=True)


if __name__ == '__main__':
    main()
