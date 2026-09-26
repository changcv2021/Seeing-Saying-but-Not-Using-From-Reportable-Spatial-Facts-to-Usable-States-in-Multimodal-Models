from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .adapters.pipeline import ADAPTER_VERSIONS
from .hashing import sha256_bytes, sha256_file
from .profiling.profile import REVISIONS
from .registry import ROOT, load_json


CANONICAL_VERSION = "canonical_v4"
CONTEXT_KEYS = {
    "world_id", "media_id", "view_id", "frame_id", "time_scope",
    "reference_frame", "state_id", "branch_id", "scope",
}


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(_json_bytes(row) + b"\n" for row in rows)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _validator(root: Path) -> Draft202012Validator:
    record_schema = copy.deepcopy(load_json(root / "schemas/canonical_record.schema.json"))
    record_schema["properties"]["facts"]["items"] = load_json(
        root / "schemas/canonical_fact.schema.json"
    )
    return Draft202012Validator(record_schema)


def _select_media_report(dataset: str, media_run_id: str | None, root: Path) -> tuple[Path, dict[str, Any]]:
    report_dir = root / "reports" / dataset
    if media_run_id:
        paths = [report_dir / f"media_validation.{media_run_id}.json"]
    else:
        paths = sorted(report_dir.glob("media_validation.*.json"), reverse=True)
    for path in paths:
        if not path.exists():
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("status") == "PILOT_MEDIA_VALID":
            return path, report
    requested = media_run_id or "latest PILOT_MEDIA_VALID report"
    raise FileNotFoundError(f"No valid media report for {dataset}: {requested}")


