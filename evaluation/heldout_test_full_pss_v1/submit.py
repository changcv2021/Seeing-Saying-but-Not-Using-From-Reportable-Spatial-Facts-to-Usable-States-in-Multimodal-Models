"""Each Full PSS seed depends only on its own training/final adapter."""
import datetime
import os
import shlex
import subprocess
from full_common import *


def main():
    args = parser(__doc__).parse_args()
    validate(args)
    if (ROOT / 'SUBMITTED.json').exists() or (ROOT / 'SUBMISSION_PROGRESS.json').exists():
        raise FileExistsError('NO_DUPLICATE_SUBMISSION_CHECK_EXISTING_RECEIPTS')
    previous.verify_plan()
    sinfo = subprocess.run(['sinfo', '-p', 'gpu,general', '-o', '%P %a %l %D %C %m %G'],
                           check=True, text=True, capture_output=True).stdout
    assoc = subprocess.run(['sacctmgr', '-nP', 'show', 'assoc', 'where', 'user=' + os.environ['USER'],
                            'format=Cluster,Account,Partition,QOS,DefaultQOS'],
                           check=True, text=True, capture_output=True).stdout
    if 'gpu' not in sinfo or '|YOUR_ACCOUNT|' not in assoc or 'allocated' not in assoc:
        raise ValueError('RESOURCES_NOT_CONFIRMED')
    prerequisites = {}
    for seed in SEEDS:
        complete_path = previous.TRAIN / 'runs' / key(seed) / 'TRAINING_COMPLETE.json'
        if complete_path.exists():
            complete = read(complete_path)
            if complete['status'] != 'COMPLETE_FIXED_UPDATE_BUDGET' or complete['progress']['step'] != 2237:
                raise ValueError('INVALID_TRAINING_RECEIPT')
            prerequisites[seed] = None
        else:
            job = TRAINING_JOBS[seed]
            state = subprocess.run(['squeue', '-h', '-j', job, '-o', '%T'], check=True,
                                   text=True, capture_output=True).stdout.strip()
            if state not in ('RUNNING', 'PENDING', 'COMPLETING'):
                raise ValueError('UNFINISHED_TRAINING_NOT_ACTIVE:' + job + ':' + state)
            prerequisites[seed] = 'afterok:' + job
    if not args.dry_run:
        (ROOT / 'logs').mkdir(parents=True, exist_ok=True)
        files = list(CODE.glob('*.py')) + list(CODE.glob('*.sbatch'))
        files += [EIGHT_ROOT / 'PLAN.json', EIGHT_ROOT / 'FREEZE.json']
        write(ROOT / 'EXTENSION_FREEZE.json', dict(run_id=RUN_ID, training_seeds=SEEDS,
              files={str(p): sha(p) for p in files}, final_step=2237, requests_each=5608,
              output_policy='retained_prefix_512_v1', prerequisites=prerequisites,
              source_code=str(PREVIOUS_CODE), time=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    jobs = []

    def submit(name, stage, seed=None, dependency=None, gpu=False):
        cmd = ['sbatch', '--parsable', '--job-name=' + name,
               '--partition=' + ('gpu' if gpu else 'general'), '--account=YOUR_ACCOUNT', '--qos=allocated',
               '--nodes=1', '--ntasks=1', '--cpus-per-task=' + ('4' if gpu else '2'),
               '--mem=' + ('64G' if gpu else '16G'), '--time=' + ('2-00:00:00' if gpu else '00:45:00'),
               '--output=' + str(ROOT / 'logs/%x_%A_%a.out'), '--error=' + str(ROOT / 'logs/%x_%A_%a.err')]
        if gpu:
            cmd += ['--gpus-per-node=1', '--array=0-3', '--exclude=' + previous.EXCLUDE]
        if dependency:
            cmd += ['--dependency=' + dependency, '--kill-on-invalid-dep=yes']
        cmd += [str(CODE / 'job.sbatch'), stage]
        if seed is not None:
            cmd += ['--training-seed', str(seed)]
        print(shlex.join(cmd), flush=True)
        if args.dry_run:
            job = str(9800000 + len(jobs))
        else:
            result = subprocess.run(cmd, check=True, text=True, capture_output=True)
            job = result.stdout.strip().split(';')[0]
            if not job.isdigit():
                raise ValueError('AMBIGUOUS_SBATCH_RESPONSE')
        jobs.append(dict(job_id=job, stage=stage, training_seed=seed, command=cmd))
        if not args.dry_run:
            write(ROOT / 'SUBMISSION_PROGRESS.json', jobs)
        return job

    scores = []
    for seed in SEEDS:
        prepared = submit(f'sc_full_{seed}_prepare', 'prepare', seed, prerequisites[seed])
        inference = submit(f'sc_full_{seed}_test', 'infer_adapter', seed, 'afterok:' + prepared, True)
        scores.append(submit(f'sc_full_{seed}_score', 'score', seed, 'afterany:' + inference))
    old_scores = [job['job_id'] for job in read(EIGHT_ROOT / 'SUBMITTED.json')['jobs'] if job['stage'] == 'score']
    # Only the final combined report waits for all ten scores. No inference does.
    submit('sc_pss_ten_test_summary', 'summarize', dependency='afterany:' + ':'.join(old_scores + scores))
    if not args.dry_run:
        write(ROOT / 'SUBMITTED.json', dict(status='SUBMITTED_NOT_COMPLETE', run_id=RUN_ID,
              authorization='USER: Full PSS 提交测评 如果没有完成的话，完成后立刻提交测评',
              jobs=jobs, prerequisites=prerequisites, live_sinfo=sinfo, live_assoc=assoc,
              original_eight_models_untouched=True))
        lines = ['# Full PSS held-out test 提交记录', '',
                 '两个 seeds 各测完整 test 5,608 条；固定最终 step 2237；沿用八模型的冻结推理和评分代码。', '',
                 '| Training seed | 准备任务 | 推理数组 | 评分任务 | 训练依赖 |', '|---|---|---|---|---|']
        for seed in SEEDS:
            selected = [j for j in jobs if j['training_seed'] == seed]
            dep = prerequisites[seed] or '已训练完成，无等待'
            lines.append(f'| {seed} | {selected[0]["job_id"]} | {selected[1]["job_id"]}_[0-3] | {selected[2]["job_id"]} | {dep} |')
        lines += ['', '未结束的训练成功完成后，其 CPU 核验和 GPU test 自动释放；无需再次人工提交。',
                  'GPU 仍由 Slurm 调度，自动释放不等于立即获得显卡。训练失败或最终回执缺失不使用中间 checkpoint。',
                  '两 seed 不互相等待；不依赖前八模型完成；前八模型的原始冻结文件和作业未修改。',
                  '每个 GPU 分片：1 A100、4 CPU、64 GiB、48h，gpu / YOUR_ACCOUNT / allocated；沿用坏节点避让，无数组限流。',
                  'CPU 核验/评分/汇总：2 CPU、16 GiB、45min，general / YOUR_ACCOUNT / allocated。',
                  f'十模型总汇总任务：{jobs[-1]["job_id"]}。仅汇总报告等待十项评分。', '',
                  f'结果目录：{ROOT}', '']
        (CODE / 'SUBMISSION_STATUS.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
