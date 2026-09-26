"""Submit independent GPU arrays, then each model's own exact scoring job."""
import os
import shlex
import subprocess
from settings import *


def main():
    args = arguments(__doc__).parse_args()
    validate(args)
    if (ROOT / 'SUBMITTED.json').exists():
        raise FileExistsError('ALREADY_SUBMITTED_CHECK_LIVE_JOBS')
    # Read-only live checks, never guess scheduling resources.
    sinfo = subprocess.run(['sinfo', '-p', 'gpu,general', '-o', '%P %a %l %D %C %m %G'],
                           text=True, capture_output=True, check=True).stdout
    assoc = subprocess.run(['sacctmgr', '-nP', 'show', 'assoc', 'where', 'user=' + os.environ['USER'],
                            'format=Cluster,Account,Partition,QOS,DefaultQOS'],
                           text=True, capture_output=True, check=True).stdout
    if 'gpu' not in sinfo or '|YOUR_ACCOUNT|' not in assoc or 'allocated' not in assoc:
        raise ValueError('LIVE_RESOURCES_NOT_CONFIRMED')
    logs = ROOT / 'logs'
    if not args.dry_run:
        logs.mkdir(parents=True, exist_ok=True)
    submitted = []

    def submit(name, stage, extra=(), dependency=None, model_index=None, gpu=False):
        command = ['sbatch', '--parsable', '--job-name=' + name,
                   '--partition=' + ('gpu' if gpu else 'general'), '--account=YOUR_ACCOUNT', '--qos=allocated',
                   '--nodes=1', '--ntasks=1', '--cpus-per-task=' + ('4' if gpu else '2'),
                   '--mem=' + ('64G' if gpu else '16G'), '--time=' + ('2-00:00:00' if gpu else '00:45:00'),
                   '--output=' + str(logs / '%x_%A_%a.out'), '--error=' + str(logs / '%x_%A_%a.err')]
        if gpu:
            command += ['--gpus-per-node=1', '--exclude=' + EXCLUDE, '--array=0-3']
        if dependency:
            command += ['--dependency=' + dependency, '--kill-on-invalid-dep=yes']
        command += list(extra) + [str(CODE / 'job.sbatch'), stage]
        if model_index is not None:
            command += ['--model-index', str(model_index)]
        print(shlex.join(command), flush=True)
        if args.dry_run:
            job = str(9900000 + len(submitted))
        else:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            job = result.stdout.strip().split(';')[0]
            if not job.isdigit():
                raise ValueError('BAD_SBATCH_RESPONSE:' + result.stdout)
        submitted.append(dict(job_id=job, name=name, stage=stage, model_index=model_index, command=command))
        if not args.dry_run:
            write(ROOT / 'SUBMISSION_PROGRESS.json', submitted)
        return job

    prepare = submit('sc_pss_test_prepare', 'prepare')
    scores = []
    for i, key in enumerate(KEYS):
        gpu = submit(f'sc_psst_{i}_infer', 'infer_adapter', dependency='afterok:' + prepare, model_index=i, gpu=True)
        scores.append(submit(f'sc_psst_{i}_score', 'score', dependency='afterany:' + gpu, model_index=i))
    submit('sc_pss_test_summary', 'summarize', dependency='afterany:' + ':'.join(scores))
    if not args.dry_run:
        write(ROOT / 'SUBMITTED.json', dict(status='SUBMITTED_NOT_COMPLETE', jobs=submitted,
              live_sinfo=sinfo, live_assoc=assoc, keys=KEYS, request_count=8 * N_TEST,
              authorization='USER: 8个模型先开始test把', run_id=RUN_ID))
        lines = ['# Phase8 held-out test 提交记录', '', '已提交不等于完成。8 adapters × 4 单卡分片；模型间无依赖。', '',
                 '| 模型 | 推理数组 | 评分任务 |', '|---|---|---|']
        for i, key in enumerate(KEYS):
            jobs = [j for j in submitted if j['model_index'] == i]
            lines.append(f'| {key} | {jobs[0]["job_id"]}_[0-3] | {jobs[1]["job_id"]} |')
        lines += ['', f'前置 CPU 核验：{prepare}；汇总：{submitted[-1]["job_id"]}。',
                  '评分任务仅依赖本模型的四个推理分片；afterany 用于保留失败/不完整诊断，不把失败当成功。',
                  'GPU 每分片 1 A100 / 4 CPU / 64 GiB / 48h，gpu/YOUR_ACCOUNT/allocated。',
                  '48h 是集群一次分配上限，不是 6h 限制或总体预算。无人为数组并发上限。',
                  'CPU 核验/评分/汇总：general/YOUR_ACCOUNT/allocated，2 CPU / 16 GiB / 45min。',
                  '所有原始 release、gold、旧预测和最终训练检查点保持只读。',
                  '', f'结果目录：{ROOT}', '']
        (CODE / 'SUBMISSION_STATUS.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
