"""CPU G0 inventory, history protection, trusted construction and deterministic tests."""
import subprocess
from collections import Counter
from v3common import *


def command(args):
    r=subprocess.run(args,text=True,capture_output=True,timeout=30)
    return dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('PLANNED: CPU inventory/history protection and new input construction; no model generation'); return
    compute(); root.mkdir(parents=True,exist_ok=True)
    before=root/'manifest/history_before.jsonl'
    if not before.exists():
        protected=[]
        # Do not re-include our new namespace under the historical parent code directory.
        for k in ['phase_a_root','old_a1_root','format_v2_root']:
            for p in sorted(Path(c[k]).rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts: protected.append(entry(p))
        for d in [Path(c['old_a1_code'])/'src',Path(c['old_a1_code'])/'scripts',Path(c['old_a1_code'])/'configs',Path(c['old_a1_code'])/'format_repair_v2']:
            for p in sorted(d.rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts: protected.append(entry(p))
        save(before,protected,'jsonl')
    baseline=list(rows(Path(c['old_a1_root'])/'manifest/phase_a_files_before.jsonl'))
    count=check_entries(baseline)
    campaign=load(Path(c['campaign'])/'config.json'); model_checks=[]
    for m in campaign['models']:
        mm=load(m['manifest_path']); assert (mm['model_id'],mm['revision'])==(m['model'],m['revision'])
        mp=Path(m['model_path']); idx=load(mp/'model.safetensors.index.json')
        shards=sorted(set(idx['weight_map'].values()))
        assert shards and all((mp/s).is_file() and (mp/s).stat().st_size>0 for s in shards)
        model_checks.append(dict(key=m['key'],model_id=m['model'],revision=m['revision'],manifest=entry(m['manifest_path']),
            index=entry(mp/'model.safetensors.index.json'),config=entry(mp/'config.json'),
            shard_sizes=[dict(path=str(mp/s),bytes=(mp/s).stat().st_size) for s in shards],
            scope='LOCAL_MANIFEST_REVISION_CONFIG_HASH_AND_SHARD_EXISTENCE_SIZE_NOT_FULL_WEIGHT_REHASH'))
    currents=[]
    for sibling in sorted(root.parent.iterdir()):
        if not sibling.is_dir() or sibling==root: continue
        core=list((sibling/'raw/core').glob('*/*.json')) if (sibling/'raw/core').exists() else []
        currents.append(dict(root=str(sibling),live=load(sibling/'LIVE_STATUS.json') if (sibling/'LIVE_STATUS.json').exists() else None,
                             core_files=[entry(p) for p in core if p.name not in ['completion.json','progress.json']]))
    if any(x['core_files'] for x in currents): raise ValueError('EXISTING_CORE_FOUND_REVIEW_PROTOCOL_BEFORE_NEW_RUN')
    save(root/'current_state_inventory.json',dict(checked_at=now(),hostname=socket.gethostname(),run_id=c['run_id'],
        old_runs=currents,models=model_checks,original_phase_a_baseline_checked=count,
        slurm=command(['squeue','-u','anonymous','-o','%i|%j|%T|%R']),
        partitions=command(['sinfo','-p','gpu,debug,general','-o','%P|%a|%l|%c|%m|%G']),
        account=command(['sacctmgr','-nP','show','assoc','user=anonymous','format=Cluster,Account,User,QOS,DefaultQOS']),
        quota=command(['lfs','quota','-u','anonymous','external/project']),
        code_revision=command(['git','-C',c['project'],'rev-parse','HEAD']),
        full_code_snapshot_hash=digest(code_entries(c)),new_core_responses=0),frozen=False)
    save(root/'protocol_amendments.json',dict(version='phase_a1_core_v3',guide=entry(Path(c['package'])/'SpaceConflict_PhaseA1_Core_Execution_v3_CN.md'),
        amendments=['ALL_MATCHED_VALUE_CONDITIONS_NULLABLE','SEMANTIC_ACCURACY_NOT_GATE','SELECT_MEDIA_SEPARATE_FROM_ORACLE_MULTI',
                    'NO_AUTOMATIC_FAILURE_COUNT_THRESHOLD','SYMBOLIC_D2_NOT_SOURCE_TRUTH','NULL_INVALID_INFRA_NOT_RUN_SEPARATE',
                    'V2_SCALAR_ALIAS_UNCHANGED_ACTION_NULLABLE_EXTENSION','POST_NO_MEDIA_TWO_COMPLETIONS_REQUIRE_REVIEW',
                    'BINARY_RELATION_DEFERRED','SEMANTIC_BRIDGE_ONE_FIXED_PASS','NEW_GPU_BUDGET_REQUIRED'],
        source_history_modified=False))
    # Invoke the actual provided generator in memory via the versioned builder; do not modify its source.
    import build_v3
    build_v3.main()
    from test_v3 import validate_design
    save(root/'reports/design_checks.json',validate_design(root))
    tests=[]
    for args in [[sys.executable,'-m','unittest','-v','test_v3'],
                 [sys.executable,'-m','unittest','discover','-s',str(Path(c['package'])/'tests'),'-v']]:
        r=subprocess.run(args,text=True,capture_output=True)
        tests.append(dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr))
        if r.returncode: save(root/'reports/failed_cpu_tests.json',tests,frozen=False); raise ValueError('CPU_TESTS_FAILED')
    save(root/'reports/cpu_tests.json',dict(status='PASS',runs=tests))
    checked=check_entries(list(rows(before)))
    save(root/'reports/history_protection.json',dict(status='PASS',files_checked=checked,changed_files=[],baseline_sha256=sha(before)))
    save(root/'LIVE_STATUS.json',dict(status='CPU_BUILD_TESTED_AWAITING_PROCESSOR_REVIEW',generated_core=0,verified_worlds=0),frozen=False)
    print(json.dumps(dict(status='CPU_BUILD_TESTED',history_files=checked,new_model_predictions=0)))


if __name__=='__main__': main()
