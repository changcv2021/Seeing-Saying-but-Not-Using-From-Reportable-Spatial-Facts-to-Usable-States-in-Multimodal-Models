"""Load a frozen LoRA, then call the unchanged historical inference runner."""
import os
import runpy
import time
from settings import *


def main():
    parser = arguments(__doc__)
    parser.add_argument('--model-index', type=int, required=True)
    parser.add_argument('--shard-index', type=int)
    args = parser.parse_args()
    validate(args)
    key = KEYS[args.model_index]
    index = args.shard_index if args.shard_index is not None else int(os.environ['SLURM_ARRAY_TASK_ID'])
    if not 0 <= index < SHARDS:
        raise ValueError('INVALID_SHARD')
    if args.dry_run:
        print(json.dumps(dict(key=key, index=index, n=N_TEST // SHARDS)))
        return
    if not os.environ.get('SLURM_JOB_ID'):
        raise ValueError('SLURM_REQUIRED')
    plan = verify_plan()
    cfg = verify_model(key, plan)
    root = ROOT / key
    stage = root / 'full'
    stage.mkdir(exist_ok=True)
    raw_path = stage / f'predictions_{index:03d}.jsonl'
    if raw_path.exists():
        prior = load(raw_path)
        if any(row.get('error') for row in prior):
            raise ValueError('FAILED_RESPONSES_PRESERVED_NO_BLIND_RESUME')
        if prior and not args.resume:
            raise FileExistsError(raw_path)
    env = read(PSS / 'environment/ENVIRONMENT.json')
    sys.path.insert(0, env['overlay'])
    import torch
    import transformers
    import peft
    from transformers import Qwen3_5ForConditionalGeneration, AutoModelForMultimodalLM
    from gpu_health import check
    health = check(stage)
    torch.backends.cuda.enable_flash_sdp(True)
    torch.backends.cuda.enable_mem_efficient_sdp(True)
    torch.backends.cuda.enable_cudnn_sdp(True)
    torch.backends.cuda.enable_math_sdp(True)
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.cuda.reset_peak_memory_stats()
    receipt = root / f'adapter_receipt_{index:03d}.json'

    def load_with_adapter(cls, model_path, **kwargs):
        if str(model_path) != cfg['model_path']:
            raise ValueError('UNEXPECTED_BASE_MODEL')
        base = Qwen3_5ForConditionalGeneration.from_pretrained(model_path, **kwargs)
        model = peft.PeftModel.from_pretrained(base, cfg['adapter_path'], is_trainable=False,
                                             autocast_adapter_dtype=False).eval()
        model.gradient_checkpointing_disable()
        model.config.use_cache = True
        adapter_params = {name: value for name, value in model.named_parameters() if 'lora_' in name}
        if not adapter_params or any(p.requires_grad for p in model.parameters()):
            raise ValueError('ADAPTER_MISSING_OR_TRAINABLE_DURING_TEST')
        if model.training or model.is_gradient_checkpointing or model.active_adapters != ['default']:
            raise ValueError('INFERENCE_MODE_NOT_ACTIVE')
        if model.peft_config['default'].base_model_name_or_path != cfg['model_path']:
            raise ValueError('WRONG_ADAPTER_BASE')
        write(receipt, dict(status='LOADED_FROZEN_ADAPTER', key=key, adapter_path=cfg['adapter_path'],
              adapter_provenance=cfg['adapter_provenance'], trainable_parameters=0,
              adapter_parameter_tensors=len(adapter_params),
              adapter_dtypes=sorted({str(p.dtype) for p in adapter_params.values()}),
              active_adapters=model.active_adapters, use_cache=True, gradient_checkpointing=False,
              attention='sdpa_fast_backends_enabled', peft=peft.__version__,
              torch=torch.__version__, transformers=transformers.__version__,
              gpu_name=torch.cuda.get_device_name(), job_id=os.environ['SLURM_JOB_ID'],
              original_runner_sha256=sha(ORIGINAL / 'infer.py')))
        return model

    original_loader = AutoModelForMultimodalLM.__dict__['from_pretrained'] if 'from_pretrained' in AutoModelForMultimodalLM.__dict__ else None
    AutoModelForMultimodalLM.from_pretrained = classmethod(load_with_adapter)
    started = time.monotonic()
    sys.argv = [str(ORIGINAL / 'infer.py'), '--run-root', str(root), '--run-id', cfg['run_id'],
                '--scope', 'full', '--num-shards', str(SHARDS), '--shard-index', str(index),
                '--seed', str(DECODE_SEED)] + (['--resume'] if args.resume else [])
    try:
        runpy.run_path(str(ORIGINAL / 'infer.py'), run_name='__main__')
        if not receipt.exists():
            raise ValueError('RUNNER_DID_NOT_LOAD_ADAPTER')
        write(stage / f'adapter_completion_{index:03d}.json', dict(status='COMPLETE', key=key,
              job_id=os.environ['SLURM_JOB_ID'], shard_index=index, adapter_receipt_sha256=sha(receipt),
              elapsed_seconds=time.monotonic() - started,
              peak_allocated_gib=torch.cuda.max_memory_allocated() / 2**30,
              peak_reserved_gib=torch.cuda.max_memory_reserved() / 2**30,
              output_sha256=sha(raw_path), wrapper_sha256=sha(__file__)))
    except BaseException as exc:
        write(stage / f'failure_{os.environ["SLURM_JOB_ID"]}_{index:03d}.json',
              dict(status='STOPPED_OUTPUTS_PRESERVED', error=repr(exc), key=key,
                   elapsed_seconds=time.monotonic() - started))
        raise
    finally:
        if original_loader is None:
            del AutoModelForMultimodalLM.from_pretrained
        else:
            AutoModelForMultimodalLM.from_pretrained = original_loader


if __name__ == '__main__':
    main()
