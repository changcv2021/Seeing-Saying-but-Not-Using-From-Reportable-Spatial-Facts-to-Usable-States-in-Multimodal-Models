"""Conservative Phase A handoff from the predeclared primary contrasts only."""
from base import *


def decide(done,per,supplement,comparisons):
    common=dict(auto_execute=False,allow_whitebox=False,allow_training=False,allow_confirmation=False,allow_new_test=False)
    if not done:
        return dict(status='PHASE_A_INCOMPLETE',candidate='UNRESOLVED',reasons=['Full frozen model panels and execution-integrity checks have not all completed.'],**common)
    primary={r['contrast']:r for r in comparisons if r['model']=='qwen35_9b'}
    def positive(name):
        r=primary.get(name,{})
        return bool(r.get('ci95') and r['ci95'][0]>0 and r.get('n_clusters',0)>1)
    strict_core=[r for r in per if r['model']=='qwen35_9b' and r['condition'] in ['D_ORIG','FACT_SEPARATE','FACT_JOINT','SELECT_VALUE','STATE_VERDICT','ACTION_PARSE']]
    invalid=[r for r in strict_core if r['prediction']['status']=='INVALID']
    swaps=[r for r in per if r['model']=='qwen35_9b' and r['condition']=='FACT_JOINT' and r['prediction'].get('classifier')=='VALUES_RIGHT_BINDING_WRONG']
    interface=[r for r in supplement['interventions'] if r['model']=='qwen35_9b' and r['group_key']=='ALL' and r['comparison'] in ['VERDICT_to_ABC','VERDICT_to_semantic']]
    supported=positive('IntrusionExcess') and positive('AccuracyCost')
    candidate='ORACLE_TEXT_NON_TARGET_INTERFERENCE_CANDIDATE' if supported else 'MIXED_OR_UNRESOLVED'
    return dict(status='AWAIT_RESEARCHER_REVIEW',candidate=candidate,
        priority='ANSWER_CONTRACT_AND_DERIVED_INPUT_REVIEW' if invalid else 'DERIVED_INPUT_AND_COMPLETE_PREMISE_COVERAGE_REVIEW',
        primary_model='qwen35_9b',primary_contrasts=primary,
        observed_report_binding_swap_worlds=len({r['cluster_id'] for r in swaps}),
        core_output_contract_invalid=dict(n=len(invalid),denominator=len(strict_core),worlds=len({r['cluster_id'] for r in invalid}),
            evidence=[r['raw_path'] for r in invalid]),
        interface_controls=interface,
        reasons=['Candidate determination consults only the predeclared 9B primary comparisons, not the best of many subgroups.',
            'Any positive candidate is limited to explicit oracle text tables, not proof of an MLLM neural mechanism.',
            'Derived media/query review remains PROVISIONAL; a complete required-premise-query adapter is unavailable.',
            'State-wise source/provenance and larger-model counterexamples remain in the report regardless of direction.'],
        falsifiers=['Equal or larger reference-value hits in matched SHAM weaken directional non-target interference.',
            'Resolution under a separately validated answer interface weakens an explanation requiring state-selection failure.',
            'Insufficient premise-correct or independent-world coverage prevents separating computation from input failure.'],
        evidence=['scores/primary_comparisons.json','scores/primary_comparisons_by_scope.json','scores/supplemental_analyses.json','examples_cn.md'],**common)
