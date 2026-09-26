#!/usr/bin/env python3
"""Stream-profile the frozen SPAR-7M parquet without loading it into memory."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--parquet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--limit", type=int, default=0, help="0 profiles all rows")
    args = parser.parse_args()
    root = args.root.resolve()
    parquet = args.parquet.resolve()
    output = args.output.resolve()
    output.relative_to(root)
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    if args.dry_run:
        print(json.dumps({
            "status": "PLANNED", "parquet": str(parquet), "output": str(output),
            "limit": args.limit, "seed": args.seed, "run_id": args.run_id,
        }, sort_keys=True))
        return 0

    parquet_file = pq.ParquetFile(parquet)
    qa_types: Counter[str] = Counter()
    qa_formats: Counter[str] = Counter()
    splits: Counter[str] = Counter()
    answer_types: Counter[str] = Counter()
    image_ref_counts: Counter[int] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    row_count = 0
    columns = ["id", "qa_type", "qa_format", "question", "answer", "image", "split"]
    for batch in parquet_file.iter_batches(batch_size=65536, columns=columns):
        for row in batch.to_pylist():
            if args.limit and row_count >= args.limit:
                break
            row_count += 1
            qa_type = str(row.get("qa_type") or "MISSING")
            qa_format = str(row.get("qa_format") or "MISSING")
            split = str(row.get("split") or "MISSING")
            answer = row.get("answer")
            images = row.get("image") or []
            qa_types[qa_type] += 1
            qa_formats[qa_format] += 1
            splits[split] += 1
            image_ref_counts[len(images)] += 1
            answer_types[
                "integer" if isinstance(answer, str) and answer.strip().lstrip("-").isdigit()
                else "choice_letter" if isinstance(answer, str) and answer.strip().upper() in {"A", "B", "C", "D"}
                else "text"
            ] += 1
            if len(examples[qa_type]) < 5:
                examples[qa_type].append({
                    "id": row.get("id"), "qa_format": qa_format,
                    "question": row.get("question"), "answer": answer,
                    "image_count": len(images), "split": split,
                })
        if args.limit and row_count >= args.limit:
            break

    report = {
        "schema_version": "1.0",
        "profile_version": "spar_7m_full_profile_v1",
        "status": "PROFILED",
        "seed": args.seed,
        "run_id": args.run_id,
        "source_revision": "0fe664cbada1e7c1173fd743e0f781882eebf777",
        "parquet_metadata_rows": parquet_file.metadata.num_rows,
        "parquet_row_groups": parquet_file.metadata.num_row_groups,
        "profiled_rows": row_count,
        "limit": args.limit,
        "qa_type_counts": dict(sorted(qa_types.items())),
        "qa_format_counts": dict(sorted(qa_formats.items())),
        "split_counts": dict(sorted(splits.items())),
        "answer_type_counts": dict(sorted(answer_types.items())),
        "image_reference_count_distribution": {str(k): v for k, v in sorted(image_ref_counts.items())},
        "examples_by_qa_type": dict(sorted(examples.items())),
        "input_hashes": {str(parquet): sha256(parquet)},
        "success_count": row_count,
        "failure_count": 0,
        "next_gate": "DETERMINISTIC_NONMETRIC_TASK_SELECTION_AND_ADAPTER_PREFLIGHT",
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        if not args.resume:
            raise FileExistsError(f"Output exists: {output}; use --resume")
        if output.read_bytes() != payload:
            raise ValueError(f"Non-deterministic output: {output}")
    else:
        output.write_bytes(payload)
    print(compact({
        "status": report["status"], "profiled_rows": row_count,
        "qa_type_count": len(qa_types), "output": str(output),
    }).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
