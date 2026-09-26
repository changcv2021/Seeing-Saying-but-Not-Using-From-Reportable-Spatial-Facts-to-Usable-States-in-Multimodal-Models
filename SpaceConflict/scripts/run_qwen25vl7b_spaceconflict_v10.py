#!/usr/bin/env python3
"""Run deterministic Qwen2.5-VL-7B inference on blind SpaceConflict L1-L3 requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
import transformers
from qwen_vl_utils import process_vision_info
from transformers import AutoModelForImageTextToText, AutoProcessor

from spaceconflict.mllm_l4 import SYSTEM_PROMPT, parse_model_response


MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"
MODEL_REVISION = "cc594898137f460bfe9f0759e9844b3ce807cfb5"
DEFAULT_MODEL_PATH = Path("external/scratch/industbench_qwen25vl7b/model/Qwen2.5-VL-7B-Instruct")
DEFAULT_ENVIRONMENT = Path("external/projects/iclr benchmark/industry/reports/qwen25vl7b_full_eval_20260902/environment.json")
DEFAULT_MIN_PIXELS = 128 * 28 * 28
DEFAULT_MAX_PIXELS = 512 * 28 * 28
DEFAULT_VIDEO_MAX_PIXELS = 256 * 28 * 28


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def user_prompt(sample: dict[str, Any]) -> str:
    return (
        f"Spatial claim:\n{sample['claim_text']}\n\n"
        f"Accessible evidence: {len(sample.get('media') or [])} media item(s) supplied above.\n\n"
        "Return exactly one JSON object with this schema:\n"
        '{"label":"SUPPORTED|CONTRADICTORY|UNKNOWN","confidence":0.0,"reason":"brief explanation"}'
    )


def messages_for(
    sample: dict[str, Any], min_pixels: int, max_pixels: int,
    video_max_pixels: int, video_frames: int,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for index, media in enumerate(sample.get("media") or [], 1):
        role = str(media.get("role") or f"media_{index}")
        kind = str(media.get("kind") or "image")
        content.append({"type": "text", "text": f"Evidence {kind} {index} ({role}):"})
        if kind == "video":
            content.append({
                "type": "video", "video": media["path"], "nframes": video_frames,
                "min_pixels": min_pixels, "max_pixels": video_max_pixels,
            })
        elif kind == "video_frames":
            content.append({
                "type": "video", "video": media["paths"], "sample_fps": media.get("sample_fps", 2.0),
                "min_pixels": min_pixels, "max_pixels": video_max_pixels,
            })
        elif kind == "image":
            content.append({
                "type": "image", "image": media["path"],
                "min_pixels": min_pixels, "max_pixels": max_pixels,
            })
        else:
            raise ValueError(f"UNSUPPORTED_MEDIA_KIND:{kind}")
    content.append({"type": "text", "text": user_prompt(sample)})
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}]


def generate(model, processor, sample, args):
    messages = messages_for(
        sample, args.min_pixels, args.max_pixels, args.video_max_pixels, args.video_frames,
    )
    rendered = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    images, videos, video_kwargs = process_vision_info(messages, return_video_kwargs=True)
    inputs = processor(
        text=[rendered], images=images, videos=videos, padding=True, return_tensors="pt", **video_kwargs,
    )
    inputs = {key: value.to("cuda:0") if hasattr(value, "to") else value for key, value in inputs.items()}
    with torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False, use_cache=True)
    prompt_tokens = int(inputs["input_ids"].shape[-1])
    generated = output[:, prompt_tokens:]
    response = processor.batch_decode(
        generated, skip_special_tokens=True, clean_up_tokenization_spaces=False,
    )[0].strip()
    return response, prompt_tokens, int(generated.shape[-1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requested-samples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--environment", type=Path, default=DEFAULT_ENVIRONMENT)
    parser.add_argument("--min-pixels", type=int, default=DEFAULT_MIN_PIXELS)
    parser.add_argument("--max-pixels", type=int, default=DEFAULT_MAX_PIXELS)
    parser.add_argument("--video-max-pixels", type=int, default=DEFAULT_VIDEO_MAX_PIXELS)
    parser.add_argument("--video-frames", type=int, default=16)
    parser.add_argument("--max-new-tokens", type=int, default=160)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260903)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    args = parser.parse_args()

    if args.num_shards < 1:
        raise ValueError("NUM_SHARDS_MUST_BE_POSITIVE")
    if not 0 <= args.shard_index < args.num_shards:
        raise ValueError("SHARD_INDEX_OUT_OF_RANGE")
    all_samples = read_jsonl(args.requested_samples)
    samples = [
        sample for index, sample in enumerate(all_samples)
        if index % args.num_shards == args.shard_index
    ]
    if args.limit is not None:
        samples = samples[:args.limit]
    if not samples:
        raise ValueError("REQUESTED_SAMPLES_EMPTY")
    ids = [row["sample_id"] for row in samples]
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_SAMPLE_IDS")
    missing_media: list[str] = []
    for row in samples:
        for media in row.get("media") or []:
            kind = str(media.get("kind") or "image")
            paths = media.get("paths") if kind == "video_frames" else [media.get("path")]
            if not isinstance(paths, list) or not paths:
                raise ValueError(f"MEDIA_PATH_SCHEMA_INVALID:{row['sample_id']}:{kind}")
            for raw_path in paths:
                if not isinstance(raw_path, str) or not Path(raw_path).is_file():
                    missing_media.append(str(raw_path))
    if missing_media:
        raise ValueError(f"MATERIALIZED_MEDIA_MISSING:{len(missing_media)}")
    plan = {
        "status": "PLANNED", "run_id": args.run_id, "sample_count": len(samples),
        "total_input_count": len(all_samples), "num_shards": args.num_shards,
        "shard_index": args.shard_index,
        "image_references": sum(media.get("kind") == "image" for row in samples for media in row.get("media") or []),
        "video_references": sum(media.get("kind") in {"video", "video_frames"} for row in samples for media in row.get("media") or []),
        "seed": args.seed, "decode": {"do_sample": False, "max_new_tokens": args.max_new_tokens},
    }
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    environment = json.loads(args.environment.read_text(encoding="utf-8"))
    if environment.get("model_revision") != MODEL_REVISION:
        raise ValueError("UNEXPECTED_MODEL_REVISION")
    if torch.cuda.device_count() != 1:
        raise RuntimeError(f"EXPECTED_ONE_VISIBLE_GPU:found={torch.cuda.device_count()}")
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    torch.set_float32_matmul_precision("high")
    processor = AutoProcessor.from_pretrained(args.model_path, local_files_only=True, use_fast=True)
    model = AutoModelForImageTextToText.from_pretrained(
        args.model_path, local_files_only=True, dtype=torch.bfloat16,
        device_map="cuda", attn_implementation="sdpa", low_cpu_mem_usage=True,
    )
    model.eval()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    existing = read_jsonl(args.output)
    if existing and not args.resume:
        raise FileExistsError(f"OUTPUT_EXISTS:{args.output}")
    existing_ids = [row["sample_id"] for row in existing]
    if len(existing_ids) != len(set(existing_ids)) or not set(existing_ids).issubset(ids):
        raise ValueError("EXISTING_OUTPUT_INVALID")
    completed = set(existing_ids)
    request_hash = sha256_file(args.requested_samples)
    started_at = datetime.now(timezone.utc).isoformat()
    with args.output.open("a", encoding="utf-8") as stream:
        for index, sample in enumerate(samples, 1):
            if sample["sample_id"] in completed:
                continue
            started = time.perf_counter()
            record: dict[str, Any] = {
                "schema_version": "spaceconflict_qwen25vl7b_prediction_v1",
                "run_id": args.run_id, "sample_id": sample["sample_id"],
                "pair_id": sample.get("pair_id"), "component": sample["component"],
                "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
                "requested_samples_sha256": request_hash, "seed": args.seed,
                "decode": {"do_sample": False, "max_new_tokens": args.max_new_tokens},
                "run_started_at_utc": started_at,
            }
            try:
                response, prompt_tokens, generated_tokens = generate(model, processor, sample, args)
                record.update({
                    "raw_response": response, "prediction": parse_model_response(response),
                    "prompt_tokens": prompt_tokens, "generated_tokens": generated_tokens, "error": None,
                })
            except Exception as exc:
                record.update({
                    "raw_response": "", "prediction": parse_model_response(""),
                    "error": f"{type(exc).__name__}: {exc}",
                })
                torch.cuda.empty_cache()
            record["inference_seconds"] = round(time.perf_counter() - started, 4)
            record["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            print(json.dumps({
                "index": index, "total": len(samples), "sample_id": sample["sample_id"],
                "label": record["prediction"]["label"], "schema_valid": record["prediction"]["schema_valid"],
                "error": record["error"], "seconds": record["inference_seconds"],
            }, ensure_ascii=False), flush=True)

    observed = read_jsonl(args.output)
    if [row["sample_id"] for row in observed] != ids:
        raise RuntimeError("OUTPUT_COVERAGE_OR_ORDER_INVALID")
    failures = [row for row in observed if row.get("error")]
    manifest = {
        "status": "PASS" if not failures else "FAIL", "run_id": args.run_id,
        "model_id": MODEL_ID, "model_revision": MODEL_REVISION, "seed": args.seed,
        "requested_samples": str(args.requested_samples), "requested_samples_sha256": request_hash,
        "output": str(args.output), "output_sha256": sha256_file(args.output),
        "sample_count": len(observed), "failure_count": len(failures),
        "total_input_count": len(all_samples), "num_shards": args.num_shards,
        "shard_index": args.shard_index,
        "strict_json_valid": sum(row["prediction"]["strict_json_valid"] for row in observed),
        "schema_valid": sum(row["prediction"]["schema_valid"] for row in observed),
        "software": {"torch": torch.__version__, "transformers": transformers.__version__},
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"), "cuda_device": torch.cuda.get_device_name(0),
    }
    manifest_path = args.output.with_suffix(args.output.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
