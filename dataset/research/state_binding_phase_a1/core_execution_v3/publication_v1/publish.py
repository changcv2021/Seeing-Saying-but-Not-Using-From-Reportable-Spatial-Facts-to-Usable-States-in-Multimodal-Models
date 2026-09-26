"""Publication integrity only: no inference, rescoring, new statistics or mechanism selection."""
import re
import zipfile
from v3common import *

HERE=Path(__file__).resolve().parent


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run:
        print('PLANNED: verify existing analysis, repair root-relative report links, create decision archive')
        return
    compute()
    handoff=root/'handoff'; acceptance=load(handoff/'06_ACCEPTANCE_AND_PROTOCOL.json')
    if acceptance['status'] not in ['COMPLETE_FOR_LOCKED_PANEL','PARTIAL_BLOCKED_INFRA']:
        raise ValueError('ACTUAL_CORE_ANALYSIS_REQUIRED')
    check_entries(load(root/'manifest/core_analysis_v1_lock.json')['code'])
    source=csvrows(handoff/'SOURCE_INDEX.csv')
    for row in source:
        if sha(row['path'])!=row['sha256']: raise ValueError('SOURCE_INDEX_MISMATCH:'+row['path'])
    index=csvrows(handoff/'raw_response_index.csv'); counted=0
    for row in index:
        if row['raw_path']:
            if sha(row['raw_path'])!=row['raw_sha256']: raise ValueError('RAW_INDEX_MISMATCH')
            counted+=1
    expected=sum(r['N_attempted'] for r in acceptance['G4']['per_model'].values())
    if counted!=expected: raise ValueError('RAW_COUNT_MISMATCH')
    report=(handoff/'01_A1_CORE_REPORT_CN.md').read_text()
    links=re.findall(r'\[[^\]]*\]\(([^)]+)\)',report)
    for link in links:
        if not link.startswith(('/', 'https:', 'http:', '#')) and not (handoff/link).is_file():
            raise ValueError('BROKEN_HANDOFF_REPORT_LINK:'+link)
    root_report=re.sub(r'(\[[^\]]*\]\()([^)/][^)]*)(\))',lambda m:m[1]+'handoff/'+m[2]+m[3],report)
    save(root/'phase_a1_report_cn.md',root_report,'text',frozen=False)
    for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)',root_report):
        if not link.startswith(('/', 'https:', 'http:', '#')) and not (root/link).is_file():
            raise ValueError('BROKEN_ROOT_REPORT_LINK:'+link)
    submissions=load(root/'resources/core_submissions.json')
    text='# Reproduction and scope\n\nAll data paths below are server-only. The enclosed report and CSV links are package-relative.\n\n'
    text+='Run ID: '+c['run_id']+'. The core contains the exact same 312 requests for all three models; no outcome-based world selection.\n\n'
    text+='## Original GPU commands (already executed; do not blindly resubmit)\n\n'
    for row in submissions['jobs']: text+='    '+row['command']+'\n\n'
    text+='These are provenance records. Old dependency job IDs can expire from the Slurm controller; confirm accounting and frozen acceptance before any separately authorized replay. Existing raw responses must never be overwritten or retried for accuracy.\n\n'
    text+='## CPU-only scoring replay\n\nUse a Slurm CPU allocation with the same module and environment. The wrapper loads python/gpu/3.12.5 and the existing virtual environment, verifies frozen analysis and inference source hashes, and never calls a model:\n\n'
    text+='    bash "'+str(CODE/'analysis_v1/job.sh')+'" analyze\n\n'
    text+='After replay, regenerate report-link/checksum/package artifacts with the publication wrapper below. If an earlier decision ZIP exists with different contents, the publisher stops rather than overwriting it.\n\n'
    text+='    bash "'+str(HERE/'job.sh')+'"\n\n'
    text+='Bootstrap uses 2,000 paired underlying-world replicates, seed 20260907. The original source-grounded private gold is separate from inference inputs. Synthetic engineering test fixtures were never saved as model predictions.\n\n'
    text+='Analysis code was locked before inspecting real core answer contents; some model jobs had already generated responses at that time. This is exposed discovery diagnostics, not prospective independent confirmation.\n\n'
    text+='STOP after A.1. No hidden states, probes, activation patching, SFT/RL, new models, confirmation or test are authorized by these replay commands.\n'
    save(handoff/'REPRODUCE_COMMANDS.md',text,'text',frozen=False)
    actual=(root/'analysis_v1/slurm_accounting.txt').read_text()
    accounting=[]
    lines=actual.splitlines(); fields=lines[0].split('|')
    for line in lines[1:]:
        cells=line.split('|')
        if len(cells)!=len(fields) or '.' in cells[0]: continue
        row=dict(zip(fields,cells))
        gpu=re.search(r'(?:^|,)gres/gpu=(\d+)',row['AllocTRES'])
        accounting.append(dict(job_id=row['JobID'],state=row['State'],exit_code=row['ExitCode'],elapsed=row['Elapsed'],
            elapsed_seconds=int(row['ElapsedRaw']),gpus=int(gpu[1]) if gpu else 0))
    gpu_hours=sum(r['elapsed_seconds']*r['gpus'] for r in accounting)/3600
    record=dict(status='PUBLICATION_INTEGRITY_PASS',analysis_status=acceptance['status'],
        indexed_raw_files=counted,main_report_links_checked=len(links),root_report_links_repaired=True,
        actual_core_jobs=accounting,actual_core_allocated_gpu_hours=gpu_hours,approved_core_max_gpu_hours=24,
        no_rescoring_or_model_calls=True,publication_code=[entry(HERE/'publish.py'),entry(HERE/'job.sh')])
    if len(accounting)!=3: raise ValueError('CORE_JOB_ACCOUNTING_INCOMPLETE')
    save(root/'reports/publication_integrity.json',record,frozen=False)
    for path in [root/'reports/publication_integrity.json',root/'phase_a1_report_cn.md',HERE/'publish.py',HERE/'job.sh']:
        source=[r for r in source if r['path']!=str(path)]+[entry(path)]
    csvsave(handoff/'SOURCE_INDEX.csv',source,['path','bytes','sha256'],frozen=False)
    files=sorted(p for p in handoff.iterdir() if p.is_file() and p.name!='SHA256SUMS.txt')
    save(handoff/'SHA256SUMS.txt',''.join(sha(p)+'  '+p.name+'\n' for p in files),'text',frozen=False)
    archive=root/'SpaceConflict_A1_Core_v3_Decision_Package_20260908.zip'
    members=sorted(p for p in handoff.iterdir() if p.is_file())
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            if z.namelist()!=[p.name for p in members] or any(z.read(p.name)!=p.read_bytes() for p in members):
                raise ValueError('EXISTING_DECISION_PACKAGE_DIFFERS_DO_NOT_OVERWRITE')
    else:
        temporary=archive.with_suffix('.zip.part')
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in members: z.write(p,p.name)
        temporary.replace(archive)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None: raise ValueError('ZIP_CRC_FAILURE')
    save(root/'reports/decision_package_manifest.json',dict(archive=entry(archive),files=len(members),analysis_status=acceptance['status'],
        report=entry(root/'phase_a1_report_cn.md'),core_actual_allocated_gpu_hours=gpu_hours,stop_after_a1=True),frozen=False)
    live=load(root/'LIVE_STATUS.json'); live.update(publication_status='PASS',decision_package=str(archive),
        report=str(root/'phase_a1_report_cn.md'),actual_core_allocated_gpu_hours=gpu_hours,auto_execute_phase_b=False)
    save(root/'LIVE_STATUS.json',live,frozen=False)
    print(json.dumps(load(root/'reports/decision_package_manifest.json')),flush=True)


if __name__=='__main__': main()
