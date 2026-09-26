"""Per-seed preparation, unchanged inference, and unchanged exact scoring."""
import os
import runpy
import shutil
from full_common import *


def main():
    p = parser(__doc__)
    p.add_argument('stage', choices=('prepare', 'infer_adapter', 'score'))
    p.add_argument('--training-seed', type=int, required=True, choices=SEEDS)
    args = p.parse_args()
    validate(args)
    if not args.dry_run:
        if not os.environ.get('SLURM_JOB_ID'):
            raise ValueError('SLURM_REQUIRED')
        verify_extension()
        previous.verify_plan()  # Check the original frozen code before remapping.
    config = configure_seed(args.training_seed)
    target = PREVIOUS_CODE / f'{args.stage}.py'
    if args.stage == 'prepare' and not args.dry_run:
        # A successful allocation boundary is not necessarily completed training.
        # Require its explicit fixed-final-step receipt, never use a partial adapter.
        complete_path = previous.TRAIN / 'runs' / key(args.training_seed) / 'TRAINING_COMPLETE.json'
        if not complete_path.exists():
            raise ValueError('TRAINING_NOT_FINISHED_NO_PARTIAL_CHECKPOINT_TEST')
        complete = read(complete_path)
        if complete['status'] != 'COMPLETE_FIXED_UPDATE_BUDGET' or complete['progress']['step'] != 2237:
            raise ValueError('WRONG_FINAL_TRAINING_STATE')
        config.ROOT.mkdir(parents=True, exist_ok=True)
        write(config.ROOT / 'BRIDGE_PROVENANCE.json', dict(
            extension_freeze_sha256=sha(ROOT / 'EXTENSION_FREEZE.json'),
            reused_code=str(PREVIOUS_CODE), training_job=TRAINING_JOBS[args.training_seed],
            training_seed=args.training_seed, training_complete_sha256=sha(complete_path),
            changed=('run_id', 'output_root', 'method=pss_full', 'training_seed'),
            unchanged=('requests', 'prompt', 'processor', 'base_revision', 'decode', 'output_policy', 'scorer')))
        snapshot = config.ROOT / 'source_snapshot/full_pss_extension'
        snapshot.mkdir(parents=True, exist_ok=True)
        for path in list(CODE.glob('*.py')) + list(CODE.glob('*.sbatch')):
            shutil.copy2(path, snapshot / path.name)
    sys.argv = [str(target), '--run-id', config.RUN_ID, '--seed', str(config.DECODE_SEED)]
    if args.stage in ('infer_adapter', 'score'):
        sys.argv += ['--model-index', '0']
    if args.dry_run:
        sys.argv += ['--dry-run']
        if args.stage == 'infer_adapter':
            sys.argv += ['--shard-index', '0']
    if args.resume:
        sys.argv += ['--resume']
    runpy.run_path(str(target), run_name='__main__')


if __name__ == '__main__':
    main()
