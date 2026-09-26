"""Test and publish a separate active-policy overlay; never rewrite old outputs."""
import io
import os
import unittest
from common_auto_v2 import *
from review_policy_v2 import VERSION, effective_policy
from test_review_policy_v2 import ReviewPolicyTests


def main():
    args = arguments(__doc__).parse_args()
    c, root = setup(args)
    policy = effective_policy(c)
    if args.dry_run:
        print(json.dumps(policy)); return
    target = root / 'scheduler' / VERSION
    acceptance_path = target / 'POLICY_ACCEPTANCE.json'
    if acceptance_path.exists():
        old = load(acceptance_path)
        for item in old['policy_files'] + old['protected_files']:
            if sha(item['path']) != item['sha256']:
                raise ValueError('ACTIVATION_INPUT_CHANGED:' + item['path'])
        print(json.dumps({'status': 'REUSED_ACCEPTED_POLICY', 'path': str(acceptance_path)})); return
    protected = [entry(CODE / name) for name in (
        'config.json', 'common.py', 'contracts.py', 'inventory.py', 'inventory_v2.py',
        'e0_snapshot.py', 'e0_snapshot_v2.py', 'gpu_worker_v1.py', 'collect_startup.py',
        'job_cpu_v2.sh', 'world_identity_v2.py', 'snapshot_store_v2.py',
        'verify_world_repair_v2.py')]
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ReviewPolicyTests))
    if not result.wasSuccessful():
        raise RuntimeError(output.getvalue())
    source = root / 'repairs/world_identity_v2/inventory/manifest/world_candidate_inventory.jsonl'
    expected = next(x for x in load(root / 'repairs/world_identity_v2/REPAIR_ACCEPTANCE.json')['output_files']
                    if x['path'] == str(source))
    if sha(source) != expected['sha256']:
        raise ValueError('FROZEN_CANDIDATE_INVENTORY_CHANGED')
    candidates = []
    for record in rows(source):
        candidates.append(dict(
            world_cluster_id=record['world_cluster_id'], policy_version=VERSION,
            review_status=policy['review_status'], human_review_required=False,
            human_review_blocks_execution=False,
            historical_review_status=record.get('review_status'),
            scientific_review_grade=policy['scientific_review_grade'],
            human_verified=False,
            automatic_input_qualification='NOT_YET_COMPILED_AND_VALIDATED',
            qualified_for_real_inference=False))
    save(target / 'candidate_review_policy_overlay.jsonl', candidates, 'jsonl')
    save(target / 'policy_regression.log', output.getvalue(), 'text')
    for item in protected:
        if sha(item['path']) != item['sha256']:
            raise ValueError('PROTECTED_FILE_CHANGED:' + item['path'])
    policy_files = [entry(CODE / name) for name in (
        'config_auto_v2.json', 'review_policy_v2.py', 'common_auto_v2.py',
        'test_review_policy_v2.py', 'activate_review_policy_v2.py', 'job_cpu_auto_v2.sh')]
    policy_files.append(entry(c['review_waiver_record']))
    save(acceptance_path, dict(
        status='PASS_HUMAN_EXECUTION_GATES_REMOVED_NOT_STUDY_COMPLETION',
        job_id=os.environ['SLURM_JOB_ID'], created_at=now(), **policy,
        policy_files=policy_files, protected_files=protected, tests_run=result.testsRun,
        tests_scope='POLICY_FIXTURES_NOT_REAL_INPUT_VERIFICATION',
        historical_mismatches=[], candidate_worlds=len(candidates),
        candidate_inventory=expected, real_worlds_newly_qualified=0,
        new_GPU_calls=0, human_review_blockers=[],
        remaining_work='NEW_E1_E8_INPUT_COMPILATION_AUTOMATIC_VALIDATION_AND_REQUEST_HASH_LOCKS',
        overlay=entry(target / 'candidate_review_policy_overlay.jsonl')))
    save(root / 'scheduler/ACTIVE_EXECUTION_POLICY.json', dict(
        **policy, config=str(args.config), config_sha256=sha(args.config),
        waiver_record=c['review_waiver_record'], waiver_sha256=sha(c['review_waiver_record']),
        common_entry=str(CODE / 'common_auto_v2.py'),
        acceptance=entry(acceptance_path), historical_outputs_read_only=True,
        manual_review_pending_does_not_block=True,
        resource_authorization=c['resources']['authorization_record'],
        obsolete_new_work_entries=['common.py default config', 'collect_startup.py',
                                   'package tools/submit_wave.py template']))
    print(json.dumps(dict(status='PASS', tests=result.testsRun, candidate_worlds=len(candidates),
                          human_review_blockers=0, new_GPU_calls=0), ensure_ascii=False))


if __name__ == '__main__':
    main()
