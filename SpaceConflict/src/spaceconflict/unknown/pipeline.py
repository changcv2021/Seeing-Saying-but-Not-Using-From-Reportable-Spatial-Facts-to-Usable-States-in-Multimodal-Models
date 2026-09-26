from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from ..generation.verification import PROOF_VERIFICATION_VERSION, independent_label
from ..hashing import sha256_bytes, sha256_file
from ..registry import ROOT


UNKNOWN_VERSION = "unknown_p1_v2"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write(path: Path, payload: bytes, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume:
            raise FileExistsError(f"Output exists: {path}; use --resume")
        if path.read_bytes() != payload:
            raise ValueError(f"Non-deterministic output: {path}")
    else:
        path.write_bytes(payload)


def _witness_facts(atom: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    positive = {
        "fact_id": "witness:positive", "subject": atom["subject"], "predicate": atom["predicate"],
        "object": atom.get("object"), "value": atom.get("value"), "polarity": "positive",
        "context": context,
    }
    negative = {**positive, "fact_id": "witness:negative"}
    if atom["predicate"] == "VISIBLE_IN_FRAME":
        negative["polarity"] = "negative"
    elif atom["predicate"] == "COUNT":
        negative["value"] = int(atom["value"]) + 1
    else:
        negative["subject"], negative["object"] = atom.get("object"), atom["subject"]
    return positive, negative


def generate_unknown(
    *, config: Path, dry_run: bool, resume: bool, seed: int, limit: int | None,
    root: Path = ROOT,
) -> dict[str, Any]:
    policy = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    proof_version = str(policy.get("proof_verification_version", PROOF_VERIFICATION_VERSION))
    unknown_version = str(policy.get("unknown_version", UNKNOWN_VERSION))
    for value in (proof_version, unknown_version):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
            raise ValueError(f"UNSAFE_PIPELINE_VERSION:{value}")
    source_path = root / "candidates/auto_accepted" / f"pairs.{proof_version}.jsonl"
    output_path = root / "candidates/unknown" / f"claims.{unknown_version}.jsonl"
    certificate_dir = root / "certificates/unknown" / unknown_version
    report_path = root / "reports" / f"unknown_generation.{unknown_version}.json"
    if dry_run:
        return {"status": "PLANNED", "input": str(source_path.relative_to(root)), "output": str(output_path.relative_to(root)), "config": str(config)}
    if not source_path.exists():
        return {"status": "BLOCKED_SOURCE", "reason": "AUTO_ACCEPTED_PAIRS_MISSING"}
    target = int(policy.get("target_claims", 2000))
    if limit is not None:
        target = min(target, limit)
    validator = Draft202012Validator(json.loads((root / "schemas/unknown_certificate.schema.json").read_text(encoding="utf-8")))
    rows = [
        row for row in _load_jsonl(source_path)
        if row["source_dataset"] == "ca_vqa" and row["split"] == "test"
    ]
    rows.sort(key=lambda row: (
        hashlib.sha256(f"{seed}\0{row['pair_id']}".encode("utf-8")).hexdigest(), row["pair_id"],
    ))
    accepted: list[dict[str, Any]] = []
    certificate_hashes: dict[str, str] = {}
    reject_counts: dict[str, int] = {}
    for ordinal, row in enumerate(rows):
        graph = json.loads((root / row["world_graph_path"]).read_text(encoding="utf-8"))
        side = "supported_claim" if ordinal % 2 == 0 else "contradictory_claim"
        claim = row[side]
        context = claim["normalized"]["context"]
        target_media = next((media for media in graph["media"] if media["media_id"] == context.get("media_id")), None)
        if target_media is None or len(target_media.get("support_frames", [])) != 4 or not target_media.get("reference_frame"):
            reject_counts["MISSING_REFERENCE_SUPPORT_FRAME_ROLES"] = reject_counts.get("MISSING_REFERENCE_SUPPORT_FRAME_ROLES", 0) + 1
            continue
        available_facts = [fact for fact in graph["facts"] if fact["context"].get("media_id") != target_media["media_id"]]
        unknown_result = independent_label(candidate=claim, entity_graph=claim["normalized"], world_facts=available_facts)
        if unknown_result["label"] != "UNKNOWN" or unknown_result["co_truth_possible"]:
            reject_counts["UNKNOWN_SAT_CHECK_FAILED"] = reject_counts.get("UNKNOWN_SAT_CHECK_FAILED", 0) + 1
            continue
        atom = claim["normalized"]["atoms"][0]
        witness_positive, witness_negative = _witness_facts(atom, context)
        positive_result = independent_label(
            candidate=claim, entity_graph=claim["normalized"], world_facts=[*available_facts, witness_positive],
        )
        negative_result = independent_label(
            candidate=claim, entity_graph=claim["normalized"], world_facts=[*available_facts, witness_negative],
        )
        if positive_result["label"] != "SUPPORTED" or negative_result["label"] != "CONTRADICTORY":
            reject_counts["UNKNOWN_WITNESS_REPLAY_FAILED"] = reject_counts.get("UNKNOWN_WITNESS_REPLAY_FAILED", 0) + 1
            continue
        unknown_id = "sc_unknown_" + hashlib.sha256(
            f"{unknown_version}\0{row['pair_id']}\0{side}".encode("utf-8")
        ).hexdigest()[:24]
        certificate = {
            "certificate_id": f"{unknown_id}:certificate", "label": "UNKNOWN",
            "unknown_reason": "MISSING_VIEW",
            "available_evidence_ids": [f"support_frame_{index}" for index in range(1, 5)],
            "missing_decisive_evidence": ["reference_frame"],
            "satisfiable_with_claim": True, "satisfiable_with_negation": True,
            "witness_completion_positive": witness_positive,
            "witness_completion_negative": witness_negative,
            "resolving_evidence_type": "REFERENCE_FRAME",
            "forbidden_inference": "support-frame content does not determine the withheld reference-frame fact",
            "would_be_level_if_resolved": row["level"],
            "parent_pair_id": row["pair_id"], "source_world_graph_hash": row["world_graph_hash"],
            "verification": {
                "ablated_label": unknown_result["label"],
                "positive_witness_label": positive_result["label"],
                "negative_witness_label": negative_result["label"],
            },
        }
        errors = list(validator.iter_errors(certificate))
        if errors:
            raise ValueError(f"UNKNOWN_CERTIFICATE_SCHEMA_INVALID:{unknown_id}:{errors[0].message}")
        certificate_path = certificate_dir / f"{unknown_id}.json"
        certificate_payload = json.dumps(certificate, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        _write(certificate_path, certificate_payload, resume)
        certificate_hashes[str(certificate_path.relative_to(root))] = sha256_bytes(certificate_payload)
        support_references = [
            {
                "role": f"support_frame_{index}", "archive_member": archive_member,
                "source_revision": target_media["source_revision"],
            }
            for index, archive_member in enumerate(target_media["support_frames"], start=1)
        ]
        accepted.append({
            "unknown_id": unknown_id, "schema_version": "1.0", "parent_pair_id": row["pair_id"],
            "global_world_id": row["global_world_id"], "split": "test", "source_dataset": "ca_vqa",
            "source_item_ids": row["source_item_ids"],
            "media": {
                "media_type": "multi_view_images", "source_references": support_references,
                "withheld_evidence": {"role": "reference_frame", "archive_member": target_media["reference_frame"]},
            },
            "claim": claim, "label": "UNKNOWN", "unknown_reason": "MISSING_VIEW",
            "certificate_path": str(certificate_path.relative_to(root)),
            "certificate_sha256": sha256_bytes(certificate_payload), "status": "AUTO_ACCEPTED_UNKNOWN",
        })
        if len(accepted) >= target:
            break
    payload = b"".join(_json_bytes(row) + b"\n" for row in accepted)
    _write(output_path, payload, resume)
    status = "UNKNOWN_VALID" if len(accepted) >= target else "UNKNOWN_SHORTFALL"
    report = {
        "schema_version": "1.0", "unknown_version": unknown_version, "status": status,
        **({"proof_verification_version": proof_version} if "proof_verification_version" in policy else {}),
        "target_claim_count": target, "eligible_parent_pair_count": len(rows),
        "auto_accepted_unknown_count": len(accepted), "rejected_count": sum(reject_counts.values()),
        "reject_code_counts": dict(sorted(reject_counts.items())),
        "evidence_ablation_count": len(accepted),
        "evidence_ablation_ratio": 1.0 if accepted else 0.0,
        "positive_witness_pass_rate": 1.0 if accepted else 0.0,
        "negative_witness_pass_rate": 1.0 if accepted else 0.0,
        "input_hashes": {str(source_path.relative_to(root)): sha256_file(source_path), str(config): sha256_file(config)},
        "output_hashes": {str(output_path.relative_to(root)): sha256_bytes(payload), **dict(sorted(certificate_hashes.items()))},
        "quality_policy": "SHORTFALL_REPORTED_NEVER_FILLED_WITH_UNPROVED_UNKNOWN",
        "next_gate": "UNKNOWN_EXPORT_ALLOWED" if accepted else "UNKNOWN_EVIDENCE_SOURCE_MISSING",
    }
    _write(report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n", resume)
    return report
