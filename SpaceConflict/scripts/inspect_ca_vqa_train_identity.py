#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Iterator


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
            payload = handle.read(length)
            if len(payload) != length or len(handle.read(4)) != 4:
                raise ValueError(f"TFRECORD_TRUNCATED_PAYLOAD:{path}:{index}")
            yield index, payload
            index += 1


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def inspect(task: str, path: Path, limit: int, example_type: Any) -> list[dict[str, Any]]:
    result = []
    for record_index, payload in tfrecords(path, limit):
        example = example_type.FromString(payload)
        features = example.features.feature
        images = list(features["images"].bytes_list.value)
        questions = list(features["questions"].bytes_list.value)
        answers = list(features["answers"].bytes_list.value)
        depth_counts = {
            key: len(features[key].bytes_list.value)
            for key in ("depth_maps_arkit", "depth_maps_ground_truth", "depth_maps_monocular")
        }
        pose_value_count = len(features["poses"].float_list.value)
        intrinsic_value_count = len(features["intrinsics"].float_list.value)
        frame_count = len(images)
        valid_shape = (
            frame_count >= 1 and len(questions) == len(answers) and bool(questions)
            and all(count == frame_count for count in depth_counts.values())
            and pose_value_count == frame_count * 16
            and intrinsic_value_count == frame_count * 9
        )
        image_hashes = [digest(value) for value in images]
        bundle = digest("\0".join(image_hashes).encode("ascii")) if valid_shape else None
        frame_order = [
            *(f"support_frame_{distance}" for distance in range(frame_count - 1, 0, -1)),
            "reference_frame",
        ] if frame_count else None
        result.append({
            "task": task, "record_index": record_index,
            "record_sha256": "sha256:" + digest(payload),
            "image_sha256": ["sha256:" + value for value in image_hashes],
            "bundle_sha256": "sha256:" + bundle if bundle else None,
            "reference_image_sha256": "sha256:" + image_hashes[-1] if images else None,
            "frame_order": frame_order,
            "record_shape_valid": valid_shape,
            "image_count": frame_count,
            "depth_counts": depth_counts,
            "pose_value_count": pose_value_count,
            "intrinsic_value_count": intrinsic_value_count,
            "question_count": len(questions),
            "answer_count": len(answers),
            "first_question": questions[0].decode("utf-8") if questions else None,
            "first_answer": answers[0].decode("utf-8") if answers else None,
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--multichoice", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=64)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--official-readme", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from tensorflow.train import Example

    by_task = {
        "binary": inspect("binary", args.binary, args.limit, Example),
        "multichoice": inspect("multichoice", args.multichoice, args.limit, Example),
    }
    bundle_sets = {
        task: {row["bundle_sha256"] for row in values if row["bundle_sha256"] is not None}
        for task, values in by_task.items()
    }
    intersection = sorted(bundle_sets["binary"] & bundle_sets["multichoice"])
    same_index = sum(
        left["bundle_sha256"] is not None and left["bundle_sha256"] == right["bundle_sha256"]
        for left, right in zip(by_task["binary"], by_task["multichoice"], strict=False)
    )
    report = {
        "schema_version": "1.0", "dataset": "ca_vqa", "audit_version": "ca_vqa_train_identity_preflight_v1",
        "status": "PASS_WITH_SOURCE_SHAPE_REJECTS" if any(
            not row["record_shape_valid"] for values in by_task.values() for row in values
        ) else "PASS",
        "official_frame_order": "zero_or_more_preceding_frames_in_source_order_then_reference_frame_last",
        "official_frame_order_evidence": {
            "path": str(args.official_readme), "revision": args.source_revision,
            "statement": "train images have the reference frame last; val preceding-frame order is [4,3,2,1,reference]",
        },
        "record_limit_per_task": args.limit,
        "record_counts": {task: len(values) for task, values in by_task.items()},
        "valid_record_counts": {task: sum(row["record_shape_valid"] for row in values) for task, values in by_task.items()},
        "invalid_record_shape_counts": {task: sum(not row["record_shape_valid"] for row in values) for task, values in by_task.items()},
        "invalid_record_shape_examples": {
            task: [
                {key: row[key] for key in (
                    "record_index", "image_count", "depth_counts", "pose_value_count",
                    "intrinsic_value_count", "question_count", "answer_count",
                )}
                for row in values if not row["record_shape_valid"]
            ][:20]
            for task, values in by_task.items()
        },
        "question_counts": {task: sum(row["question_count"] for row in values) for task, values in by_task.items()},
        "unique_bundle_counts": {task: len(bundle_sets[task]) for task in by_task},
        "within_task_duplicate_bundle_counts": {
            task: sum(count - 1 for count in Counter(
                row["bundle_sha256"] for row in values if row["bundle_sha256"] is not None
            ).values() if count > 1)
            for task, values in by_task.items()
        },
        "cross_task_bundle_intersection_count": len(intersection),
        "same_record_index_bundle_match_count": same_index,
        "cross_task_bundle_intersection_examples": intersection[:20],
        "provisional_world_id_policy": "ca_vqa_train:sha256_of_ordered_source_image_sha256_values",
        "policy_rationale": "train TFRecords expose no stable capture ID; exact ordered media identity is source-native and avoids guessed cross-record identity",
        "records": by_task,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"], "record_counts": report["record_counts"],
        "invalid_record_shape_counts": report["invalid_record_shape_counts"],
        "question_counts": report["question_counts"],
        "cross_task_bundle_intersection_count": len(intersection),
        "same_record_index_bundle_match_count": same_index,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
