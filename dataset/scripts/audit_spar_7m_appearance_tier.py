#!/usr/bin/env python3
"""Audit SPAR appearance-order proofs and enforce their auxiliary-track boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from spaceconflict.generation.verification import independent_label
from spaceconflict.hashing import sha256_bytes, sha256_file


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--proofs", type=Path, required=True)
    parser.add_argument("--media-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--details", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    root, proofs_path = args.root.resolve(), args.proofs.resolve()
    media_index_path = args.media_index.resolve()
    output_path, details_path = args.output.resolve(), args.details.resolve()
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "proofs": str(proofs_path), "limit": args.limit}))
        return 0
    proofs = load_jsonl(proofs_path)
    if args.limit is not None:
        proofs = proofs[:args.limit]
    media_index = {row["media_id"]: row for row in load_jsonl(media_index_path)}
    registry = yaml.safe_load((root / "datasets.yaml").read_text(encoding="utf-8"))
    planned_tracks = set(registry["datasets"]["spar"]["planned_tracks"])
    rows: list[dict[str, Any]] = []
    failures: Counter[str] = Counter()
    for pair in proofs:
        graph = json.loads((root / pair["world_graph_path"]).read_text(encoding="utf-8"))
        evidence = json.loads((root / pair["evidence_subgraph_path"]).read_text(encoding="utf-8"))
        media_ids = set(evidence["media_ids"])
        referenced_media = [media for media in graph["media"] if media["media_id"] in media_ids]
        checks = {
            "proof_level_l3": pair["level"] == "L3",
            "operator_appearance_order": pair["operator_id"] == "APPEARANCE_ORDER_ERROR",
            "media_present": bool(referenced_media),
            "ordered_multi_frame": bool(referenced_media) and all(
                media["media_type"] == "ordered_multi_frame" for media in referenced_media
            ),
            "source_reference_only_disclosed": bool(referenced_media) and all(
                media.get("source_reference_only") is True
                and media.get("local_media_byte_validation") == "NOT_PERFORMED_UNDERLYING_MEDIA_NOT_PRESENT"
                for media in referenced_media
            ),
            "media_manifest_resolves": all(media["media_id"] in media_index for media in referenced_media),
            "frame_count_consistent": all(
                media["ordered_frame_count"] == media_index[media["media_id"]]["frame_count"]
                for media in referenced_media if media["media_id"] in media_index
            ),
        }
        ablated_facts = [
            fact for fact in graph["facts"]
            if not (set(fact["grounding"].get("media_ids", [])) & media_ids)
        ]
        authorized = set(graph.get("authorized_rule_ids", []))
        ablation_labels = {
            side: independent_label(
                candidate=pair[f"{side}_claim"],
                entity_graph=pair[f"{side}_claim"]["normalized"],
                world_facts=ablated_facts, authorized_rule_ids=authorized,
            )["label"]
            for side in ("supported", "contradictory")
        }
        checks["bundle_media_ablation_unknown"] = set(ablation_labels.values()) == {"UNKNOWN"}
        for name, passed in checks.items():
            if not passed:
                failures[name] += 1
        rows.append({
            "pair_id": pair["pair_id"], "checks": checks,
            "bundle_media_ablation_labels": ablation_labels,
            "frame_specific_ablation": "NOT_TESTABLE_SOURCE_ANNOTATION_HAS_NO_OBJECT_TO_FRAME_BINDING",
            "core_track_status": (
                "CORE_TRACK_ALLOWED" if pair["primary_track"] in planned_tracks
                else "AUXILIARY_EXCLUDED_PRIMARY_TRACK_NOT_PLANNED_FOR_SPAR"
            ),
        })
    detail_payload = b"".join(json_bytes(row) + b"\n" for row in rows)
    write_versioned(details_path, detail_payload, args.resume)
    auxiliary_count = sum(row["core_track_status"].startswith("AUXILIARY_") for row in rows)
    report = {
        "schema_version": "1.0", "audit_version": "spar_7m_appearance_tier_v1",
        "status": (
            "AUXILIARY_PROOF_VALID_CORE_TRACK_BLOCKED"
            if rows and not failures and auxiliary_count == len(rows) else "FAIL"
        ),
        "pair_count": len(rows), "check_failure_counts": dict(sorted(failures.items())),
        "bundle_media_ablation_pass_count": sum(
            row["checks"]["bundle_media_ablation_unknown"] for row in rows
        ),
        "frame_specific_ablation_status": "NOT_TESTABLE_SOURCE_ANNOTATION_HAS_NO_OBJECT_TO_FRAME_BINDING",
        "planned_spar_tracks": sorted(planned_tracks),
        "observed_primary_track_counts": dict(sorted(Counter(row["primary_track"] for row in proofs).items())),
        "auxiliary_excluded_pair_count": auxiliary_count,
        "core_release_eligible_pair_count": len(rows) - auxiliary_count,
        "media_validation_scope": "OFFICIAL_ANNOTATION_PATH_REFERENCES_ONLY_NO_LOCAL_PIXEL_DECODE",
        "input_hashes": {
            str(proofs_path.relative_to(root)): sha256_file(proofs_path),
            str(media_index_path.relative_to(root)): sha256_file(media_index_path),
        },
        "output_hashes": {str(details_path.relative_to(root)): sha256_bytes(detail_payload)},
        "next_gate": "KEEP_AUXILIARY_SEPARATE_AND_BUILD_PLANNED_SPAR_RELATION_TRACKS",
    }
    write_versioned(
        output_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n",
        args.resume,
    )
    print(json.dumps({
        key: report[key] for key in (
            "status", "pair_count", "bundle_media_ablation_pass_count",
            "auxiliary_excluded_pair_count", "core_release_eligible_pair_count", "next_gate",
        )
    }, sort_keys=True))
    return 0 if report["status"] == "AUXILIARY_PROOF_VALID_CORE_TRACK_BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())

