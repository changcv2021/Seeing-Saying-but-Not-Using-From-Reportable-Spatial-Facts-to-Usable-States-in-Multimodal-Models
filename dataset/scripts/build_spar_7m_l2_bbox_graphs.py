#!/usr/bin/env python3
"""Build SPAR single-image graphs with exact bbox-annotation identity links."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from build_spar_7m_appearance_graphs import json_bytes, jsonl_bytes, write_versioned
from spaceconflict.adapters.spar import adapt_qualitative_relation
from spaceconflict.canonical import _validator
from spaceconflict.graphs.pipeline import _graph_validator, _merge_duplicates, _node_type, _validation_errors
from spaceconflict.hashing import sha256_bytes, sha256_file


SOURCE_REVISION = "0fe664cbada1e7c1173fd743e0f781882eebf777"


def _bbox(value: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(value, list) or len(value) != 1:
        return None
    box = value[0]
    if not isinstance(box, list) or len(box) != 4 or not all(isinstance(v, int) for v in box):
        return None
    return tuple(box)


def _safe_name(world_id: str) -> str:
    digest = hashlib.sha256(world_id.encode()).hexdigest()[:12]
    stem = "".join(c if c.isalnum() or c in "-_." else "_" for c in world_id)
    return f"{stem[:100]}.{digest}.json"


def _fact_hash(fact: dict[str, Any]) -> dict[str, Any]:
    core = {key: value for key, value in fact.items() if key not in {"fact_id", "canonical_fact_hash"}}
    digest = sha256_bytes(json_bytes(core))
    return {**core, "fact_id": "fact:" + digest.removeprefix("sha256:")[:24], "canonical_fact_hash": digest}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--scan-report", type=Path, required=True)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--artifact-version", choices=("v1", "v2"), default="v1")
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root, input_path = args.root.resolve(), args.input.resolve()
    scan_report_path, split_path = args.scan_report.resolve(), args.split.resolve()
    adapter_version = f"spar_7m_bbox_identity_l2_{args.artifact_version}"
    canonical_version = f"canonical_spar_7m_bbox_identity_l2_{args.artifact_version}"
    graph_version = f"world_graph_spar_7m_bbox_identity_l2_{args.artifact_version}"
    build_version = f"spar_7m_bbox_identity_graph_build_{args.artifact_version}"
    scan_report = json.loads(scan_report_path.read_text())
    if scan_report.get("status") not in {"STRICT_L2_CHAINS_FOUND", "SUBSET_SELECTED"}:
        raise ValueError("STRICT_L2_SCAN_NOT_VALID")
    expected_input_hash = scan_report.get("input_sha256", scan_report.get("output_sha256"))
    if expected_input_hash != sha256_file(input_path):
        raise ValueError("SOURCE_INPUT_HASH_MISMATCH")
    split_by_world = {
        row["global_world_id"]: row["split"]
        for row in (json.loads(line) for line in split_path.open() if line.strip())
    }

    canonical_validator = _validator(root)
    records: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    media_index: dict[str, dict[str, Any]] = {}
    rows_checked = single_image_rows = adapter_accepted = 0
    fact_counts: Counter[str] = Counter()
    reject_counts: Counter[str] = Counter()
    with input_path.open("r", encoding="utf-8") as handle:
        for row_index, line in enumerate(handle):
            if not line.strip():
                continue
            rows_checked += 1
            row = json.loads(line)
            if row.get("qa_type") != "obj_spatial_relation_oo":
                continue
            single_image_rows += 1
            red_box, blue_box = _bbox(row.get("red_bbox")), _bbox(row.get("blue_bbox"))
            images = row.get("image") or []
            adapted = adapt_qualitative_relation(row, row_index)
            if (
                adapted.status != "SOURCE_REFERENCE_VALID" or len(images) != 1
                or red_box is None or blue_box is None or red_box == blue_box
            ):
                codes = adapted.reject_codes or ["INVALID_SINGLE_IMAGE_BBOX_IDENTITY"]
                reject_counts.update(codes)
                rejects.append({
                    "source_item_id": adapted.source_item_id,
                    "source_record_hash": adapted.source_record_hash,
                    "reject_codes": sorted(set(codes)),
                })
                continue
            spatial_facts = [
                fact for fact in adapted.facts
                if fact["predicate"] in {"LEFT_OF", "RIGHT_OF", "ABOVE", "BELOW"}
            ]
            if not spatial_facts:
                reject_counts["NO_TRANSITIVE_DIRECTION_FACT"] += 1
                continue
            adapter_accepted += 1
            image = str(images[0])
            media_token = hashlib.sha256(f"{SOURCE_REVISION}\0{image}".encode()).hexdigest()[:16]
            media_id = "media:" + media_token
            media = {
                "media_id": media_id, "media_type": "single_image", "relative_path": image,
                "archive_member": image, "source_revision": SOURCE_REVISION,
                "validation_scope": "OFFICIAL_ANNOTATION_PATH_AND_BBOX_REFERENCES_ONLY",
                "source_reference_only": True,
                "local_media_byte_validation": "NOT_PERFORMED_UNDERLYING_MEDIA_NOT_PRESENT",
                "bbox_annotation_identity_scope": "EXACT_COORDINATES_WITHIN_THIS_IMAGE_ONLY",
            }
            media_index[media_id] = media
            red = f"bbox_anchor:{media_token}:" + "_".join(map(str, red_box))
            blue = f"bbox_anchor:{media_token}:" + "_".join(map(str, blue_box))
            world_id = str(adapted.global_world_id)
            canonical_facts: list[dict[str, Any]] = []
            for source_fact in spatial_facts:
                fact_counts[source_fact["predicate"]] += 1
                canonical_facts.append(_fact_hash({
                    "subject": red, "predicate": source_fact["predicate"], "object": blue,
                    "value": None, "polarity": "positive",
                    "context": {
                        "world_id": world_id, "media_id": media_id, "view_id": "primary_view",
                        "time_scope": None, "reference_frame": "source_question_declared_perspective",
                        "state_id": "observed", "branch_id": "actual", "scope": "current_media",
                    },
                    "provenance": {
                        "origin_type": "QA_DIRECT", "source_dataset": "SPAR",
                        "source_item_ids": [adapted.source_item_id],
                        "source_field_paths": ["answer", "image", "qa_type", "red_bbox", "blue_bbox"],
                        "adapter_version": adapter_version,
                        "source_record_hash": adapted.source_record_hash,
                    },
                    "grounding": {
                        "media_ids": [media_id], "archive_members": [image],
                        "bbox_annotation_keys": {"subject_red_bbox": list(red_box), "object_blue_bbox": list(blue_box)},
                        "entity_identity_policy": "EXACT_SAME_IMAGE_PATH_AND_INTEGER_BBOX_ANNOTATION_KEY",
                        "source_media_locator": {
                            "dataset": "jasonzhango/SPAR-7M", "revision": SOURCE_REVISION,
                            "base_dataset": row.get("base_dataset"), "scene_id": row.get("scene_id"),
                            "ordered_frame_paths": [image], "frame_count": 1,
                            "validation_scope": "OFFICIAL_ANNOTATION_PATH_AND_BBOX_REFERENCES_ONLY",
                        },
                        "validation_scope": "OFFICIAL_ANNOTATION_PATH_AND_BBOX_REFERENCES_ONLY",
                    },
                    "observability": "directly_observable", "derivation": None,
                }))
            record_core = {
                "source_item_id": adapted.source_item_id, "source_record_hash": adapted.source_record_hash,
                "facts": canonical_facts, "media": media,
            }
            record_digest = sha256_bytes(json_bytes(record_core)).removeprefix("sha256:")
            record = {
                "record_id": "record:" + record_digest[:24], "schema_version": "1.0",
                "source_dataset": "spar", "source_item_ids": [adapted.source_item_id],
                "global_world_id": world_id, "media": [media], "facts": canonical_facts,
                "source_record_hash": adapted.source_record_hash,
            }
            schema_errors = [error.message for error in canonical_validator.iter_errors(record)]
            if schema_errors:
                reject_counts["CANONICAL_SCHEMA_INVALID"] += 1
                rejects.append({"source_item_id": adapted.source_item_id, "reject_codes": ["CANONICAL_SCHEMA_INVALID"], "schema_errors": schema_errors})
            else:
                records.append(record)

    records.sort(key=lambda row: row["record_id"])
    rejects.sort(key=lambda row: row["source_item_id"])
    canonical_path = root / f"data/canonical/spar/{SOURCE_REVISION}/{canonical_version}/records.jsonl"
    reject_path = root / f"rejected/canonical/spar/{SOURCE_REVISION}/{canonical_version}.jsonl"
    media_path = root / f"data/media_index/spar/{SOURCE_REVISION}/qualitative_relation_bbox_identity.{args.artifact_version}.jsonl"
    write_versioned(canonical_path, jsonl_bytes(records), args.resume)
    write_versioned(reject_path, jsonl_bytes(rejects), args.resume)
    write_versioned(media_path, jsonl_bytes([media_index[key] for key in sorted(media_index)]), args.resume)

    by_world: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_world[record["global_world_id"]].append(record)
    missing_splits = sorted(set(by_world) - set(split_by_world))
    if missing_splits:
        raise ValueError(f"WORLD_SPLIT_MISSING:{missing_splits[:5]}")
    contract = yaml.safe_load((root / "contracts/spar.yaml").read_text())
    allowed_predicates = set(contract["allowed_predicates"])
    authorized_rules = sorted(contract["authorized_rules"])
    graph_validator = _graph_validator(root)
    manifest: list[dict[str, Any]] = []
    graph_reject_counts: Counter[str] = Counter()
    duplicate_facts = 0
    valid_graphs = rejected_graphs = 0
    for world_id, world_records in sorted(by_world.items()):
        media_by_id = {media["media_id"]: media for record in world_records for media in record["media"]}
        facts, merged = _merge_duplicates([fact for record in world_records for fact in record["facts"]])
        duplicate_facts += merged
        node_ids = sorted({value for fact in facts for value in (fact["subject"], fact.get("object")) if isinstance(value, str)})
        graph = {
            "world_graph_id": "world_graph:" + hashlib.sha256(f"{graph_version}\0{world_id}".encode()).hexdigest()[:24],
            "schema_version": "1.0", "global_world_id": world_id, "source_datasets": ["spar"],
            "media": [media_by_id[key] for key in sorted(media_by_id)],
            "nodes": [{"node_id": node, "node_type": _node_type(node)} for node in node_ids],
            "facts": facts, "authorized_rule_ids": authorized_rules,
            "validation_status": "GRAPH_VALID", "reject_codes": [],
        }
        errors = _validation_errors(graph, allowed_predicates, graph_validator)
        graph["validation_status"] = "GRAPH_REJECTED" if errors else "GRAPH_VALID"
        graph["reject_codes"] = errors
        graph_reject_counts.update(errors)
        valid_graphs += int(not errors)
        rejected_graphs += int(bool(errors))
        graph_path = root / ("world_graphs" if not errors else "rejected/graphs") / "spar" / graph_version / _safe_name(world_id)
        graph_payload = json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
        write_versioned(graph_path, graph_payload, args.resume)
        manifest.append({
            "global_world_id": world_id, "split": split_by_world[world_id],
            "validation_status": graph["validation_status"], "graph_path": str(graph_path.relative_to(root)),
            "graph_sha256": sha256_bytes(graph_payload), "record_count": len(world_records), "fact_count": len(facts),
        })
    manifest_path = root / f"world_graphs/manifest.{graph_version}.jsonl"
    write_versioned(manifest_path, jsonl_bytes(manifest), args.resume)
    report = {
        "schema_version": "1.0", "build_version": build_version, "status": "GRAPH_VALID" if valid_graphs and not rejected_graphs else "PARTIAL",
        "run_id": args.run_id, "rows_checked": rows_checked, "single_image_rows": single_image_rows,
        "adapter_accepted_rows": adapter_accepted, "canonical_record_count": len(records),
        "canonical_fact_count": sum(len(record["facts"]) for record in records),
        "fact_predicate_counts": dict(sorted(fact_counts.items())), "media_count": len(media_index),
        "world_count": len(by_world), "graph_valid_count": valid_graphs, "graph_rejected_count": rejected_graphs,
        "semantic_duplicate_fact_merge_count": duplicate_facts,
        "reject_code_counts": dict(sorted((reject_counts + graph_reject_counts).items())),
        "identity_policy": "EXACT_SAME_IMAGE_PATH_AND_INTEGER_BBOX_ANNOTATION_KEY",
        "media_validation_scope": "OFFICIAL_ANNOTATION_PATH_AND_BBOX_REFERENCES_ONLY_NO_LOCAL_PIXEL_BYTES",
        "input_hashes": {
            str(input_path.relative_to(root)) if input_path.is_relative_to(root) else str(input_path): sha256_file(input_path),
            str(scan_report_path.relative_to(root)) if scan_report_path.is_relative_to(root) else str(scan_report_path): sha256_file(scan_report_path),
            str(split_path.relative_to(root)) if split_path.is_relative_to(root) else str(split_path): sha256_file(split_path),
        },
        "output_hashes": {
            str(canonical_path.relative_to(root)): sha256_file(canonical_path),
            str(media_path.relative_to(root)): sha256_file(media_path),
            str(manifest_path.relative_to(root)): sha256_file(manifest_path),
        },
    }
    report_path = root / f"reports/spar/l2_bbox_graph_build.{args.artifact_version}.json"
    write_versioned(report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n", args.resume)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
