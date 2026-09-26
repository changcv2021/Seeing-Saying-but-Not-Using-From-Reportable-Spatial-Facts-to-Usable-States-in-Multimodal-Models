"""Researcher-waived human gates; automatic evidence checks remain independent.

This module decides policy, not data truth. Callers supply their actual automatic
qualification report. A PASS here never certifies human review or creates gold.
"""
from common import CODE, load

VERSION = 'sws_auto_review_waiver_v2_20260910'
CONFIG = CODE / 'config_auto_v2.json'
WAIVED = 'HUMAN_REVIEW_WAIVED_BY_RESEARCHER'
GRADE = 'AUTO_ONLY_PROVISIONAL'
HUMAN_FLAGS = (
    'human_primary_required', 'human_secondary_required',
    'human_key_case_required', 'human_confirmation_case_required',
    'human_review_blocks_submission', 'human_review_blocks_statistics',
    'human_review_blocks_packaging',
)


def validate_policy(config, waiver):
    if config.get('effective_policy_version') != VERSION:
        raise ValueError('WRONG_POLICY_VERSION')
    if waiver.get('policy_version') != VERSION or waiver.get('run_id') != config['run_id']:
        raise ValueError('WAIVER_SCOPE_MISMATCH')
    if waiver.get('approved') is not True or waiver.get('source') != 'USER_DIRECT_MESSAGE':
        raise ValueError('MISSING_RESEARCHER_WAIVER')
    review = config['review']
    for key in HUMAN_FLAGS:
        if review.get(key) is not False or waiver.get(key) is not False:
            raise ValueError('HUMAN_GATE_REINTRODUCED:' + key)
    if config['sampling']['all_real_main_inputs_require_human_review'] is not False:
        raise ValueError('SAMPLING_HUMAN_GATE_REINTRODUCED')
    if config['sampling']['secondary_review_fraction'] != 0:
        raise ValueError('SECONDARY_QUOTA_REINTRODUCED')
    if review['automatic_checks_still_required'] is not True:
        raise ValueError('AUTOMATIC_CHECKS_REMOVED')
    for record in (review, waiver):
        if record.get('automatic_pass_is_human_verified') is not False:
            raise ValueError('FALSE_HUMAN_CERTIFICATION')
        if (record.get('default_review_status'), record.get('scientific_review_grade')) != (WAIVED, GRADE):
            raise ValueError('REVIEW_PROVENANCE_CHANGED')
    return dict(policy_version=VERSION, review_status=WAIVED,
                scientific_review_grade=GRADE, human_review_required=False,
                human_review_blocks_execution=False, human_verified=False)


def effective_policy(config=None):
    config = config if config is not None else load(CONFIG)
    return validate_policy(config, load(config['review_waiver_record']))


def execution_decision(config, waiver, automatic_checks, *, human_record=None,
                       technical_dependencies=()):
    """Absent, pending or empty human signatures have no bearing on admission.

    automatic_checks maps named existing machine checks to PASS / NOT_APPLICABLE
    / failure or missing statuses. It must come from the batch validator, not from
    a human-approval flag. Concrete defect findings stay in automatic_checks.
    Neither this helper nor a successful policy test validates a real world.
    """
    result = validate_policy(config, waiver)
    blockers = []
    if not isinstance(automatic_checks, dict) or not automatic_checks:
        blockers.append('AUTOMATIC_QUALIFICATION_NOT_AVAILABLE')
    else:
        for name, status in automatic_checks.items():
            if status not in ('PASS', 'NOT_APPLICABLE'):
                blockers.append('AUTOMATIC_CHECK:' + name + ':' + str(status))
    blockers.extend('TECHNICAL_DEPENDENCY:' + item for item in technical_dependencies)
    return dict(result, can_proceed=not blockers, blockers=blockers,
                human_record_used_as_gate=False)
