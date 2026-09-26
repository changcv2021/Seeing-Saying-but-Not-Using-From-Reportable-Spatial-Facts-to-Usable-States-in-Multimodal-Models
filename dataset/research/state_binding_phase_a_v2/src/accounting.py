"""Parse explicit-job Slurm allocation records, not token-generation timings."""


TERMINAL = {'COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT', 'OUT_OF_MEMORY', 'NODE_FAIL', 'PREEMPTED', 'BOOT_FAIL', 'DEADLINE', 'REVOKED'}


def summarize(text, expected_ids):
    expected = {str(i) for i in expected_ids}; records = {}; rejected = []
    for line in text.splitlines():
        if not line.strip(): continue
        fields = line.split('|')
        if len(fields) < 7 or fields[0] not in expected:
            rejected.append(line); continue
        job, state, code, elapsed, cpus, tres, nodes = fields[:7]
        if job in records: raise ValueError('DUPLICATE_ACCOUNTING_JOB:' + job)
        resources = dict(part.split('=', 1) for part in tres.split(',') if '=' in part)
        # Prefer total GPU count; typed GPU entries can duplicate that total.
        gpu_count = int(resources['gres/gpu']) if 'gres/gpu' in resources else sum(int(v) for k,v in resources.items() if k.startswith('gres/gpu:'))
        seconds = int(elapsed or 0)
        records[job] = dict(job_id=job, state=state, exit_code=code, elapsed_seconds=seconds,
            allocated_gpus=gpu_count, allocated_gpu_seconds=seconds*gpu_count, nodes=nodes)
    missing = sorted(expected-records.keys())
    terminal = bool(expected) and not missing and all(r['state'].split()[0].rstrip('+') in TERMINAL for r in records.values())
    total = sum(r['allocated_gpu_seconds'] for r in records.values())
    return dict(status='PASS' if not missing and not rejected else 'FAIL', all_listed_jobs_terminal=terminal,
        allocated_gpu_seconds_to_query=total, allocated_gpu_hours_to_query=total/3600,
        jobs=list(records.values()), missing_job_ids=missing, rejected_lines=rejected,
        scope='SCHEDULER_ALLOCATION_TIME_INCLUDES_LOADING_IDLE_AND_FAILED_ALLOCATIONS; pending allocations cost zero so far, not predicted zero final cost.')
