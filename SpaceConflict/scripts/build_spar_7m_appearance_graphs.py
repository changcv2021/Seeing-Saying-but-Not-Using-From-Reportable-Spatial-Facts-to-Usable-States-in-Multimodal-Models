#!/usr/bin/env python3
"""Build source-reference canonical records and graphs for SPAR-7M appearance order."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from spaceconflict.adapters.spar import (
    SPAR7M_APPEARANCE_ADAPTER_VERSION,
    adapt_appearance_order,
)
from spaceconflict.canonical import _canonical_fact, _validator
from spaceconflict.graphs.pipeline import (
    _graph_validator,
    _merge_duplicates,
    _node_type,
    _validation_errors,
)
from spaceconflict.hashing import sha256_bytes, sha256_file


SOURCE_REVISION = "0fe664cbada1e7c1173fd743e0f781882eebf777"
CANONICAL_VERSION = "canonical_spar_7m_appearance_v1"
GRAPH_VERSION = "world_graph_spar_7m_appearance_v1"
SPLIT_VERSION = "spar_7m_appearance_v1"
BUILD_VERSION = "spar_7m_appearance_graph_build_v1"


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(json_bytes(row) + b"\n" for row in rows)


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


def split_map(world_ids: list[str], seed: int) -> dict[str, str]:
    ordered = sorted(
        world_ids,
        key=lambda world_id: (
            hashlib.sha256(f"{seed}\0{world_id}".encode()).hexdigest(), world_id,
        ),
    )
    train_end = round(len(ordered) * 0.60)
    dev_end = train_end + round(len(ordered) * 0.15)
    return {
        world_id: "train" if index < train_end else "dev" if index < dev_end else "test"
        for index, world_id in enumerate(ordered)
    }


def safe_name(world_id: str) -> str:
    stem = "".join(char if char.isalnum() or char in "-_." else "_" for char in world_id)
    return f"{stem}.{hashlib.sha256(world_id.encode()).hexdigest()[:12]}.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--selection-report", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    input_path = args.input.resolve()
    selection_report_path = args.selection_report.resolve()
    if args.dry_run:
        print(json.dumps({
            "status": "PLANNED", "input": str(input_path), "limit": args.limit,
            "canonical_version": CANONICAL_VERSION, "graph_version": GRAPH_VERSION,
        }, sort_keys=True))
        return 0

    selection_report = json.loads(selection_report_path.read_text(encoding="utf-8"))
    relative_input = str(input_path.relative_to(root))
    if selection_report.get("status") != "SUBSET_SELECTED":
        raise ValueError("SELECTION_REPORT_NOT_VALID")
    if selection_report["output_hashes"].get(relative_input) != sha256_file(input_path):
        raise ValueError("SELECTED_ROWS_HASH_MISMATCH")
    rows = load_jsonl(input_path)
    if args.limit is not None:
        rows = rows[:args.limit]

    results = [adapt_appearance_order(row, index) for index, row in enumerate(rows)]
    accepted = [result for result in results if result.status == "SOURCE_REFERENCE_VALID"]
    rejected = [result.to_dict() for result in results if result.status == "REJECTED"]
    source_item_counts = Counter(result.source_item_id for result in accepted)
    duplicate_items = sorted(item for item, count in source_item_counts.items() if count > 1)
    if duplicate_items:
        raise ValueError(f"DUPLICATE_SOURCE_ITEM_ID:{duplicate_items[:5]}")

    media_index: dict[str, dict[str, Any]] = {}
    candidate_rows: list[dict[str, Any]] = []
    for result in accepted:
        candidate = result.to_dict()
        locator = candidate["media_locator"]
        paths = locator.pop("ordered_frame_paths")
        media_core = {
            "source_revision": locator["revision"], "base_dataset": locator["base_dataset"],
            "scene_id": locator["scene_id"], "ordered_frame_paths": paths,
        }
        media_id = "media:" + hashlib.sha256(json_bytes(media_core)).hexdigest()[:24]
        media_index.setdefault(media_id, {"media_id": media_id, **media_core, "frame_count": len(paths)})
        locator.update({
            "media_id": media_id,
            "ordered_frame_manifest": f"data/media_index/spar/{SOURCE_REVISION}/appearance_order_frames.v1.jsonl",
            "ordered_frame_manifest_key": media_id,
        })
        candidate_rows.append(candidate)
    candidate_rows.sort(key=lambda row: row["source_item_id"])
    rejected.sort(key=lambda row: row["source_item_id"])
    media_rows = [media_index[key] for key in sorted(media_index)]

    candidate_path = root / f"data/staging/adapters/spar/{SOURCE_REVISION}/{SPAR7M_APPEARANCE_ADAPTER_VERSION}/fact_candidates.jsonl"
    adapter_reject_path = root / f"rejected/metadata/spar/{SOURCE_REVISION}/{SPAR7M_APPEARANCE_ADAPTER_VERSION}.jsonl"
    media_index_path = root / f"data/media_index/spar/{SOURCE_REVISION}/appearance_order_frames.v1.jsonl"
    write_versioned(candidate_path, jsonl_bytes(candidate_rows), args.resume)
    write_versioned(adapter_reject_path, jsonl_bytes(rejected), args.resume)
    write_versioned(media_index_path, jsonl_bytes(media_rows), args.resume)

    canonical_validator = _validator(root)
    canonical_records: list[dict[str, Any]] = []
    canonical_rejects: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        locator = candidate["media_locator"]
        media_row = media_index[locator["media_id"]]
        media = {
            "media_id": locator["media_id"], "media_type": "ordered_multi_frame",
            "relative_path": media_row["ordered_frame_paths"][0],
            "archive_member": media_row["ordered_frame_paths"][0],
            "source_revision": SOURCE_REVISION,
            "ordered_frame_manifest": locator["ordered_frame_manifest"],
            "ordered_frame_manifest_key": locator["ordered_frame_manifest_key"],
            "ordered_frame_count": media_row["frame_count"],
            "validation_scope": "OFFICIAL_ANNOTATION_PATH_REFERENCES_ONLY",
            "source_reference_only": True,
            "local_media_byte_validation": "NOT_PERFORMED_UNDERLYING_MEDIA_NOT_PRESENT",
        }
        facts = [_canonical_fact(source_fact, candidate, media) for source_fact in candidate["facts"]]
        record_core = {
            "dataset": "spar", "source_item_id": candidate["source_item_id"],
            "source_record_hash": candidate["source_record_hash"], "facts": facts, "media": media,
        }
        record_hash = sha256_bytes(json_bytes(record_core))
        record = {
            "record_id": "record:" + record_hash.removeprefix("sha256:")[:24],
            "schema_version": "1.0", "source_dataset": "spar",
            "source_item_ids": [candidate["source_item_id"]],
            "global_world_id": candidate["global_world_id"],
            "media": [media], "facts": facts,
            "source_record_hash": candidate["source_record_hash"],
        }
        errors = [error.message for error in canonical_validator.iter_errors(record)]
        if errors:
            canonical_rejects.append({
                "source_item_id": candidate["source_item_id"],
                "reject_codes": ["CANONICAL_SCHEMA_INVALID"], "schema_errors": errors,
            })
        else:
            canonical_records.append(record)
    canonical_records.sort(key=lambda row: row["record_id"])
    canonical_rejects.sort(key=lambda row: row["source_item_id"])
    canonical_path = root / f"data/canonical/spar/{SOURCE_REVISION}/{CANONICAL_VERSION}/records.jsonl"
    canonical_reject_path = root / f"rejected/canonical/spar/{SOURCE_REVISION}/{CANONICAL_VERSION}.jsonl"
    write_versioned(canonical_path, jsonl_bytes(canonical_records), args.resume)
    write_versioned(canonical_reject_path, jsonl_bytes(canonical_rejects), args.resume)

    records_by_world: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in canonical_records:
        records_by_world[record["global_world_id"]].append(record)
    assignments = split_map(sorted(records_by_world), args.seed)
    split_rows = [
        {"global_world_id": world_id, "split": assignments[world_id], "seed": args.seed}
        for world_id in sorted(records_by_world)
    ]
    split_path = root / f"splits/{SPLIT_VERSION}.seed_{args.seed}.jsonl"
    write_versioned(split_path, jsonl_bytes(split_rows), args.resume)

    contract = yaml.safe_load((root / "contracts/spar.v1.1.yaml").read_text(encoding="utf-8"))
    allowed_predicates = set(contract["allowed_predicates"])
    authorized_rules = sorted(contract["authorized_rules"])
    graph_validator = _graph_validator(root)
    graph_manifest: list[dict[str, Any]] = []
    index_rows: list[dict[str, Any]] = []
    graph_reject_counts: Counter[str] = Counter()
    valid_graph_count = 0
    rejected_graph_count = 0
    duplicate_fact_merge_count = 0
    for world_id, world_records in sorted(records_by_world.items()):
        media_by_id = {
            media["media_id"]: media for record in world_records for media in record["media"]
        }
        facts, merged = _merge_duplicates([fact for record in world_records for fact in record["facts"]])
        duplicate_fact_merge_count += merged
        node_ids = sorted({
            value for fact in facts for value in (fact["subject"], fact.get("object"))
            if isinstance(value, str)
        })
        graph = {
            "world_graph_id": "world_graph:" + hashlib.sha256(
                f"{GRAPH_VERSION}\0{world_id}".encode()
            ).hexdigest()[:24],
            "schema_version": "1.0", "global_world_id": world_id,
            "source_datasets": ["spar"], "media": [media_by_id[key] for key in sorted(media_by_id)],
            "nodes": [{"node_id": node_id, "node_type": _node_type(node_id)} for node_id in node_ids],
            "facts": facts, "authorized_rule_ids": authorized_rules,
            "validation_status": "GRAPH_VALID", "reject_codes": [],
        }
        errors = _validation_errors(graph, allowed_predicates, graph_validator)
        graph["validation_status"] = "GRAPH_REJECTED" if errors else "GRAPH_VALID"
        graph["reject_codes"] = errors
        graph_reject_counts.update(errors)
        valid_graph_count += int(not errors)
        rejected_graph_count += int(bool(errors))
        base = root / ("world_graphs" if not errors else "rejected/graphs") / "spar" / GRAPH_VERSION
        graph_path = base / safe_name(world_id)
        graph_payload = json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        write_versioned(graph_path, graph_payload, args.resume)
        graph_manifest.append({
            "global_world_id": world_id, "split": assignments[world_id],
            "validation_status": graph["validation_status"],
            "graph_path": str(graph_path.relative_to(root)),
            "graph_sha256": sha256_bytes(graph_payload),
            "record_count": len(world_records), "fact_count": len(facts),
        })
        index_rows.append({
            "global_world_id": world_id, "source_datasets": ["spar"],
            "record_ids": sorted(record["record_id"] for record in world_records),
            "media_ids": sorted(media_by_id), "record_count": len(world_records),
            "fact_count": len(facts),
        })
    manifest_path = root / f"world_graphs/manifest.{GRAPH_VERSION}.jsonl"
    index_path = root / f"world_index/{SPLIT_VERSION}.jsonl"
    write_versioned(manifest_path, jsonl_bytes(graph_manifest), args.resume)
    write_versioned(index_path, jsonl_bytes(index_rows), args.resume)

    reconstruction_failures = sum(not row["reconstruction_pass"] for row in candidate_rows)
    output_paths = [
        candidate_path, adapter_reject_path, media_index_path, canonical_path,
        canonical_reject_path, split_path, manifest_path, index_path,
    ]
    status = (
        "SOURCE_REFERENCE_GRAPH_VALID"
        if canonical_records and not canonical_rejects and not reconstruction_failures and not rejected_graph_count
        else "PARTIAL_SOURCE_REFERENCE_GRAPH_VALID" if canonical_records and valid_graph_count
        else "REJECTED"
    )
    report = {
        "schema_version": "1.0", "build_version": BUILD_VERSION, "status": status,
        "run_id": args.run_id, "seed": args.seed, "source_revision": SOURCE_REVISION,
        "adapter_version": SPAR7M_APPEARANCE_ADAPTER_VERSION,
        "canonical_version": CANONICAL_VERSION, "world_graph_version": GRAPH_VERSION,
        "input_row_count": len(rows), "adapter_candidate_count": len(candidate_rows),
        "adapter_rejected_count": len(rejected),
        "adapter_reject_code_counts": dict(sorted(Counter(
            code for row in rejected for code in row["reject_codes"]
        ).items())),
        "source_reconstruction_failure_count": reconstruction_failures,
        "source_reconstruction_rate": (
            (len(candidate_rows) - reconstruction_failures) / len(candidate_rows)
            if candidate_rows else 0.0
        ),
        "canonical_record_count": len(canonical_records),
        "canonical_fact_count": sum(len(record["facts"]) for record in canonical_records),
        "canonical_rejected_count": len(canonical_rejects),
        "world_count": len(records_by_world),
        "split_distribution": dict(sorted(Counter(assignments.values()).items())),
        "world_split_isolation": "PASS",
        "media_bundle_count": len(media_rows), "media_reference_count": sum(row["frame_count"] for row in media_rows),
        "media_validation_scope": "OFFICIAL_ANNOTATION_PATH_REFERENCES_ONLY",
        "local_media_byte_validation": "NOT_PERFORMED_UNDERLYING_SCANNET_MEDIA_NOT_PRESENT",
        "media_redistributed": False,
        "graph_valid_count": valid_graph_count, "graph_rejected_count": rejected_graph_count,
        "graph_reject_code_counts": dict(sorted(graph_reject_counts.items())),
        "semantic_duplicate_fact_merge_count": duplicate_fact_merge_count,
        "identity_policy": "SOURCE_ITEM_LOCAL_EVENTS_NO_CROSS_QA_CATEGORY_MERGE",
        "frame_grounding_policy": "ORDER_FACTS_ONLY_NO_FABRICATED_OBJECT_TO_FRAME_BINDING",
        "input_hashes": {
            str(input_path.relative_to(root)): sha256_file(input_path),
            str(selection_report_path.relative_to(root)): sha256_file(selection_report_path),
        },
        "output_hashes": {str(path.relative_to(root)): sha256_file(path) for path in output_paths},
        "outputs": {
            "candidates": str(candidate_path.relative_to(root)),
            "media_index": str(media_index_path.relative_to(root)),
            "canonical_records": str(canonical_path.relative_to(root)),
            "world_index": str(index_path.relative_to(root)),
            "split": str(split_path.relative_to(root)),
            "graph_manifest": str(manifest_path.relative_to(root)),
        },
        "next_gate": "L3_APPEARANCE_ORDER_CLAIMS_AND_MEDIA_REFERENCE_ABLATION_AUDIT",
    }
    report_path = args.output.resolve() if args.output else root / "reports/spar/appearance_graph_build.v1.json"
    write_versioned(
        report_path,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n",
        args.resume,
    )
    print(json.dumps({
        key: report[key] for key in (
            "status", "input_row_count", "adapter_candidate_count", "adapter_rejected_count",
            "canonical_record_count", "world_count", "graph_valid_count", "graph_rejected_count",
            "next_gate",
        )
    }, sort_keys=True))
    return 0 if valid_graph_count else 2


if __name__ == "__main__":
    raise SystemExit(main())
