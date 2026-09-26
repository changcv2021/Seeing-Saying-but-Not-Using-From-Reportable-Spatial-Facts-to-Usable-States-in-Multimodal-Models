#!/usr/bin/env python3
"""Generate test-only SPAR Unknown claims by decisive-view ablation."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from spaceconflict.generation.verification import independent_label
from spaceconflict.hashing import sha256_bytes, sha256_file
from spaceconflict.unknown.pipeline import _witness_facts


UNKNOWN_VERSION = "unknown_spar_view_ablation_v4"
SOURCE_REVISION = "0fe664cbada1e7c1173fd743e0f781882eebf777"


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.open() if line.strip()]


def write_versioned(path: Path, payload: bytes, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume:
            raise FileExistsError(path)
        if path.read_bytes() != payload:
            raise ValueError(f"NON_DETERMINISTIC_OUTPUT:{path}")
    else:
        path.write_bytes(payload)


def with_unique_local_aliases(claim: dict[str, Any], unknown_id: str) -> dict[str, Any]:
    """Make grounded claim surfaces unique without leaking source or world IDs."""
    claim = json.loads(json.dumps(claim))
    suffix = unknown_id.removeprefix("sc_unknown_")[:6].upper()
    old_aliases = sorted(set(claim.get("entity_aliases", {}).values()), key=len, reverse=True)
    replacements = {alias: f"{alias}-{suffix}" for alias in old_aliases}
    natural_text = claim["natural_text"]
    entity_declaration = claim.get("entity_declaration", "")
    for old, new in replacements.items():
        natural_text = natural_text.replace(old, new)
        entity_declaration = entity_declaration.replace(old, new)
    claim["natural_text"] = natural_text
    claim["entity_declaration"] = entity_declaration
    claim["entity_aliases"] = {
        entity_id: replacements.get(alias, alias)
        for entity_id, alias in claim.get("entity_aliases", {}).items()
    }
    for alignment in claim.get("text_graph_alignment", []):
        surface = replacements.get(alignment["surface_text"], alignment["surface_text"])
        alignment["surface_text"] = surface
        if alignment["slot"] in {"subject_id", "object_id"}:
            start = natural_text.rfind(surface)
        else:
            start = natural_text.find(surface)
        if start < 0:
            raise ValueError(f"REALIASED_ALIGNMENT_SURFACE_MISSING:{unknown_id}:{alignment['slot']}")
        alignment["char_span"] = [start, start + len(surface)]
    return claim


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--l1-proofs", type=Path, required=True)
    parser.add_argument("--l3-proofs", type=Path, required=True)
    parser.add_argument("--l3-ablations", type=Path, required=True)
    parser.add_argument("--media-index", type=Path, required=True)
    parser.add_argument("--target", type=int, default=1177)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    l1_path, l3_path = args.l1_proofs.resolve(), args.l3_proofs.resolve()
    ablation_path, media_path = args.l3_ablations.resolve(), args.media_index.resolve()
    if args.target < 1:
        parser.error("--target must be >= 1")
    validator = Draft202012Validator(json.loads((root / "schemas/unknown_certificate.schema.json").read_text()))
    l1_rows = [row for row in load(l1_path) if row["split"] == "test" and row["status"] == "AUTO_ACCEPTED"]
    l3_rows = [row for row in load(l3_path) if row["split"] == "test" and row["status"] == "AUTO_ACCEPTED"]
    ablations = {row["pair_id"]: row for row in load(ablation_path) if row["status"] == "PASS"}
    media_index = {row["media_id"]: row for row in load(media_path)}

    candidates: list[dict[str, Any]] = []
    # L3 is preferred because it retains two of three views and removes an
    # explicitly required support frame.  Use one ablation per parent and both
    # claim sides, preserving maximum parent-world diversity.
    for row in l3_rows:
        detail = ablations.get(row["pair_id"])
        cases = sorted((detail or {}).get("required_support_view_ablations", []), key=lambda item: item["removed_frame_index"])
        media_id = row["supported_claim"]["normalized"]["context"].get("media_id")
        media_row = media_index.get(media_id)
        frame_paths = (media_row or {}).get("ordered_frame_paths", [])
        case = next(
            (
                item for item in cases
                if len(frame_paths) == 3
                and frame_paths[int(item["removed_frame_index"])] not in {
                    path for index, path in enumerate(frame_paths)
                    if index != int(item["removed_frame_index"])
                }
            ),
            None,
        )
        if case is None:
            continue
        for side in ("supported_claim", "contradictory_claim"):
            candidates.append({"tier": "L3_REQUIRED_SUPPORT_VIEW", "row": row, "side": side, "case": case})
    # L1 retains a same-world distractor/context image while withholding the
    # only decisive image.  This avoids an empty-media Unknown input.
    for row in l1_rows:
        for side in ("supported_claim", "contradictory_claim"):
            candidates.append({"tier": "L1_DECISIVE_IMAGE", "row": row, "side": side, "case": None})
    tier_order = {"L3_REQUIRED_SUPPORT_VIEW": 0, "L1_DECISIVE_IMAGE": 1}
    candidates.sort(key=lambda item: (
        tier_order[item["tier"]],
        hashlib.sha256(f"{args.seed}\0{item['row']['pair_id']}\0{item['side']}".encode()).hexdigest(),
    ))

    accepted: list[dict[str, Any]] = []
    certificate_hashes: dict[str, str] = {}
    reject_counts: Counter[str] = Counter()
    tier_counts: Counter[str] = Counter()
    parent_counts: Counter[str] = Counter()
    for item in candidates:
        row, side, tier = item["row"], item["side"], item["tier"]
        graph = json.loads((root / row["world_graph_path"]).read_text())
        claim = row[side]
        context = claim["normalized"]["context"]
        target_media = next((media for media in graph["media"] if media["media_id"] == context.get("media_id")), None)
        if target_media is None:
            reject_counts["TARGET_MEDIA_MISSING"] += 1
            continue
        authorized = set(graph.get("authorized_rule_ids", []))
        source_references: list[dict[str, Any]] = []
        withheld: dict[str, Any]
        if tier == "L3_REQUIRED_SUPPORT_VIEW":
            source_item_id = row["source_item_ids"][0]
            media_row = media_index.get(target_media["media_id"])
            removed_index = int(item["case"]["removed_frame_index"])
            if media_row is None or len(media_row.get("ordered_frame_paths", [])) != 3:
                reject_counts["ORDERED_MEDIA_INDEX_MISSING"] += 1
                continue
            frame_paths = media_row["ordered_frame_paths"]
            if frame_paths[removed_index] in {
                path for index, path in enumerate(frame_paths) if index != removed_index
            }:
                reject_counts["WITHHELD_VIEW_BYTES_STILL_AVAILABLE"] += 1
                continue
            source_references = [
                {
                    "role": f"frame_{index}", "archive_member": path,
                    "source_revision": SOURCE_REVISION,
                    "validation_scope": "OFFICIAL_ANNOTATION_PATH_AND_BBOX_REFERENCES_ONLY",
                    "source_reference_only": True,
                }
                for index, path in enumerate(frame_paths) if index != removed_index
            ]
            withheld = {
                "role": f"frame_{removed_index}", "archive_member": frame_paths[removed_index],
                "source_revision": SOURCE_REVISION,
                "reason": "REQUIRED_SOURCE_BBOX_GROUNDED_IN_WITHHELD_SUPPORT_VIEW",
            }
            available_facts = [
                fact for fact in graph["facts"]
                if source_item_id not in fact["provenance"]["source_item_ids"]
            ]
        else:
            alternatives = sorted(
                (
                    media for media in graph["media"]
                    if media["media_id"] != target_media["media_id"]
                    and media.get("media_type") == "single_image"
                    and media.get("archive_member", media.get("relative_path"))
                    != target_media.get("archive_member", target_media.get("relative_path"))
                ),
                key=lambda media: media["media_id"],
            )
            if not alternatives:
                reject_counts["SAME_WORLD_CONTEXT_IMAGE_MISSING"] += 1
                continue
            context_media = alternatives[0]
            source_references = [{
                "role": "context_frame_0", "archive_member": context_media.get("archive_member", context_media["relative_path"]),
                "source_revision": context_media["source_revision"],
                "validation_scope": context_media.get("validation_scope"),
                "source_reference_only": context_media.get("source_reference_only", True),
            }]
            withheld = {
                "role": "frame_0", "archive_member": target_media.get("archive_member", target_media["relative_path"]),
                "source_revision": target_media["source_revision"], "reason": "ONLY_DECISIVE_IMAGE_WITHHELD",
            }
            available_facts = [
                fact for fact in graph["facts"]
                if fact["context"].get("media_id") == context_media["media_id"]
            ]
        result = independent_label(
            candidate=claim, entity_graph=claim["normalized"], world_facts=available_facts,
            authorized_rule_ids=authorized,
        )
        if result["label"] != "UNKNOWN" or result["co_truth_possible"]:
            reject_counts["UNKNOWN_SAT_CHECK_FAILED"] += 1
            continue
        atom = claim["normalized"]["atoms"][0]
        positive, negative = _witness_facts(atom, context)
        positive_result = independent_label(
            candidate=claim, entity_graph=claim["normalized"], world_facts=[*available_facts, positive],
            authorized_rule_ids=authorized,
        )
        negative_result = independent_label(
            candidate=claim, entity_graph=claim["normalized"], world_facts=[*available_facts, negative],
            authorized_rule_ids=authorized,
        )
        if positive_result["label"] != "SUPPORTED" or negative_result["label"] != "CONTRADICTORY":
            reject_counts["UNKNOWN_WITNESS_REPLAY_FAILED"] += 1
            continue
        unknown_id = "sc_unknown_" + hashlib.sha256(
            f"{UNKNOWN_VERSION}\0{row['pair_id']}\0{side}\0{withheld['role']}".encode()
        ).hexdigest()[:24]
        available_roles = [reference["role"] for reference in source_references]
        certificate = {
            "certificate_id": f"{unknown_id}:certificate", "label": "UNKNOWN",
            "unknown_reason": "MISSING_VIEW", "available_evidence_ids": available_roles,
            "missing_decisive_evidence": [withheld["role"]],
            "satisfiable_with_claim": True, "satisfiable_with_negation": True,
            "witness_completion_positive": positive, "witness_completion_negative": negative,
            "resolving_evidence_type": "REQUIRED_VIEW",
            "forbidden_inference": "remaining or context views do not entail the relation grounded in the withheld decisive view",
            "would_be_level_if_resolved": row["level"], "parent_pair_id": row["pair_id"],
            "source_world_graph_hash": row["world_graph_hash"], "ablation_tier": tier,
            "verification": {
                "ablated_label": result["label"], "positive_witness_label": positive_result["label"],
                "negative_witness_label": negative_result["label"],
            },
        }
        errors = list(validator.iter_errors(certificate))
        if errors:
            raise ValueError(f"UNKNOWN_CERTIFICATE_SCHEMA_INVALID:{unknown_id}:{errors[0].message}")
        certificate_path = root / "certificates/unknown" / UNKNOWN_VERSION / f"{unknown_id}.json"
        certificate_payload = json.dumps(certificate, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
        write_versioned(certificate_path, certificate_payload, args.resume)
        certificate_hashes[str(certificate_path.relative_to(root))] = sha256_bytes(certificate_payload)
        release_claim = with_unique_local_aliases(claim, unknown_id)
        accepted.append({
            "unknown_id": unknown_id, "schema_version": "1.0", "parent_pair_id": row["pair_id"],
            "global_world_id": row["global_world_id"], "split": "test", "source_dataset": "spar",
            "source_item_ids": row["source_item_ids"],
            "media": {
                "media_type": "multi_view_images" if tier.startswith("L3") else "single_image_context",
                "source_references": source_references, "withheld_evidence": withheld,
            },
            "claim": release_claim, "label": "UNKNOWN", "unknown_reason": "MISSING_VIEW",
            "certificate_path": str(certificate_path.relative_to(root)),
            "certificate_sha256": sha256_bytes(certificate_payload), "status": "AUTO_ACCEPTED_UNKNOWN",
            "ablation_tier": tier,
        })
        tier_counts[tier] += 1
        parent_counts[row["pair_id"]] += 1
        if len(accepted) >= args.target:
            break

    output_path = root / "candidates/unknown" / f"claims.{UNKNOWN_VERSION}.jsonl"
    payload = b"".join(compact(row) + b"\n" for row in accepted)
    write_versioned(output_path, payload, args.resume)
    report = {
        "schema_version": "1.0", "unknown_version": UNKNOWN_VERSION,
        "status": "UNKNOWN_VALID" if len(accepted) == args.target else "UNKNOWN_SHORTFALL",
        "run_id": args.run_id, "target_claim_count": args.target,
        "eligible_l3_test_parent_count": len(l3_rows), "eligible_l1_test_parent_count": len(l1_rows),
        "candidate_count": len(candidates), "auto_accepted_unknown_count": len(accepted),
        "unique_parent_pair_count": len(parent_counts), "max_unknown_per_parent": max(parent_counts.values(), default=0),
        "ablation_tier_counts": dict(sorted(tier_counts.items())),
        "rejected_count": sum(reject_counts.values()), "reject_code_counts": dict(sorted(reject_counts.items())),
        "evidence_ablation_count": len(accepted), "evidence_ablation_ratio": 1.0 if accepted else 0.0,
        "positive_witness_pass_rate": 1.0 if accepted else 0.0,
        "negative_witness_pass_rate": 1.0 if accepted else 0.0,
        "split_counts": {"test": len(accepted)},
        "unique_natural_text_count": len({row["claim"]["natural_text"] for row in accepted}),
        "media_validation_scope": "OFFICIAL_ANNOTATION_PATH_AND_BBOX_REFERENCES_ONLY_NO_LOCAL_PIXEL_BYTES",
        "input_hashes": {
            str(l1_path.relative_to(root)): sha256_file(l1_path), str(l3_path.relative_to(root)): sha256_file(l3_path),
            str(ablation_path.relative_to(root)): sha256_file(ablation_path), str(media_path.relative_to(root)): sha256_file(media_path),
        },
        "output_hashes": {str(output_path.relative_to(root)): sha256_bytes(payload), **dict(sorted(certificate_hashes.items()))},
        "quality_policy": "TEST_ONLY_DECISIVE_VIEW_ABLATION_WITH_POSITIVE_AND_NEGATIVE_WITNESS_REPLAY",
        "next_gate": "UNKNOWN_EXPORT_ALLOWED" if len(accepted) == args.target else "UNKNOWN_EVIDENCE_SOURCE_EXPANSION_REQUIRED",
    }
    report_path = root / f"reports/unknown_generation.{UNKNOWN_VERSION}.json"
    write_versioned(report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n", args.resume)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "UNKNOWN_VALID" else 2


if __name__ == "__main__":
    raise SystemExit(main())