def _media(dataset: str, mapping: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    if dataset == "ca_vqa":
        roles = mapping["frame_roles"]
        archive_members = {role: f"cavqa_val/{path}" for role, path in roles.items()}
        identity = json.dumps(archive_members, sort_keys=True, separators=(",", ":"))
        media_id = "media:" + hashlib.sha256(
            f"{dataset}\0{report['source_revision']}\0cavqa_val.tar.gz\0{identity}".encode("utf-8")
        ).hexdigest()[:24]
        return {
            "media_id": media_id,
            "media_type": "multi_view_images",
            "relative_path": f"cavqa_val.tar.gz#{archive_members['reference_frame']}",
            "source_revision": report["source_revision"],
            "archive_member": archive_members["reference_frame"],
            "reference_frame": archive_members["reference_frame"],
            "support_frames": [archive_members[f"support_frame_{index}"] for index in range(1, 5)],
            "frame_roles": archive_members,
            "validation_scope": mapping["validation_scope"],
        }
    if dataset == "hypo3d":
        roles = mapping["media_roles"]
        primary = roles["camera_view"]
        identity = json.dumps(roles, sort_keys=True, separators=(",", ":"))
        media_id = "media:" + hashlib.sha256(
            f"{dataset}\0{report['source_revision']}\0{identity}".encode("utf-8")
        ).hexdigest()[:24]
        return {
            "media_id": media_id,
            "media_type": "multi_view_images",
            "relative_path": primary,
            "source_revision": report["source_revision"],
            "archive_member": primary,
            "reference_frame": primary,
            "support_frames": [path for role, path in sorted(roles.items()) if role != "camera_view"],
            "frame_roles": roles,
            "validation_scope": mapping["validation_scope"],
        }
    archive_member = str(
        mapping.get("archive_member")
        or f"SPAR-Bench/data#row={mapping.get('full_benchmark_row_id')}"
    )
    if dataset == "sti_bench":
        archive = "video.zip"
    elif dataset == "vsi_bench":
        archive = str(mapping["media_locator"]["archive"])
    elif dataset == "omnispatial":
        archive = "OmniSpatial-full.zip"
    else:
        archive = "SPAR-Bench/data/*.parquet"
    media_id = "media:" + hashlib.sha256(
        f"{dataset}\0{report['source_revision']}\0{archive}\0{archive_member}".encode("utf-8")
    ).hexdigest()[:24]
    return {
        "media_id": media_id,
        "media_type": "multi_view_images" if dataset == "spar" else mapping.get("media_type", "video"),
        "relative_path": f"{archive}#{archive_member}",
        "source_revision": report["source_revision"],
        "archive_member": archive_member,
        "validation_scope": "decoded_pilot" if mapping.get("selected_for_pilot") else "archive_index",
    }


def _canonical_fact(
    candidate_fact: dict[str, Any], candidate: dict[str, Any], media: dict[str, Any],
) -> dict[str, Any]:
    source_context = candidate_fact["context"]
    resolved_world_id = candidate.get("resolved_global_world_id") or candidate["global_world_id"]
    context = {key: value for key, value in source_context.items() if key in CONTEXT_KEYS}
    context["world_id"] = resolved_world_id
    context["media_id"] = media["media_id"]
    grounding = {
        "media_ids": [media["media_id"]],
        "archive_members": [media["archive_member"]],
        "source_media_locator": candidate["media_locator"],
        "validation_scope": media["validation_scope"],
    }
    if candidate["source_dataset"] in {"ca_vqa", "hypo3d"}:
        grounding["frame_roles"] = media["frame_roles"]
        grounding["reference_frame"] = media["reference_frame"]
        grounding["support_frames"] = media["support_frames"]
    context_extras = {
        key: value for key, value in source_context.items() if key not in CONTEXT_KEYS
    }
    if context_extras:
        grounding["source_context_extensions"] = context_extras
    provenance = copy.deepcopy(candidate_fact["provenance"])
    provenance["adapter_version"] = candidate["adapter_version"]
    core = {
        key: copy.deepcopy(value)
        for key, value in candidate_fact.items()
        if key in {"subject", "predicate", "object", "value", "polarity", "quantifier"}
    }
    local_suffix = hashlib.sha256(candidate["source_item_id"].encode("utf-8")).hexdigest()[:12]
    for slot in ("subject", "object"):
        value = core.get(slot)
        if isinstance(value, str) and value.startswith(("mention:", "first_appear:")):
            core[slot] = f"{value}@source_item:{local_suffix}"
            grounding["entity_identity_policy"] = "SOURCE_ITEM_LOCAL_NO_OFFICIAL_INSTANCE_ID"
    core.update({
        "context": context,
        "provenance": provenance,
        "grounding": grounding,
        "observability": "directly_observable",
        "derivation": None,
    })
    fact_hash = sha256_bytes(_json_bytes(core))
    core["fact_id"] = f"fact:{fact_hash.removeprefix('sha256:')[:24]}"
    core["canonical_fact_hash"] = fact_hash
    return core


def promote_candidates(
    dataset: str, *, dry_run: bool, resume: bool, media_run_id: str | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    if dataset not in ADAPTER_VERSIONS:
        return {"dataset": dataset, "status": "BLOCKED_SOURCE", "reason": "NO_DETERMINISTIC_ADAPTER"}
    revision = REVISIONS[dataset]
    adapter_version = ADAPTER_VERSIONS[dataset]
    candidate_path = (
        root / "data/staging/adapters" / dataset / revision / adapter_version / "fact_candidates.jsonl"
    )
    output_dir = root / "data/canonical" / dataset / revision / CANONICAL_VERSION
    records_path = output_dir / "records.jsonl"
    reject_path = root / "rejected/canonical" / dataset / revision / f"{CANONICAL_VERSION}.jsonl"
    report_path = root / "reports" / dataset / f"canonical_promotion.{CANONICAL_VERSION}.json"
    if dry_run:
        return {
            "dataset": dataset, "status": "PLANNED", "candidate_input": str(candidate_path.relative_to(root)),
            "canonical_output": str(records_path.relative_to(root)), "media_run_id": media_run_id or "auto",
        }
    if not candidate_path.exists():
        return {"dataset": dataset, "status": "BLOCKED_SOURCE", "reason": "ADAPTER_OUTPUT_MISSING"}
    try:
        media_report_path, media_report = _select_media_report(dataset, media_run_id, root)
    except FileNotFoundError as error:
        return {"dataset": dataset, "status": "BLOCKED_SOURCE", "reason": "PILOT_MEDIA_NOT_VALID", "detail": str(error)}
    if dataset == "spar" and media_report.get("next_gate") != "WORLD_ID_VALID":
        return {
            "dataset": dataset, "status": "BLOCKED_SOURCE",
            "reason": "UNRESOLVED_WORLD_ID",
            "media_validation_report": str(media_report_path.relative_to(root)),
        }
    mapping_path = root / media_report["outputs"]["mapping"]
    mappings = {row["source_item_id"]: row for row in _load_jsonl(mapping_path)}
    candidates = _load_jsonl(candidate_path)
    records: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    validator = _validator(root)
    for candidate in candidates:
        mapping = mappings.get(candidate["source_item_id"])
        reject_codes: list[str] = []
        if mapping is None:
            reject_codes.append("MISSING_MEDIA_MAPPING")
        elif mapping.get("status") != "VALID":
            reject_codes.extend(mapping.get("reject_codes") or ["MEDIA_MAPPING_REJECTED"])
        if reject_codes:
            rejects.append({
                "source_item_id": candidate["source_item_id"],
                "source_record_hash": candidate["source_record_hash"],
                "reject_codes": sorted(set(reject_codes)),
            })
            continue
        media = _media(dataset, mapping, media_report)
        resolved_world_id = mapping.get("resolved_global_world_id") or candidate["global_world_id"]
        promoted_candidate = {**candidate, "resolved_global_world_id": resolved_world_id}
        facts = [_canonical_fact(fact, promoted_candidate, media) for fact in candidate["facts"]]
        record_hash = sha256_bytes(_json_bytes({
            "dataset": dataset,
            "source_item_id": candidate["source_item_id"],
            "source_record_hash": candidate["source_record_hash"],
            "facts": facts,
            "media": media,
        }))
        record = {
            "record_id": f"record:{record_hash.removeprefix('sha256:')[:24]}",
            "schema_version": "1.0",
            "source_dataset": dataset,
            "source_item_ids": [candidate["source_item_id"]],
            "global_world_id": resolved_world_id,
            "media": [media],
            "facts": facts,
            "source_record_hash": candidate["source_record_hash"],
        }
        errors = sorted(validator.iter_errors(record), key=lambda error: list(error.path))
        if errors:
            rejects.append({
                "source_item_id": candidate["source_item_id"],
                "source_record_hash": candidate["source_record_hash"],
                "reject_codes": ["CANONICAL_SCHEMA_INVALID"],
                "schema_errors": [error.message for error in errors],
            })
            continue
        records.append(record)
    records.sort(key=lambda row: row["record_id"])
    rejects.sort(key=lambda row: row["source_item_id"])
    records_payload = _jsonl_bytes(records)
    rejects_payload = _jsonl_bytes(rejects)
    for path, payload in ((records_path, records_payload), (reject_path, rejects_payload)):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if not resume:
                raise FileExistsError(f"Output exists: {path}; use --resume")
            if path.read_bytes() != payload:
                raise ValueError(f"Non-deterministic canonical output: {path}")
        else:
            path.write_bytes(payload)
    reject_counts = Counter(code for row in rejects for code in row["reject_codes"])
    report = {
        "schema_version": "1.0",
        "canonical_version": CANONICAL_VERSION,
        "dataset": dataset,
        "source_revision": revision,
        "adapter_version": adapter_version,
        "media_validator_version": media_report["validator_version"],
        "media_validation_report": str(media_report_path.relative_to(root)),
        "candidate_count": len(candidates),
        "canonical_record_count": len(records),
        "canonical_fact_count": sum(len(row["facts"]) for row in records),
        "rejected_count": len(rejects),
        "reject_code_counts": dict(sorted(reject_counts.items())),
        "observability_policy": "AUTO_OBSERVABILITY_PASS_SOURCE_TASK_AND_MEDIA_RESOLUTION",
        "input_hashes": {
            str(candidate_path.relative_to(root)): sha256_file(candidate_path),
            str(mapping_path.relative_to(root)): sha256_file(mapping_path),
            str(media_report_path.relative_to(root)): sha256_file(media_report_path),
        },
        "output_hashes": {
            str(records_path.relative_to(root)): sha256_bytes(records_payload),
            str(reject_path.relative_to(root)): sha256_bytes(rejects_payload),
        },
        "status": "CANONICAL_VALID" if records and not rejects else ("PARTIAL" if records else "REJECTED"),
    }
    report_payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if report_path.exists() and resume and report_path.read_text(encoding="utf-8") != report_payload:
        raise ValueError(f"Non-deterministic canonical report: {report_path}")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if not report_path.exists():
        report_path.write_text(report_payload, encoding="utf-8")
    return report
