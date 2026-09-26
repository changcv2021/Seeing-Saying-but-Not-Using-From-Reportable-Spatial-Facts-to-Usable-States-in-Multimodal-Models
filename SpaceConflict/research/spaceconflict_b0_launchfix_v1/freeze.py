"""Freeze the B0 core after fixed smoke measurements, without accuracy selection."""
import subprocess
import math
from collections import Counter
from b0common import *


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('Freeze identical B0 panel based on engineering and resources only'); return
    compute(); check_entries(load(root/'manifest/smoke_lock.json')['code'])
    authorization=load(root/'resources/core_authorization.json')
    if not authorization.get('approved') or authorization.get('run_id')!=c['run_id']: raise ValueError('B0_CORE_AUTHORIZATION_MISSING')
    req=list(rows(root/'inputs/core/requests.jsonl')); smoke=list(rows(root/'inputs/smoke/requests.jsonl')); smap={r['request_id']:r for r in smoke}
    measured=[]
    for model in c['models']:
        directory=root/'raw/smoke'/model
        comp=load(directory/'completion.json'); check_entries([comp['responses_file']])
        actual=list(rows(directory/'responses.jsonl'))
        if len(actual)!=len(smoke) or {r['request_id'] for r in actual}!=set(smap) or any(r.get('infrastructure_error') for r in actual): raise ValueError('SMOKE_INCOMPLETE_OR_INFRA_ERROR')
        if any(r['gold_access_audit']['private_gold_open_attempts'] for r in actual): raise ValueError('SMOKE_GOLD_ACCESS')
        pre={r['request_id']:r for r in rows(root/'preflight'/f'{model}.jsonl')}
        costs={on:max(r['wall_seconds'] for r in actual if bool(smap[r['request_id']]['payload']['media'])==on) for on in [True,False]}
        tokenmax={on:max(r['input_tokens'] for r in actual if bool(smap[r['request_id']]['payload']['media'])==on) for on in [True,False]}
        seconds=comp['load_seconds']+60
        for r in req:
            on=bool(r['payload']['media']); seconds+=costs[on]*max(1,pre[r['request_id']]['input_tokens']/tokenmax[on])
        estimate=math.ceil(seconds*1.5)
        measured.append(dict(model=model,requests=len(req),smoke_count=len(actual),estimated_wall_seconds_with_50pct_margin=estimate,
            measured_cost_by_media={str(k):v for k,v in costs.items()},max_smoke_input_tokens=tokenmax,
            parse_statuses=dict(Counter(r['parse_without_gold']['status'] for r in actual)),
            max_peak_memory_bytes=[max(r['peak_memory_bytes'][i] for r in actual) for i in range(len(actual[0]['peak_memory_bytes']))],
            correctness_used_for_gate=False,estimated_within_6h=estimate<=21600))
    save(root/'reports/resource_measurement.json',dict(status='PASS' if all(r['estimated_within_6h'] for r in measured) else 'BUDGET_ESTIMATE_EXCEEDS_LIMIT',models=measured,
        max_gpu_hours=24,smoke_separate_budget=True,accuracy_not_gate=True))
    if not all(r['estimated_within_6h'] for r in measured): raise ValueError('NO_PANEL_OR_PROMPT_REDUCTION_BASED_ON_RESULTS_NEW_RESOURCE_DECISION_NEEDED')
    test=subprocess.run([sys.executable,'-m','unittest','-v','test_b0'],text=True,capture_output=True)
    save(root/'reports/final_precore_engineering_tests.json',dict(returncode=test.returncode,stdout=test.stdout,stderr=test.stderr))
    if test.returncode: raise ValueError('FINAL_ENGINEERING_TEST_FAILED')
    files=dependency_files(c)+[entry(Path(c['campaign'])/'config.json')]
    for record in files:
        path=Path(record['path']); save(root/'code_snapshot'/(digest(str(path))[:10]+'_'+path.name),path.read_text(),'text')
    save(root/'manifest/analysis_rules.json',load(CODE/'analysis_rules.json'))
    lock=dict(status='B0_CORE_FROZEN',run_id=c['run_id'],seed=c['seed'],frozen_at_utc=now(),
        inputs_sha256=sha(root/'inputs/core/requests.jsonl'),private_gold_sha256=sha(root/'private_gold/core.jsonl'),
        config_sha256=sha(a.config),panel_sha256=sha(root/'02_B0_PANEL_MANIFEST.jsonl'),
        matched_pairs_sha256=sha(root/'manifest/matched_pairs.jsonl'),analysis_rules_sha256=sha(CODE/'analysis_rules.json'),
        code=files,requests_per_model=len(req),requests_total=3*len(req),models=c['models'],primary_model=c['primary_model'],
        preflight=entry(root/'manifest/preflight_index.json'),resource_measurement=entry(root/'reports/resource_measurement.json'),
        assistant_render_inspection=entry(root/'review/assistant_visual_inspection.json'),
        generation=c['generation'],normal_attempts=1,automatic_model_retries=0,
        source_inventory=entry(root/'manifest/source_inventory.json'),history_baseline=entry(root/'manifest/history_before.jsonl'),
        formal_test_or_confirmation_requests=0,stop_after_b0=True)
    save(root/'manifest/core_lock.json',lock); save(root/'01_B0_PROTOCOL_LOCK.json',lock)
    save(root/'LIVE_STATUS.json',dict(status='CORE_FROZEN_READY_FOR_B0_INFERENCE',core_responses=0,requests_per_model=len(req)),frozen=False)
    print(json.dumps(dict(status=lock['status'],requests_per_model=len(req),models=measured)),flush=True)


if __name__=='__main__': main()
