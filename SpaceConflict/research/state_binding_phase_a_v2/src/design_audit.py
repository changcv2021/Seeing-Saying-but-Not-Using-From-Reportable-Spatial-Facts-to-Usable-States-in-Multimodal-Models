"""Read-only design checks of frozen requests; never inspect model outcomes."""
import collections
from base import *


def near_balanced(counts, levels):
    values = [counts.get(level, 0) for level in levels]
    return bool(sum(values)) and max(values) - min(values) <= 1


def inspect_design(requests, groups):
    by_group = {g['group_id']: g for g in groups}
    checks = []; joint = []; mappings = {}; row_positions = collections.defaultdict(collections.Counter)
    inconsistent_maps = []; table_mismatches = []
    tables = {}
    for r in requests:
        if r['condition'] == 'FACT_JOINT':
            group = by_group[r['group_id']]
            order_text = r['payload']['text'].split('REPORT ORDER: ', 1)[1].split('.', 1)[0]
            order = [v.strip() for v in order_text.split(',')]
            roles = {s['alias']: s['role'] for s in group['states']}
            joint.append(dict(group_id=r['group_id'], cluster_id=r['cluster_id'], request_id=r['request_id'],
                state_dimension=r['state_dimension'], first_alias=order[0], first_role=roles[order[0]], order=order))
        if r['condition'] == 'LABEL_INTERFACE_CONTROL' and r['variant'] == 'ABC':
            if r['group_id'] in mappings and mappings[r['group_id']] != r['label_map']:
                inconsistent_maps.append(r['request_id'])
            mappings[r['group_id']] = r['label_map']
        if r['condition'] in ['G_MULTI_VALUE', 'G_SHAM_VALUE']:
            target = r.get('alias_map', {}).get(r['target'], r['target'])
            positions = [i for i, row in enumerate(r['oracle_table']) if row['state'] == target]
            if len(positions) != 1: raise ValueError('ORACLE_TARGET_NOT_UNIQUE:' + r['request_id'])
            row_positions[(r['condition'], r['variant'])][positions[0]] += 1
            tables[(r['group_id'], r['target'], r['variant'], r['condition'])] = r
    temporal = [r for r in joint if r['state_dimension'] == 'PRE_POST']
    first_roles = dict(collections.Counter(r['first_role'] for r in temporal))
    checks.append(dict(check='joint_PRE_POST_report_order_counterbalance',
        status='PASS' if near_balanced(first_roles, ['PRE', 'POST']) else 'FAIL' if temporal else 'NOT_APPLICABLE',
        group_count=len(temporal), world_count=len({r['cluster_id'] for r in temporal}), first_role_counts=first_roles,
        limitation='Alias randomization does not counterbalance semantic PRE/POST output order. No isolated joint-order control was frozen.'))
    code_counts = {code:dict(collections.Counter(mp[code] for mp in mappings.values())) for code in 'ABC'}
    labels = ['SUPPORTED', 'CONTRADICTORY', 'UNKNOWN']
    balanced = bool(mappings) and all(near_balanced(code_counts[c], labels) for c in 'ABC')
    checks.append(dict(check='ABC_mapping_within_group_consistency', status='FAIL' if inconsistent_maps else 'PASS' if mappings else 'NOT_RUN',
        inconsistent_request_ids=inconsistent_maps, group_count=len(mappings)))
    checks.append(dict(check='ABC_mapping_across_group_counterbalance',
        status='PASS' if balanced else 'FAIL' if mappings else 'NOT_RUN', group_count=len(mappings), code_label_counts=code_counts,
        limitation='Seeded independent permutations are not guaranteed to give a finite-panel balanced design. No best mapping is selected.'))
    for (gid, target, variant, condition), multi in tables.items():
        if condition != 'G_MULTI_VALUE': continue
        sham = tables.get((gid, target, variant, 'G_SHAM_VALUE'))
        if sham is None or [(x['state'], x['value']) for x in multi['oracle_table']] != [(x['state'], x['value']) for x in sham['oracle_table']]:
            table_mismatches.append(multi['request_id'])
    checks.append(dict(check='MULTI_SHAM_same_values_and_row_order',
        status='FAIL' if table_mismatches else 'PASS' if tables else 'NOT_RUN', mismatched_request_ids=table_mismatches))
    positions = [dict(condition=key[0], variant=key[1], counts=dict(counts),
        status='PASS' if near_balanced(counts, [0, 1]) else 'FAIL') for key, counts in sorted(row_positions.items())]
    checks.append(dict(check='oracle_target_row_counterbalance', status='PASS' if positions and all(r['status']=='PASS' for r in positions) else 'FAIL' if positions else 'NOT_RUN', strata=positions))
    checks.append(dict(check='proved_physical_invariant_fact_control', status='NOT_APPLICABLE',
        limitation='Only independently proved label-invariant C/C claims are present. They are not evidence of a physically unchanged fact.'))
    checks.append(dict(check='isolated_alias_versus_order_effect', status='NOT_APPLICABLE',
        limitation='The frozen renamed_reversed variant changes aliases and table order jointly. It cannot isolate either effect.'))
    return dict(status='FAIL' if any(c['status']=='FAIL' for c in checks) else 'PASS',
        scope='SCIENTIFIC_DESIGN_LIMITATIONS_NOT_INPUT_CORRUPTION', checks=checks, joint_order_rows=joint,
        group_label_mappings=mappings, inspected_model_outputs=False, modified_frozen_inputs=False,
        interpretation='Request execution may complete provisionally; guide counterbalance acceptance is not automatically PASS.')


def audit(cfg, root):
    req = root/'inputs/discovery/requests.jsonl'
    groups = root/'manifest/discovery/state_group_manifest.jsonl'
    result = inspect_design(list(rows(req)), list(rows(groups)))
    result['input_sha256'] = sha(req)
    write(root/'reports/frozen_design_audit.json', result)
    csvwrite(root/'tables/joint_report_order.csv', result['joint_order_rows'])
    return result


def main():
    a=args(__doc__).parse_args(); cfg,root,project=setup(a)
    if a.dry_run: print(json.dumps(dict(status='PLANNED',action='read_only_frozen_design_audit'))); return
    print(json.dumps(audit(cfg,root)))


if __name__ == '__main__': main()
