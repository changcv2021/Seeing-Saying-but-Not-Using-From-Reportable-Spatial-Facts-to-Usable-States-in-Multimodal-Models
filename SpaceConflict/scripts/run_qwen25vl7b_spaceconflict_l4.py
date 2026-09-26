#!/usr/bin/env python3
"""Run deterministic Qwen2.5-VL-7B inference on blind SpaceConflict L4 requests."""

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

from spaceconflict.mllm_l4 import SYSTEM_PROMPT, parse_model_response, user_prompt


MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"
DEFAULT_MODEL_PATH = Path("external/scratch/industbench_qwen25vl7b/model/Qwen2.5-VL-7B-Instruct")
DEFAULT_ENVIRONMENT = Path("external/projects/iclr benchmark/industry/reports/qwen25vl7b_full_eval_20260902/environment.json")
DEFAULT_MIN_PIXELS = 128 * 28 * 28
DEFAULT_MAX_PIXELS = 512 * 28 * 28


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


def messages_for(sample: dict[str, Any], min_pixels: int, max_pixels: int) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for index, media in enumerate(sample.get("media") or [], 1):
        content.append({"type": "text", "text": f"Evidence image {index} ({media['role']}):"})
        content.append({
            "type": "image", "image": media["path"],
            "min_pixels": min_pixels, "max_pixels": max_pixels,
        })
    content.append({"type": "text", "text": user_prompt(sample)})
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def generate(model, processor, sample, min_pixels, max_pixels, max_new_tokens):
    messages = messages_for(sample, min_pixels, max_pixels)
    rendered = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    images, videos = process_vision_info(messages)
    inputs = processor(
        text=[rendered], images=images, videos=videos, padding=True, return_tensors="pt"
    )
    inputs = {key: value.to("cuda:0") if hasattr(value, "to") else value for key, value in inputs.items()}
    with torch.inference_mode():
        output = model.generate(
            **inputs, max_new_tokens=max_new_tokens, do_sample=False, use_cache=True,
        )
    prompt_tokens = int(inputs["input_ids"].shape[-1])
    generated = output[:, prompt_tokens:]
    text = processor.batch_decode(
        generated, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0].strip()
    return text, prompt_tokens, int(generated.shape[-1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requested-samples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--environment", type=Path, default=DEFAULT_ENVIRONMENT)
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--min-pixels", type=int, default=DEFAULT_MIN_PIXELS)
    parser.add_argument("--max-pixels", type=int, default=DEFAULT_MAX_PIXELS)
    parser.add_argument("--max-new-tokens", type=int, default=160)
    args = parser.parse_args()
    if args.num_shards < 1 or not 0 <= args.shard_index < args.num_shards:
        raise ValueError("Invalid shard configuration")

    all_samples = read_jsonl(args.requested_samples)
    if not all_samples:
        raise ValueError("Requested-samples file is empty")
    samples = [row for index, row in enumerate(all_samples) if index % args.num_shards == args.shard_index]
    expected_ids = [row["sample_id"] for row in samples]
    if len(expected_ids) != len(set(expected_ids)):
        raise ValueError("Duplicate sample IDs in requested shard")
    environment = json.loads(args.environment.read_text(encoding="utf-8"))
    if environment.get("model_revision") != "cc594898137f460bfe9f0759e9844b3ce807cfb5":
        raise ValueError("Unexpected model revision in pinned environment")
    if torch.cuda.device_count() != 1:
        raise RuntimeError(f"Expected exactly one visible GPU, found {torch.cuda.device_count()}")

    torch.set_float32_matmul_precision("high")
    processor = AutoProcessor.from_pretrained(args.model_path, local_files_only=True, use_fast=True)
    model = AutoModelForImageTextToText.from_pretrained(
        args.model_path, local_files_only=True, dtype=torch.bfloat16,
        device_map="cuda", attn_implementation="sdpa", low_cpu_mem_usage=True,
    )
    model.eval()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    existing = read_jsonl(args.output)
    existing_ids = [row["sample_id"] for row in existing]
    if len(existing_ids) != len(set(existing_ids)) or not set(existing_ids).issubset(expected_ids):
        raise ValueError("Existing output is duplicated or does not belong to this shard")
    completed = set(existing_ids)
    started_at = datetime.now(timezone.utc).isoformat()
    request_hash = sha256_file(args.requested_samples)
    with args.output.open("a", encoding="utf-8") as stream:
        for index, sample in enumerate(samples, 1):
            if sample["sample_id"] in completed:
                continue
            started = time.perf_counter()
            record = {
                "schema_version": "spaceconflict_qwen25vl7b_prediction_v1",
                "run_id": args.run_id,
                "sample_id": sample["sample_id"],
                "pair_id": sample.get("pair_id"),
                "component": sample["component"],
                "model_id": MODEL_ID,
                "model_revision": environment["model_revision"],
                "requested_samples_sha256": request_hash,
                "num_shards": args.num_shards,
                "shard_index": args.shard_index,
                "decode": {"do_sample": False, "max_new_tokens": args.max_new_tokens},
                "image_budget": {"min_pixels": args.min_pixels, "max_pixels": args.max_pixels},
                "run_started_at_utc": started_at,
            }
            try:
                response, prompt_tokens, generated_tokens = generate(
                    model, processor, sample, args.min_pixels, args.max_pixels, args.max_new_tokens,
                )
                parsed = parse_model_response(response)
                record.update({
                    "raw_response": response,
                    "prediction": parsed,
                    "prompt_tokens": prompt_tokens,
                    "generated_tokens": generated_tokens,
                    "error": None,
                })
            except Exception as exc:  # preserve every model/runtime failure
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
                "component": sample["component"], "label": record["prediction"]["label"],
                "schema_valid": record["prediction"]["schema_valid"],
                "error": record["error"], "seconds": record["inference_seconds"],
            }, ensure_ascii=False), flush=True)

    observed = read_jsonl(args.output)
    if [row["sample_id"] for row in observed] != expected_ids:
        raise RuntimeError("Shard output is incomplete, duplicated, or out of order")
    failures = [row for row in observed if row.get("error")]
    if failures:
        raise RuntimeError(f"Inference finished with {len(failures)} runtime failures")
    manifest = {
        "status": "PASS",
        "run_id": args.run_id,
        "model_id": MODEL_ID,
        "model_revision": environment["model_revision"],
        "requested_samples": str(args.requested_samples),
        "requested_samples_sha256": request_hash,
        "output": str(args.output),
        "output_sha256": sha256_file(args.output),
        "sample_count": len(observed),
        "strict_json_valid": sum(row["prediction"]["strict_json_valid"] for row in observed),
        "schema_valid": sum(row["prediction"]["schema_valid"] for row in observed),
        "software": {"torch": torch.__version__, "transformers": transformers.__version__},
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "cuda_device": torch.cuda.get_device_name(0),
    }
    manifest_path = args.output.with_suffix(args.output.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
