#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from spaceconflict.adapters.ca_vqa import adapt
from spaceconflict.adapters.common import record_hash
from spaceconflict.hashing import sha256_file


ADAPTER_VERSION = "ca_vqa_train_tfrecord_v1"
FRAME_FEATURES = ("images", "depth_maps_arkit", "depth_maps_ground_truth", "depth_maps_monocular")


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def payload(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(compact(row) + b"\n" for row in rows)


def write_versioned(path: Path, value: bytes, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume:
            raise FileExistsError(f"OUTPUT_EXISTS:{path}")
        if path.read_bytes() != value:
            raise ValueError(f"NONDETERMINISTIC_OUTPUT:{path}")
    else:
        path.write_bytes(value)


def tfrecords(path: Path) -> Iterator[tuple[int, bytes]]:
    with path.open("rb") as handle:
        index = 0
        while True:
            length_bytes = handle.read(8)
            if not length_bytes:
                return
            if len(length_bytes) != 8 or len(handle.read(4)) != 4:
                raise ValueError(f"TFRECORD_TRUNCATED_HEADER:{path}:{index}")
            length = struct.unpack("<Q", length_bytes)[0]
            value = handle.read(length)
            if len(value) != length or len(handle.read(4)) != 4:
                raise ValueError(f"TFRECORD_TRUNCATED_PAYLOAD:{path}:{index}")
            yield index, value
            index += 1


def frame_roles(relative_shard: str, record_index: int, image_hashes: list[str]) -> dict[str, str]:
    count = len(image_hashes)
    names = [*(f"support_frame_{distance}" for distance in range(count - 1, 0, -1)), "reference_frame"]
    return {
        role: f"tfrecord://{relative_shard}#record={record_index}&feature=images&index={index}&sha256={image_hashes[index].removeprefix('sha256:')}"
        for index, role in enumerate(names)
    }


def keep_example(examples: list[tuple[str, dict[str, Any]]], row: dict[str, Any], limit: int) -> None:
    key = hashlib.sha256(compact(row)).hexdigest()
    examples.append((key, row))
    examples.sort(key=lambda item: item[0])
    del examples[limit:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--selection-manifest", type=Path, required=True)
    parser.add_argument("--download-results", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--task", choices=["binary", "cardinality", "multichoice"], required=True)
    parser.add_argument("--output-version", default="ca_vqa_train_production_subset_v2")
    parser.add_argument("--report-version", default="v2")
    parser.add_argument("--candidate-cap-per-world", type=int, default=8)
    parser.add_argument("--reject-example-limit", type=int, default=256)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    root, data_root = args.root.resolve(), args.data_root.resolve()
    selection_manifest, download_results = args.selection_manifest.resolve(), args.download_results.resolve()
    selected = [
        json.loads(line) for line in selection_manifest.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line)["task"] == args.task
    ]
    if args.limit is not None:
        selected = selected[:args.limit]
    results = {}
    with download_results.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get("status") not in {"DOWNLOADED_AND_VERIFIED", "ALREADY_VALID"}:
                continue
            relative = row["url"].split("/datasets/cavqa/", 1)[-1]
            results[relative] = row
    if len(selected) == 0:
        raise ValueError(f"NO_SELECTED_SHARDS:{args.task}")
    output_root = root / "data/staging/ca_vqa_train" / args.source_revision / args.output_version / args.task
    paths = {
        "source_rows": output_root / "source_rows.jsonl",
        "fact_candidates": output_root / "fact_candidates.jsonl",
        "reject_examples": root / "rejected/metadata/ca_vqa_train" / args.source_revision / args.output_version / f"{args.task}.examples.jsonl",
    }
    report_path = root / "reports/ca_vqa" / f"train_production_subset.{args.task}.{args.report_version}.json"
    if args.dry_run:
        print(json.dumps({
            "status": "PLANNED", "task": args.task, "run_id": args.run_id,
            "selected_shard_count": len(selected), "outputs": {name: str(path) for name, path in paths.items()},
        }, sort_keys=True))
        return 0
    if args.resume and report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("status") != "PRODUCTION_SUBSET_TASK_VALID" or report.get("task") != args.task:
            raise ValueError(f"RESUME_REPORT_INVALID:{report_path}")
        expected_selection_hash = report["input_hashes"].get(str(selection_manifest.relative_to(root)))
        if expected_selection_hash != sha256_file(selection_manifest):
            raise ValueError("RESUME_SELECTION_MANIFEST_HASH_MISMATCH")
        for shard_row in selected:
            relative_shard = shard_row["relative_path"]
            result = results.get(relative_shard)
            expected_hash = report["input_hashes"].get(relative_shard)
            if result is None or expected_hash != "sha256:" + result["sha256"].removeprefix("sha256:"):
                raise ValueError(f"RESUME_SELECTED_SHARD_EVIDENCE_MISMATCH:{relative_shard}")
            path = Path(result["local_path"])
            if not path.is_file() or path.stat().st_size != int(result["bytes"]):
                raise ValueError(f"RESUME_SELECTED_SHARD_MISSING:{relative_shard}")
        for path in paths.values():
            if sha256_file(path) != report["output_hashes"][str(path.relative_to(root))]:
                raise ValueError(f"RESUME_OUTPUT_HASH_MISMATCH:{path}")
        print(json.dumps({
            "status": report["status"], "task": args.task, "resumed": True,
            "selected_shard_count": report["selected_shard_count"],
            "record_count": report["record_count"], "qa_count": report["qa_count"],
            "selected_candidate_count": report["selected_candidate_count"],
            "selected_world_count": report["selected_world_count"], "next_gate": report["next_gate"],
        }, sort_keys=True))
        return 0

    from tensorflow.io import decode_image
    from tensorflow.train import Example

    source_rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    reject_examples: list[tuple[str, dict[str, Any]]] = []
    reject_counts: Counter[str] = Counter()
    frame_counts: Counter[int] = Counter()
    record_count = qa_count = accepted_qa_count = decoded_image_count = 0
    input_hashes = {}
    shard_record_counts = {}
    for shard_row in selected:
        relative_shard = shard_row["relative_path"]
        result = results.get(relative_shard)
        if result is None:
            raise ValueError(f"SELECTED_SHARD_NOT_FINALIZED:{relative_shard}")
        shard = (data_root / relative_shard).resolve()
        if shard != Path(result["local_path"]).resolve() or shard.stat().st_size != int(result["bytes"]):
            raise ValueError(f"SELECTED_SHARD_PATH_OR_SIZE_MISMATCH:{relative_shard}")
        input_hashes[relative_shard] = "sha256:" + result["sha256"].removeprefix("sha256:")
        shard_records = 0
        for record_index, serialized in tfrecords(shard):
            shard_records += 1
            record_count += 1
            serialized_hash = digest(serialized)
            example = Example.FromString(serialized)
            features = example.features.feature
            byte_values = {key: list(features[key].bytes_list.value) for key in FRAME_FEATURES}
            questions = list(features["questions"].bytes_list.value)
            answers = list(features["answers"].bytes_list.value)
            frame_count = len(byte_values["images"])
            valid_shape = (
                frame_count >= 1 and all(len(value) == frame_count for value in byte_values.values())
                and len(features["poses"].float_list.value) == frame_count * 16
                and len(features["intrinsics"].float_list.value) == frame_count * 9
                and len(questions) == len(answers) and bool(questions)
            )
            if not valid_shape:
                reject_counts["TRAIN_RECORD_SHAPE_INVALID"] += len(questions) or 1
                keep_example(reject_examples, {
                    "scope": "source_record", "task": args.task, "shard": relative_shard,
                    "record_index": record_index, "reject_codes": ["TRAIN_RECORD_SHAPE_INVALID"],
                    "record_sha256": serialized_hash,
                }, args.reject_example_limit)
                continue
            image_hashes = [digest(value) for value in byte_values["images"]]
            try:
                for value in byte_values["images"]:
                    decoded = decode_image(value, channels=3, expand_animations=False)
                    shape = [int(size) for size in decoded.shape]
                    if len(shape) != 3 or min(shape) <= 0 or shape[2] != 3:
                        raise ValueError(shape)
            except Exception as error:
                reject_counts["MEDIA_DECODE_FAIL"] += len(questions)
                keep_example(reject_examples, {
                    "scope": "source_record", "task": args.task, "shard": relative_shard,
                    "record_index": record_index, "reject_codes": ["MEDIA_DECODE_FAIL"],
                    "detail": type(error).__name__, "record_sha256": serialized_hash,
                }, args.reject_example_limit)
                continue
            decoded_image_count += frame_count
            frame_counts[frame_count] += 1
            bundle_hash = digest("\0".join(image_hashes).encode("ascii"))
            bundle_id = bundle_hash.removeprefix("sha256:")[:24]
            roles = frame_roles(relative_shard, record_index, image_hashes)
            selected_qas: list[tuple[str, int, str, str]] = []
            for qa_index, (question_bytes, answer_bytes) in enumerate(zip(questions, answers, strict=True)):
                qa_count += 1
                try:
                    question, answer = question_bytes.decode("utf-8").strip(), answer_bytes.decode("utf-8").strip()
                except UnicodeDecodeError:
                    reject_counts["SOURCE_TEXT_NOT_UTF8"] += 1
                    continue
                scan_row = {
                    "task": args.task, "id": f"scan:{qa_index}", "capture_id": f"train_bundle_{bundle_id}",
                    "reference_index": f"record_{record_index}_frame_{frame_count - 1}", "qa_index": str(qa_index),
                    "question": question, "answer": answer, "media_roles": roles,
                    "global_world_id": f"ca_vqa_train:{bundle_id}", "adapter_version": ADAPTER_VERSION,
                    "blocking_reject_codes": [], "source_record_hash": "sha256:" + "0" * 64,
                    "source_media_field_paths": [f"tfrecord.images[{index}]" for index in range(frame_count)],
                }
                adapted = adapt(scan_row, qa_index)
                if adapted.status == "WAITING_MEDIA" and adapted.reconstruction_pass:
                    accepted_qa_count += 1
                    selection_key = hashlib.sha256(f"{args.seed}\0{relative_shard}\0{record_index}\0{qa_index}".encode()).hexdigest()
                    selected_qas.append((selection_key, qa_index, question, answer))
                    selected_qas.sort(key=lambda item: item[0])
                    del selected_qas[args.candidate_cap_per_world:]
                else:
                    codes = adapted.reject_codes or ["SOURCE_RECONSTRUCTION_FAIL"]
                    reject_counts.update(codes)
                    keep_example(reject_examples, {
                        "scope": "adapter", "task": args.task, "shard": relative_shard,
                        "record_index": record_index, "qa_index": qa_index, "reject_codes": codes,
                    }, args.reject_example_limit)
            for _, qa_index, question, answer in selected_qas:
                source_id = f"train:{args.task}:{shard.name}:{record_index}:{qa_index}"
                source_locator = {
                    "tfrecord": relative_shard, "record_index": record_index, "qa_index": qa_index,
                    "frame_count": frame_count, "record_sha256": serialized_hash, "bundle_sha256": bundle_hash,
                }
                core = {
                    "task": args.task, "id": source_id, "capture_id": f"train_bundle_{bundle_id}",
                    "reference_index": f"record_{record_index}_frame_{frame_count - 1}", "qa_index": str(qa_index),
                    "question": question, "answer": answer, "media_roles": roles,
                    "global_world_id": f"ca_vqa_train:{bundle_id}", "adapter_version": ADAPTER_VERSION,
                    "source_locator": source_locator,
                    "source_media_field_paths": [f"tfrecord.images[{index}]" for index in range(frame_count)],
                    "blocking_reject_codes": [],
                }
                core["source_record_hash"] = record_hash(core)
                source_rows.append(core)
                adapted = adapt(core, qa_index).to_dict()
                if adapted["status"] != "WAITING_MEDIA" or not adapted["reconstruction_pass"]:
                    raise ValueError(f"SELECTED_CANDIDATE_REBUILD_FAILED:{source_id}")
                adapted["status"] = "MEDIA_REFERENCE_VALID"
                candidates.append(adapted)
        shard_record_counts[relative_shard] = shard_records

    source_rows.sort(key=lambda row: (row["global_world_id"], row["id"]))
    candidates.sort(key=lambda row: (row["global_world_id"], row["source_item_id"]))
    reject_rows = [row for _, row in sorted(reject_examples)]
    values = {"source_rows": payload(source_rows), "fact_candidates": payload(candidates), "reject_examples": payload(reject_rows)}
    for name, path in paths.items():
        write_versioned(path, values[name], args.resume)
    report = {
        "schema_version": "1.0", "dataset": "ca_vqa", "task": args.task,
        "output_version": args.output_version, "adapter_version": ADAPTER_VERSION,
        "status": "PRODUCTION_SUBSET_TASK_VALID" if candidates else "REJECTED",
        "source_revision": args.source_revision, "selected_shard_count": len(selected),
        "selected_bytes": sum(int(row["expected_bytes"]) for row in selected),
        "record_count": record_count, "qa_count": qa_count, "accepted_qa_count": accepted_qa_count,
        "accepted_qa_rate": accepted_qa_count / qa_count if qa_count else 0.0,
        "selected_candidate_count": len(candidates),
        "selected_world_count": len({row["global_world_id"] for row in candidates}),
        "candidate_cap_per_world": args.candidate_cap_per_world,
        "decoded_image_count": decoded_image_count, "frame_count_distribution": dict(sorted(frame_counts.items())),
        "adapter_reject_code_counts": dict(sorted(reject_counts.items())),
        "reject_example_count": len(reject_rows), "shard_record_counts": dict(sorted(shard_record_counts.items())),
        "input_hashes": {
            str(selection_manifest.relative_to(root)): sha256_file(selection_manifest),
            **dict(sorted(input_hashes.items())),
        },
        "download_manifest_evidence": {
            "path": str(download_results.relative_to(root)),
            "policy": "selected_finalized_rows_only_live_manifest_not_whole_file_hashed",
        },
        "outputs": {name: str(path.relative_to(root)) for name, path in paths.items()},
        "output_hashes": {str(paths[name].relative_to(root)): digest(value) for name, value in values.items()},
        "next_gate": "COMBINE_AND_WORLD_CAP",
    }
    write_versioned(report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n", args.resume)
    print(json.dumps({key: report[key] for key in (
        "status", "task", "selected_shard_count", "record_count", "qa_count", "accepted_qa_count",
        "selected_candidate_count", "selected_world_count", "decoded_image_count", "next_gate",
    )}, sort_keys=True))
    return 0 if report["status"] == "PRODUCTION_SUBSET_TASK_VALID" else 2


if __name__ == "__main__":
    raise SystemExit(main())
