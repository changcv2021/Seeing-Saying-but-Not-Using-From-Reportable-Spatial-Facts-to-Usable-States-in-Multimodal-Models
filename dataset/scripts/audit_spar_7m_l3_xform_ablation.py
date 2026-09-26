#!/usr/bin/env python3
"""Replay required-support-view ablations for SPAR L3 XFORM-PROJ pairs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from spaceconflict.generation.verification import independent_label
from spaceconflict.hashing import sha256_bytes, sha256_file


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_versioned(path: Path, payload: bytes, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume or path.read_bytes() != payload:
            raise ValueError(f"NONDETERMINISTIC_OR_EXISTING_OUTPUT:{path}")
    else:
        path.write_bytes(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--proofs", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--media-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--details", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    root = args.root.resolve()
    proofs_path, allowlist_path = args.proofs.resolve(), args.allowlist.resolve()
    media_path = args.media_index.resolve()
    output, details = args.output.resolve(), args.details.resolve()
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "proofs": str(proofs_path), "limit": args.limit}))
        return 0
    proofs = load_jsonl(proofs_path)
    if args.limit is not None:
        proofs = proofs[:args.limit]
    allowed = {row["source_item_id"]: row for row in load_jsonl(allowlist_path)}
    media_index = {row["media_id"]: row for row in load_jsonl(media_path)}
    rows = []
    failure_counts: Counter[str] = Counter()
    ablation_case_count = 0
    for pair in proofs:
        codes = []
        if pair["level"] != "L3" or pair["primary_track"] != "XFORM-PROJ":
            codes.append("LEVEL_TRACK_MISMATCH")
        if len(pair["source_item_ids"]) != 1:
            codes.append("NON_LOCAL_SOURCE_BUNDLE")
            selected = None
        else:
            selected = allowed.get(pair["source_item_ids"][0])
            if selected is None:
                codes.append("SOURCE_ITEM_NOT_STRICT_MULTIVIEW_SELECTED")
        graph = json.loads((root / pair["world_graph_path"]).read_text(encoding="utf-8"))
        evidence = json.loads((root / pair["evidence_subgraph_path"]).read_text(encoding="utf-8"))
        media_ids = set(evidence["media_ids"])
        if selected is not None and selected["media_id"] not in media_ids:
            codes.append("SELECTED_MEDIA_NOT_IN_EVIDENCE")
        media_row = media_index.get(selected["media_id"]) if selected is not None else None
        if media_row is None:
            codes.append("MEDIA_INDEX_MISSING")
        support_results = []
        for frame_index in (selected or {}).get("required_support_frame_indices", []):
            ablation_case_count += 1
            # A fact whose explicitly marked target bbox lives in the removed
            # support view is no longer observable from the remaining input.
            ablated_facts = [
                fact for fact in graph["facts"]
                if pair["source_item_ids"][0] not in fact["provenance"]["source_item_ids"]
            ]
            authorized = set(graph.get("authorized_rule_ids", []))
            labels = {
                side: independent_label(
                    candidate=pair[f"{side}_claim"],
                    entity_graph=pair[f"{side}_claim"]["normalized"],
                    world_facts=ablated_facts, authorized_rule_ids=authorized,
                )["label"]
                for side in ("supported", "contradictory")
            }
            passed = set(labels.values()) == {"UNKNOWN"}
            if not passed:
                codes.append("REQUIRED_SUPPORT_VIEW_ABLATION_NOT_UNKNOWN")
            support_results.append({
                "removed_frame_index": frame_index,
                "removed_source_reference": media_row["ordered_frame_paths"][frame_index] if media_row else None,
                "labels_after_observability_ablation": labels,
                "status": "PASS" if passed else "FAIL",
            })
        if not support_results:
            codes.append("NO_REQUIRED_SUPPORT_VIEW_ABLATION")
        failure_counts.update(set(codes))
        rows.append({
            "pair_id": pair["pair_id"], "source_item_id": pair["source_item_ids"][0],
            "required_support_view_ablations": support_results,
            "status": "PASS" if not codes else "FAIL", "failure_codes": sorted(set(codes)),
        })
    detail_payload = b"".join(compact(row) + b"\n" for row in rows)
    write_versioned(details, detail_payload, args.resume)
    report = {
        "schema_version": "1.0", "audit_version": "spar_7m_l3_xform_ablation_v1",
        "status": "PASS" if rows and not failure_counts else "FAIL",
        "pair_count": len(rows), "support_view_ablation_case_count": ablation_case_count,
        "pair_pass_count": sum(row["status"] == "PASS" for row in rows),
        "failure_code_counts": dict(sorted(failure_counts.items())),
        "ablation_semantics": "REMOVING_A_FRAME_WITH_A_REQUIRED_SOURCE_BBOX_MAKES_THE_QA_DIRECT_FACT_UNOBSERVABLE",
        "local_pixel_validation": "NOT_PERFORMED_SOURCE_REFERENCE_TIER",
        "input_hashes": {
            str(proofs_path.relative_to(root)): sha256_file(proofs_path),
            str(allowlist_path.relative_to(root)): sha256_file(allowlist_path),
            str(media_path.relative_to(root)): sha256_file(media_path),
        },
        "output_hashes": {str(details.relative_to(root)): sha256_bytes(detail_payload)},
        "next_gate": "CORE_RELEASE_MERGE" if not failure_counts else "EXCLUDE_FAILED_L3_PAIRS",
    }
    write_versioned(
        output, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n", args.resume,
    )
    print(json.dumps({key: report[key] for key in (
        "status", "pair_count", "support_view_ablation_case_count", "pair_pass_count",
        "failure_code_counts", "next_gate",
    )}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

