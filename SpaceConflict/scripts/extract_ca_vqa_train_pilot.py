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


EXTRACT_VERSION = "ca_vqa_train_tfrecord_pilot_v2"
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


def tfrecords(path: Path, limit: int) -> Iterator[tuple[int, bytes]]:
    with path.open("rb") as handle:
        index = 0
        while index < limit:
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


def recorded_hashes(results_path: Path, data_root: Path) -> dict[Path, str]:
    found = {}
    with results_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            # The downloader appends this file while the pilot runs. Ignore a
            # possibly incomplete final row and retain only finalized entries.
            locator = row.get("local_path") or row.get("relative_path")
            if not locator or not row.get("sha256"):
                continue
            if row.get("status") in {"DOWNLOADED_AND_VERIFIED", "ALREADY_VALID"}:
                path = Path(locator)
                if not path.is_absolute():
                    path = data_root / path
                found[path.resolve()] = "sha256:" + row["sha256"].removeprefix("sha256:")
    return found


def frame_roles(relative_shard: str, record_index: int, image_hashes: list[str]) -> dict[str, str]:
    count = len(image_hashes)
    names = [
        *(f"support_frame_{distance}" for distance in range(count - 1, 0, -1)),
        "reference_frame",
    ]
    return {
        role: f"tfrecord://{relative_shard}#record={record_index}&feature=images&index={index}&sha256={image_hashes[index].removeprefix('sha256:')}"
        for index, role in enumerate(names)
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--download-results", type=Path, action="append", required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--cardinality", type=Path, required=True)
    parser.add_argument("--multichoice", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--official-readme", type=Path, required=True)
    parser.add_argument("--record-limit", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.limit is not None:
        args.record_limit = min(args.record_limit, args.limit)
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "run_id": args.run_id, "record_limit_per_task": args.record_limit}))
        return 0
    from tensorflow.train import Example

    root = args.root.resolve()
    data_root = args.data_root.resolve()
    source_hashes: dict[Path, str] = {}
    for result_path in args.download_results:
        source_hashes.update(recorded_hashes(result_path, data_root))
    task_paths = {
        "binary": args.binary.resolve(),
        "cardinality": args.cardinality.resolve(),
        "multichoice": args.multichoice.resolve(),
    }
    rows_out: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    frame_counts: Counter[int] = Counter()
    task_qa_counts: Counter[str] = Counter()
    adapter_reject_counts: Counter[str] = Counter()
    input_hashes: dict[str, str] = {}
    for task, shard in task_paths.items():
        if shard not in source_hashes:
            raise ValueError(f"SHARD_NOT_IN_VERIFIED_DOWNLOAD_RESULTS:{shard}")
        relative_shard = str(shard.relative_to(data_root))
        input_hashes[relative_shard] = source_hashes[shard]
        for record_index, serialized in tfrecords(shard, args.record_limit):
            serialized_hash = digest(serialized)
            example = Example.FromString(serialized)
            features = example.features.feature
            byte_values = {key: list(features[key].bytes_list.value) for key in FRAME_FEATURES}
            questions = list(features["questions"].bytes_list.value)
            answers = list(features["answers"].bytes_list.value)
            frame_count = len(byte_values["images"])
            shape = {
                "frame_count": frame_count,
                "frame_feature_counts": {key: len(value) for key, value in byte_values.items()},
                "pose_value_count": len(features["poses"].float_list.value),
                "intrinsic_value_count": len(features["intrinsics"].float_list.value),
                "question_count": len(questions), "answer_count": len(answers),
            }
            valid_shape = (
                frame_count >= 1 and all(len(value) == frame_count for value in byte_values.values())
                and shape["pose_value_count"] == frame_count * 16
                and shape["intrinsic_value_count"] == frame_count * 9
                and len(questions) == len(answers) and bool(questions)
            )
            if not valid_shape:
                rejects.append({
                    "scope": "source_record", "task": task, "shard": relative_shard,
                    "record_index": record_index, "reject_codes": ["TRAIN_RECORD_SHAPE_INVALID"],
                    "shape": shape, "record_sha256": serialized_hash,
                })
                continue
            image_hashes = [digest(value) for value in byte_values["images"]]
            bundle_hash = digest("\0".join(image_hashes).encode("ascii"))
            bundle_id = bundle_hash.removeprefix("sha256:")[:24]
            roles = frame_roles(relative_shard, record_index, image_hashes)
            frame_counts[frame_count] += 1
            for qa_index, (question_bytes, answer_bytes) in enumerate(zip(questions, answers, strict=True)):
                try:
                    question, answer = question_bytes.decode("utf-8"), answer_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    rejects.append({
                        "scope": "qa", "task": task, "shard": relative_shard,
                        "record_index": record_index, "qa_index": qa_index,
                        "reject_codes": ["SOURCE_TEXT_NOT_UTF8"],
                    })
                    continue
                source_id = f"train:{task}:{shard.stem}:{record_index}:{qa_index}"
                source_locator = {
                    "tfrecord": relative_shard, "record_index": record_index,
                    "qa_index": qa_index, "frame_count": frame_count,
                    "record_sha256": serialized_hash, "bundle_sha256": bundle_hash,
                }
                core = {
                    "task": task, "id": source_id, "capture_id": f"train_bundle_{bundle_id}",
                    "reference_index": f"record_{record_index}_frame_{frame_count - 1}",
                    "qa_index": str(qa_index), "question": question.strip(), "answer": answer.strip(),
                    "media_roles": roles, "global_world_id": f"ca_vqa_train:{bundle_id}",
                    "adapter_version": ADAPTER_VERSION, "source_locator": source_locator,
                    "source_media_field_paths": [f"tfrecord.images[{index}]" for index in range(frame_count)],
                    "blocking_reject_codes": [],
                }
                core["source_record_hash"] = record_hash(core)
                rows_out.append(core)
                result = adapt(core, qa_index).to_dict()
                if result["status"] == "WAITING_MEDIA" and result["reconstruction_pass"]:
                    result["status"] = "MEDIA_REFERENCE_VALID"
                    candidates.append(result)
                else:
                    adapter_reject_counts.update(result["reject_codes"])
                    rejects.append({**result, "scope": "adapter"})
                task_qa_counts[task] += 1
    output_root = root / "data/staging/ca_vqa_train" / args.source_revision / EXTRACT_VERSION
    paths = {
        "source_rows": output_root / "source_rows.jsonl",
        "fact_candidates": output_root / "fact_candidates.jsonl",
        "rejects": root / "rejected/metadata/ca_vqa_train" / args.source_revision / f"{EXTRACT_VERSION}.jsonl",
    }
    values = {
        "source_rows": payload(rows_out), "fact_candidates": payload(candidates),
        "rejects": payload(rejects),
    }
    for name, path in paths.items():
        write_versioned(path, values[name], args.resume)
    reconstruction_failures = sum(not row["reconstruction_pass"] for row in candidates)
    report = {
        "schema_version": "1.0", "dataset": "ca_vqa", "extract_version": EXTRACT_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "status": "TRAIN_PILOT_ADAPTER_VALID" if candidates and not reconstruction_failures else "REJECTED",
        "source_revision": args.source_revision, "record_limit_per_task": args.record_limit,
        "source_record_count": sum(frame_counts.values()), "source_qa_count": len(rows_out),
        "task_qa_counts": dict(sorted(task_qa_counts.items())),
        "frame_count_distribution": {str(key): value for key, value in sorted(frame_counts.items())},
        "adapter_candidate_count": len(candidates), "rejected_count": len(rejects),
        "adapter_reject_code_counts": dict(sorted(adapter_reject_counts.items())),
        "source_reconstruction_failure_count": reconstruction_failures,
        "source_reconstruction_rate": 1.0 if candidates and not reconstruction_failures else 0.0,
        "world_count": len({row["global_world_id"] for row in candidates}),
        "world_id_policy": "content_addressed_ordered_source_image_bundle",
        "reference_frame_policy": "source_order_preserved_reference_frame_last",
        "media_redistributed": False,
        "input_hashes": {
            **dict(sorted(input_hashes.items())),
            str(args.official_readme.relative_to(root)): digest(args.official_readme.read_bytes()),
        },
        "download_manifest_evidence": {
            "paths": [str(path.relative_to(root)) for path in args.download_results],
            "policy": "selected_finalized_rows_only_live_manifest_not_whole_file_hashed",
            "verified_source_artifacts": dict(sorted(input_hashes.items())),
        },
        "output_hashes": {str(paths[name].relative_to(root)): digest(value) for name, value in values.items()},
        "outputs": {name: str(path.relative_to(root)) for name, path in paths.items()},
        "next_gate": "TRAIN_PILOT_MEDIA_LOCATOR_AND_CANONICAL_VALIDATION",
    }
    report_path = root / "reports/ca_vqa/train_adapter_pilot.v2.json"
    write_versioned(report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n", args.resume)
    print(json.dumps({key: report[key] for key in (
        "status", "source_record_count", "source_qa_count", "adapter_candidate_count",
        "rejected_count", "world_count", "next_gate",
    )}, sort_keys=True))
    return 0 if report["status"] == "TRAIN_PILOT_ADAPTER_VALID" else 2


if __name__ == "__main__":
    raise SystemExit(main())
