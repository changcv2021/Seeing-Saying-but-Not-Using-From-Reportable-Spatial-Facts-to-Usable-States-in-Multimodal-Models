"""Join measured representations to private labels after inference; keep sparse cases."""
from collections import defaultdict,Counter
from common_auto_v2 import *
from m1_compile_v1 import BATCH


def main():
    a=arguments(__doc__).parse_args();c,root=setup(a);out=root/'whitebox'/BATCH
    dest=out/'analysis'/('snapshot_'+os.environ['SLURM_JOB_ID']);lock=load(out/'manifest/M1_LOCK.json')
    labels=list(rows(out/'private_gold/measurement_labels.jsonl'));records=[]
    for label in labels:
        path=out/'measurements/records'/(label['request_id']+'.json')
        item=dict(label,status='NOT_RUN')
        if path.exists():
            raw=load(path);item.update(status=raw['status'],measurement_ref=entry(path),hidden=raw.get('hidden'),positions=raw.get('positions'),
                hook_noop_pass=raw.get('hook_noop_pass'),error=raw.get('error'))
        records.append(item)
    eligibility=[]
    for variable in ('true_value','candidate_value','target_identity','information_role','target_bound_value','protected_value'):
        groups=defaultdict(lambda:defaultdict(set))
        for r in records:
            if r['status']!='MEASUREMENT_RECORDED' or r[variable] is None:continue
            split='validation' if r['internal_group_fold']==0 else 'train'
            groups[json.dumps(r[variable])][split].add(r['world_cluster_id'])
        enough=len(groups)>=2 and all(len(g['train'])>=lock['probe_min_train_worlds_per_class'] and len(g['validation'])>=lock['probe_min_validation_worlds_per_class'] for g in groups.values())
        eligibility.append(dict(variable=variable,status='PROBE_ELIGIBLE_NOT_YET_FIT' if enough else 'PROBE_UNDERPOWERED',
            class_world_counts={k:{s:len(v[s]) for s in ('train','validation')} for k,v in groups.items()},
            train_min=lock['probe_min_train_worlds_per_class'],validation_min=lock['probe_min_validation_worlds_per_class']))
    csvsave(dest/'measurement_label_matrix.csv',records);save(dest/'probe_eligibility.json',eligibility)
    report=dict(status='INDEX_COMPLETE',planned=len(records),states=dict(Counter(r['status'] for r in records)),
        worlds=len({r['world_cluster_id'] for r in records}),readability_claim='NONE_WITHOUT_GROUP_HELDOUT_PROBES_AND_BASELINES',
        M2='NOT_RUN_NO_QUALIFIED_INTERVENTION_MANIFEST_YET',C2='NO_MECHANISM_LOCK',
        scientific_review_grade='AUTO_ONLY_PROVISIONAL',job_id=os.environ['SLURM_JOB_ID'],matrix=entry(dest/'measurement_label_matrix.csv'))
    save(dest/'COLLECTION_REPORT.json',report);print(json.dumps(report),flush=True)


if __name__=='__main__':main()
