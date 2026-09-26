#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from spaceconflict.canonical import _canonical_fact, _validator
from spaceconflict.graphs.pipeline import _graph_validator, _merge_duplicates, _node_type, _validation_errors
from spaceconflict.hashing import sha256_bytes, sha256_file


AUDIT_VERSION = "ca_vqa_train_pilot_closure_v3"
CANONICAL_VERSION = "canonical_train_pilot_v3"
GRAPH_VERSION = "world_graph_train_pilot_v3"
SEED = 20260826


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(json_bytes(row) + b"\n" for row in rows)


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_versioned(path: Path, payload: bytes, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume:
            raise FileExistsError(f"OUTPUT_EXISTS:{path}")
        if path.read_bytes() != payload:
            raise ValueError(f"NONDETERMINISTIC_OUTPUT:{path}")
    else:
        path.write_bytes(payload)


def read_tfrecord(path: Path, wanted: set[int]) -> dict[int, bytes]:
    found: dict[int, bytes] = {}
    with path.open("rb") as handle:
        index = 0
        while wanted - set(found):
            length_bytes = handle.read(8)
            if len(length_bytes) != 8 or len(handle.read(4)) != 4:
                raise ValueError(f"TFRECORD_RECORD_NOT_FOUND:{path}:{sorted(wanted - set(found))}")
            length = struct.unpack("<Q", length_bytes)[0]
            value = handle.read(length)
            if len(value) != length or len(handle.read(4)) != 4:
                raise ValueError(f"TFRECORD_TRUNCATED:{path}:{index}")
            if index in wanted:
                found[index] = value
            index += 1
    return found


def split_map_for(world_ids: list[str], seed: int) -> dict[str, str]:
    ordered = sorted(
        world_ids,
        key=lambda world_id: hashlib.sha256(f"{seed}\0{world_id}".encode()).hexdigest(),
    )
    train_count = round(len(ordered) * 0.60)
    dev_count = round(len(ordered) * 0.15)
    return {
        world_id: "train" if index < train_count else "dev" if index < train_count + dev_count else "test"
        for index, world_id in enumerate(ordered)
    }


def safe_name(world_id: str) -> str:
    stem = "".join(c if c.isalnum() or c in "-_." else "_" for c in world_id)
    return f"{stem}.{hashlib.sha256(world_id.encode()).hexdigest()[:12]}.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--extract-report", type=Path, required=True)
    parser.add_argument("--audit-version", default=AUDIT_VERSION)
    parser.add_argument("--canonical-version", default=CANONICAL_VERSION)
    parser.add_argument("--graph-version", default=GRAPH_VERSION)
    parser.add_argument("--split-version", default="ca_vqa_train_pilot_v3")
    parser.add_argument("--valid-status", default="TRAIN_PILOT_CLOSURE_VALID")
    parser.add_argument("--validation-scope", default="decoded_train_pilot")
    parser.add_argument("--next-gate", default="FULL_TRAIN_PROFILE_THEN_PRODUCTION_SUBSET_SELECTION")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print(json.dumps({
            "status": "PLANNED", "run_id": args.run_id,
            "extract_report": str(args.extract_report), "limit": args.limit,
        }, sort_keys=True))
        return 0

    from tensorflow.io import decode_image
    from tensorflow.train import Example

    root, data_root = args.root.resolve(), args.data_root.resolve()
    extract_report = json.loads(args.extract_report.read_text(encoding="utf-8"))
    source_path = root / extract_report["outputs"]["source_rows"]
    candidate_path = root / extract_report["outputs"]["fact_candidates"]
    if sha256_file(source_path) != extract_report["output_hashes"][str(source_path.relative_to(root))]:
        raise ValueError("SOURCE_ROWS_HASH_MISMATCH")
    if sha256_file(candidate_path) != extract_report["output_hashes"][str(candidate_path.relative_to(root))]:
        raise ValueError("CANDIDATES_HASH_MISMATCH")
    rows, candidates = load_jsonl(source_path), load_jsonl(candidate_path)
    if args.limit is not None:
        limited_worlds = {
            row["global_world_id"] for row in candidates[:args.limit]
        }
        candidates = [row for row in candidates if row["global_world_id"] in limited_worlds]
        selected_items = {row["source_item_id"] for row in candidates}
        rows = [row for row in rows if f"ca_vqa:{row['task']}:{row['id']}" in selected_items]
    source_by_item = {f"ca_vqa:{row['task']}:{row['id']}": row for row in rows}
    if len(source_by_item) != len(rows):
        raise ValueError("DUPLICATE_SOURCE_ITEM_ID")

    records_by_shard: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        locator = row["source_locator"]
        records_by_shard[locator["tfrecord"]].add(locator["record_index"])
    decoded_by_record: dict[tuple[str, int], dict[str, Any]] = {}
    decoded_image_count = 0
    for relative_shard, indices in sorted(records_by_shard.items()):
        shard = data_root / relative_shard
        for record_index, serialized in read_tfrecord(shard, indices).items():
            example = Example.FromString(serialized)
            feature = example.features.feature
            images = list(feature["images"].bytes_list.value)
            questions = [value.decode("utf-8").strip() for value in feature["questions"].bytes_list.value]
            answers = [value.decode("utf-8").strip() for value in feature["answers"].bytes_list.value]
            image_hashes = [digest(value) for value in images]
            bundle_hash = digest("\0".join(image_hashes).encode("ascii"))
            shapes = []
            for value in images:
                decoded = decode_image(value, channels=3, expand_animations=False)
                shape = [int(size) for size in decoded.shape]
                if len(shape) != 3 or min(shape) <= 0 or shape[2] != 3:
                    raise ValueError(f"IMAGE_DECODE_INVALID:{relative_shard}:{record_index}:{shape}")
                shapes.append(shape)
            decoded_image_count += len(images)
            decoded_by_record[(relative_shard, record_index)] = {
                "record_sha256": digest(serialized), "bundle_sha256": bundle_hash,
                "image_hashes": image_hashes, "questions": questions, "answers": answers,
                "decoded_shapes": shapes,
            }

    source_failures: list[dict[str, Any]] = []
    for source_item_id, row in source_by_item.items():
        locator = row["source_locator"]
        decoded = decoded_by_record[(locator["tfrecord"], locator["record_index"])]
        qa_index = locator["qa_index"]
        checks = {
            "record_hash": decoded["record_sha256"] == locator["record_sha256"],
            "bundle_hash": decoded["bundle_sha256"] == locator["bundle_sha256"],
            "world_id": row["global_world_id"] == "ca_vqa_train:" + locator["bundle_sha256"].removeprefix("sha256:")[:24],
            "question": decoded["questions"][qa_index] == row["question"],
            "answer": decoded["answers"][qa_index] == row["answer"],
            "frame_count": len(decoded["image_hashes"]) == locator["frame_count"],
        }
        if not all(checks.values()):
            source_failures.append({"source_item_id": source_item_id, "failed_checks": sorted(k for k, v in checks.items() if not v)})

    candidate_failures: list[dict[str, Any]] = []
    canonical_records: list[dict[str, Any]] = []
    canonical_validator = _validator(root)
    for candidate in candidates:
        item_id = candidate["source_item_id"]
        source = source_by_item.get(item_id)
        failures = []
        if source is None:
            failures.append("SOURCE_ROW_MISSING")
        else:
            if candidate["source_record_hash"] != source["source_record_hash"]:
                failures.append("SOURCE_RECORD_HASH_MISMATCH")
            if candidate["source_answer"] != source["answer"] or candidate["reconstructed_answer"] != source["answer"]:
                failures.append("SOURCE_RECONSTRUCTION_MISMATCH")
            if candidate["global_world_id"] != source["global_world_id"]:
                failures.append("WORLD_ID_MISMATCH")
        if not candidate["reconstruction_pass"]:
            failures.append("SOURCE_RECONSTRUCTION_FAIL")
        if candidate["status"] != "MEDIA_REFERENCE_VALID":
            failures.append("CANDIDATE_STATUS_INVALID")
        if failures:
            candidate_failures.append({"source_item_id": item_id, "failed_checks": sorted(set(failures))})
            continue

        locator = candidate["media_locator"]["source_locator"]
        media_id = "media:" + locator["bundle_sha256"].removeprefix("sha256:")[:24]
        roles = candidate["media_locator"]["frame_roles"]
        media = {
            "media_id": media_id, "media_type": "multi_view_images",
            "relative_path": f"tfrecord://{locator['tfrecord']}#record={locator['record_index']}",
            "source_revision": extract_report["source_revision"],
            "archive_member": roles["reference_frame"],
            "reference_frame": roles["reference_frame"],
            "support_frames": [roles[f"support_frame_{index}"] for index in range(1, len(roles))],
            "frame_roles": roles, "validation_scope": args.validation_scope,
        }
        facts = [_canonical_fact(fact, candidate, media) for fact in candidate["facts"]]
        record_core = {
            "dataset": "ca_vqa", "source_item_id": item_id,
            "source_record_hash": candidate["source_record_hash"], "facts": facts, "media": media,
        }
        record_hash = sha256_bytes(json_bytes(record_core))
        record = {
            "record_id": "record:" + record_hash.removeprefix("sha256:")[:24],
            "schema_version": "1.0", "source_dataset": "ca_vqa",
            "source_item_ids": [item_id], "global_world_id": candidate["global_world_id"],
            "media": [media], "facts": facts, "source_record_hash": candidate["source_record_hash"],
        }
        errors = [error.message for error in canonical_validator.iter_errors(record)]
        if errors:
            candidate_failures.append({"source_item_id": item_id, "failed_checks": ["CANONICAL_SCHEMA_INVALID"], "errors": errors})
        else:
            canonical_records.append(record)

    canonical_records.sort(key=lambda row: row["record_id"])
    canonical_path = root / "data/canonical/ca_vqa_train" / extract_report["source_revision"] / args.canonical_version / "records.jsonl"
    canonical_reject_path = root / "rejected/canonical/ca_vqa_train" / extract_report["source_revision"] / f"{args.canonical_version}.jsonl"
    write_versioned(canonical_path, jsonl_bytes(canonical_records), args.resume)
    write_versioned(canonical_reject_path, jsonl_bytes(candidate_failures), args.resume)

    records_by_world: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in canonical_records:
        records_by_world[record["global_world_id"]].append(record)
    split_rows, index_rows, graph_manifest = [], [], []
    graph_validator = _graph_validator(root)
    import yaml
    contract = yaml.safe_load((root / "contracts/ca_vqa.v1.1.yaml").read_text(encoding="utf-8"))
    allowed_predicates = set(contract["allowed_predicates"])
    graph_reject_counts: Counter[str] = Counter()
    graph_valid_count = 0
    graph_rejected_count = 0
    semantic_merge_count = 0
    split_by_world = split_map_for(list(records_by_world), args.seed)
    for world_id, world_records in sorted(records_by_world.items()):
        media_by_id = {media["media_id"]: media for record in world_records for media in record["media"]}
        facts, merged = _merge_duplicates([fact for record in world_records for fact in record["facts"]])
        semantic_merge_count += merged
        node_ids = sorted({value for fact in facts for value in (fact["subject"], fact.get("object")) if isinstance(value, str)})
        graph = {
            "world_graph_id": "world_graph:" + hashlib.sha256(f"{args.graph_version}\0{world_id}".encode()).hexdigest()[:24],
            "schema_version": "1.0", "global_world_id": world_id,
            "source_datasets": ["ca_vqa"], "media": list(media_by_id.values()),
            "nodes": [{"node_id": node, "node_type": _node_type(node)} for node in node_ids],
            "facts": facts, "authorized_rule_ids": sorted(contract["authorized_rules"]),
            "validation_status": "GRAPH_VALID", "reject_codes": [],
        }
        errors = _validation_errors(graph, allowed_predicates, graph_validator)
        graph["validation_status"] = "GRAPH_REJECTED" if errors else "GRAPH_VALID"
        graph["reject_codes"] = errors
        graph_reject_counts.update(errors)
        graph_valid_count += int(not errors)
        graph_rejected_count += int(bool(errors))
        base = root / ("world_graphs" if not errors else "rejected/graphs") / "ca_vqa_train" / args.graph_version
        graph_path = base / safe_name(world_id)
        graph_payload = json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        write_versioned(graph_path, graph_payload, args.resume)
        split = split_by_world[world_id]
        split_rows.append({"global_world_id": world_id, "split": split, "seed": args.seed})
        index_rows.append({
            "global_world_id": world_id, "source_datasets": ["ca_vqa"],
            "record_ids": sorted(record["record_id"] for record in world_records),
            "media_ids": sorted(media_by_id), "record_count": len(world_records), "fact_count": len(facts),
        })
        graph_manifest.append({
            "global_world_id": world_id, "split": split, "validation_status": graph["validation_status"],
            "graph_path": str(graph_path.relative_to(root)), "graph_sha256": sha256_bytes(graph_payload),
            "record_count": len(world_records), "fact_count": len(facts),
        })

    split_path = root / "splits" / f"{args.split_version}.seed_{args.seed}.jsonl"
    index_path = root / "world_index" / f"{args.split_version}.jsonl"
    manifest_path = root / "world_graphs" / f"manifest.{args.graph_version}.jsonl"
    for path, value in ((split_path, split_rows), (index_path, index_rows), (manifest_path, graph_manifest)):
        write_versioned(path, jsonl_bytes(value), args.resume)

    status = (
        args.valid_status if not source_failures and not candidate_failures and graph_valid_count
        else "REJECTED"
    )
    report = {
        "schema_version": "1.0", "audit_version": args.audit_version, "status": status,
        "source_revision": extract_report["source_revision"],
        "source_record_count": len(decoded_by_record), "source_qa_count": len(rows),
        "decoded_image_count": decoded_image_count, "decoded_image_failure_count": 0,
        "source_locator_failure_count": len(source_failures), "source_locator_failures": source_failures,
        "candidate_count": len(candidates), "candidate_failure_count": len(candidate_failures),
        "canonical_record_count": len(canonical_records), "world_count": len(records_by_world),
        "split_distribution": dict(sorted(Counter(row["split"] for row in split_rows).items())),
        "world_split_isolation": "PASS",
        "graph_valid_count": graph_valid_count, "graph_rejected_count": graph_rejected_count,
        "graph_reject_code_counts": dict(sorted(graph_reject_counts.items())),
        "semantic_duplicate_fact_merge_count": semantic_merge_count,
        "media_redistributed": False,
        "outputs": {
            "canonical_records": str(canonical_path.relative_to(root)),
            "canonical_rejects": str(canonical_reject_path.relative_to(root)),
            "world_index": str(index_path.relative_to(root)), "split": str(split_path.relative_to(root)),
            "graph_manifest": str(manifest_path.relative_to(root)),
        },
        "input_hashes": {
            str(args.extract_report.relative_to(root)): sha256_file(args.extract_report),
            str(source_path.relative_to(root)): sha256_file(source_path),
            str(candidate_path.relative_to(root)): sha256_file(candidate_path),
        },
        "output_hashes": {
            str(path.relative_to(root)): sha256_file(path)
            for path in (canonical_path, canonical_reject_path, index_path, split_path, manifest_path)
        },
        "next_gate": args.next_gate,
    }
    report_path = args.output.resolve() if args.output else root / "reports/ca_vqa/train_pilot_closure.v3.json"
    write_versioned(report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n", args.resume)
    print(json.dumps({key: report[key] for key in (
        "status", "source_record_count", "source_qa_count", "decoded_image_count",
        "candidate_count", "canonical_record_count", "world_count", "graph_valid_count",
        "graph_rejected_count", "next_gate",
    )}, sort_keys=True))
    return 0 if status == args.valid_status else 2


if __name__ == "__main__":
    raise SystemExit(main())
