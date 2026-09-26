from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from ..hashing import sha256_file
from ..registry import ROOT
from .audit_source import audit_source
from .common import (
    iter_branch_records, jsonl_bytes, load_annotations, resolve_annotation_path, write_versioned,
)
from .count_claims import build_count_pair
from .existence_claims import select_existence_calibration_pairs
from .grounding_metadata import audit_grounding_metadata
from .normalize_qa import NORMALIZER_VERSION, normalize_post_qa as normalize_qa_record
from .object_catalog import (
    OFFICIAL_SOURCE_TYPE, OFFICIAL_SOURCE_TYPES, UNVERIFIED_MIRROR_SOURCE_TYPE,
    extract_embodiedscan_object_catalog,
)
from .parse_changes import PARSER_VERSION, parse_change
from .prestates import build_count_prestate
from .resolve_targets import RESOLVER_VERSION, load_object_catalog, resolve_intervention_targets
from .verify_l4 import verify_official_count_pairs


DEFAULT_RAW_ROOT = ROOT / "data/raw/hypo3d"
DEFAULT_REPORT_DIR = ROOT / "reports/hypo3d_l4_v2"
DEFAULT_CANONICAL_DIR = ROOT / "data/canonical/hypo3d_l4_v2"
DEFAULT_MICROGRAPH_DIR = ROOT / "transition_micrographs/hypo3d_l4_v2"


def _load_schema(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _validate_rows(rows: list[dict[str, Any]], schema_name: str) -> None:
    validator = Draft202012Validator(_load_schema(schema_name))
    failures = []
    for index, row in enumerate(rows):
        errors = sorted(validator.iter_errors(row), key=lambda error: list(error.path))
        if errors:
            failures.append(f"row {index}: {errors[0].message}")
    if failures:
        raise ValueError(f"{schema_name} validation failed: {'; '.join(failures[:10])}")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def build_branch_index(
    *, raw_root: Path, output_dir: Path, dry_run: bool, resume: bool, limit: int | None,
    scene_id: str | None, change_id: str | None, question_id: str | None,
) -> dict[str, Any]:
    annotation_path = resolve_annotation_path(raw_root)
    output_path = output_dir / "branches.jsonl"
    if dry_run:
        return {"status": "PLANNED", "action": "build-branch-index", "input": str(annotation_path), "output": str(output_path)}
    annotations = load_annotations(annotation_path)
    rows = list(iter_branch_records(
        annotations, scene_id=scene_id, change_id=change_id, question_id=question_id, limit=limit,
    ))
    _validate_rows(rows, "hypo3d_branch_record.schema.json")
    payload = jsonl_bytes(rows)
    write_versioned(output_path, payload, resume=resume)
    worlds = {row["global_world_id"] for row in rows}
    branches = {row["branch_id"] for row in rows}
    return {
        "status": "BRANCH_INDEX_VALID", "action": "build-branch-index",
        "record_count": len(rows), "world_count": len(worlds), "branch_count": len(branches),
        "output": str(output_path),
        "input_hashes": {str(annotation_path): sha256_file(annotation_path)},
        "output_hashes": {str(output_path): sha256_file(output_path)},
    }


def parse_changes(
    *, branch_index: Path, output_dir: Path, dry_run: bool, resume: bool, limit: int | None,
    scene_id: str | None, change_id: str | None, question_id: str | None,
) -> dict[str, Any]:
    version_tag = PARSER_VERSION.removeprefix("hypo3d_change_parser_")
    output_path = output_dir / f"parsed_changes.{version_tag}.jsonl"
    reject_path = ROOT / f"rejected/hypo3d_l4_v2/change_parse_rejects.{version_tag}.jsonl"
    if dry_run:
        return {"status": "PLANNED", "action": "parse-changes", "input": str(branch_index), "output": str(output_path), "reject_output": str(reject_path)}
    rows = _read_jsonl(branch_index)
    selected: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    for record in rows:
        if scene_id and record["scene_id"] != scene_id:
            continue
        if change_id and record["change_id"] != change_id:
            continue
        if question_id and record["question_id"] != question_id:
            continue
        parsed, reject_code = parse_change(record)
        if parsed is None:
            rejects.append({
                "scene_id": record["scene_id"], "change_id": record["change_id"],
                "question_id": record["question_id"], "source_hash": record["source_hash"],
                "reject_code": reject_code,
            })
        else:
            selected.append({
                "scene_id": record["scene_id"], "change_id": record["change_id"],
                "question_id": record["question_id"], "branch_id": record["branch_id"],
                "source_hash": record["source_hash"], "intervention": parsed,
            })
        if limit is not None and len(selected) + len(rejects) >= limit:
            break
    write_versioned(output_path, jsonl_bytes(selected), resume=resume)
    write_versioned(reject_path, jsonl_bytes(rejects), resume=resume)
    counts = Counter(row["reject_code"] for row in rejects)
    return {
        "status": "CHANGE_PARSE_VALID", "action": "parse-changes",
        "candidate_count": len(selected), "rejected_count": len(rejects),
        "reject_code_counts": dict(sorted(counts.items())), "output": str(output_path),
        "reject_output": str(reject_path),
        "input_hashes": {str(branch_index): sha256_file(branch_index)},
        "output_hashes": {str(output_path): sha256_file(output_path), str(reject_path): sha256_file(reject_path)},
    }


def normalize_post_qa(
    *, branch_index: Path, output_dir: Path, dry_run: bool, resume: bool, limit: int | None,
    scene_id: str | None, change_id: str | None, question_id: str | None,
) -> dict[str, Any]:
    version_tag = NORMALIZER_VERSION.removeprefix("hypo3d_post_qa_normalizer_")
    output_path = output_dir / f"post_state_oracles.{version_tag}.jsonl"
    reject_path = ROOT / f"rejected/hypo3d_l4_v2/post_oracle_rejects.{version_tag}.jsonl"
    if dry_run:
        return {"status": "PLANNED", "action": "normalize-post-qa", "input": str(branch_index), "output": str(output_path), "reject_output": str(reject_path)}
    rows = _read_jsonl(branch_index)
    selected: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    for record in rows:
        if scene_id and record["scene_id"] != scene_id:
            continue
        if change_id and record["change_id"] != change_id:
            continue
        if question_id and record["question_id"] != question_id:
            continue
        oracle, reject_code = normalize_qa_record(record)
        if oracle is None:
            rejects.append({
                "scene_id": record["scene_id"], "change_id": record["change_id"],
                "question_id": record["question_id"], "source_hash": record["source_hash"],
                "reject_code": reject_code,
            })
        else:
            selected.append(oracle)
        if limit is not None and len(selected) + len(rejects) >= limit:
            break
    _validate_rows(selected, "post_state_oracle.schema.json")
    write_versioned(output_path, jsonl_bytes(selected), resume=resume)
    write_versioned(reject_path, jsonl_bytes(rejects), resume=resume)
    counts = Counter(row["reject_code"] for row in rejects)
    return {
        "status": "POST_ORACLE_VALID", "action": "normalize-post-qa",
        "oracle_count": len(selected), "rejected_count": len(rejects),
        "reject_code_counts": dict(sorted(counts.items())), "output": str(output_path),
        "reject_output": str(reject_path),
        "input_hashes": {str(branch_index): sha256_file(branch_index)},
        "output_hashes": {str(output_path): sha256_file(output_path), str(reject_path): sha256_file(reject_path)},
    }


def resolve_targets(
    *, parsed_changes: Path, object_catalog: Path | None, output_dir: Path,
    dry_run: bool, resume: bool, limit: int | None, scene_id: str | None,
    change_id: str | None, question_id: str | None,
) -> dict[str, Any]:
    # The no-catalog pass is a useful, immutable source audit.  A later pass with
    # official annotations must not overwrite it even though the resolver
    # algorithm itself has not changed.
    catalog = load_object_catalog(object_catalog) if object_catalog is not None and object_catalog.is_file() else None
    if catalog is not None and catalog.get("source_type") == UNVERIFIED_MIRROR_SOURCE_TYPE:
        artifact_version = "provisional_mirror_v2"
        reject_dir = ROOT / "rejected/hypo3d_l4_v2_provisional_mirror"
    else:
        artifact_version = RESOLVER_VERSION.removeprefix("hypo3d_target_resolver_") if object_catalog is not None else "v2"
        reject_dir = ROOT / "rejected/hypo3d_l4_v2"
    output_path = output_dir / f"target_resolutions.{artifact_version}.jsonl"
    reject_path = reject_dir / f"target_resolution_rejects.{output_dir.name}.{artifact_version}.jsonl"
    if dry_run:
        return {
            "status": "PLANNED", "action": "resolve-targets", "input": str(parsed_changes),
            "object_catalog": str(object_catalog) if object_catalog else None,
            "output": str(output_path), "reject_output": str(reject_path),
        }
    catalog = catalog if catalog is not None else load_object_catalog(object_catalog)
    rows = _read_jsonl(parsed_changes)
    selected: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    for row in rows:
        if scene_id and row["scene_id"] != scene_id:
            continue
        if change_id and row["change_id"] != change_id:
            continue
        if question_id and row["question_id"] != question_id:
            continue
        resolution, reject_code = resolve_intervention_targets(row, catalog)
        if resolution is None:
            rejects.append({
                "scene_id": row["scene_id"], "change_id": row["change_id"],
                "question_id": row["question_id"], "source_hash": row["source_hash"],
                "reject_code": reject_code,
            })
        else:
            selected.append(resolution)
        if limit is not None and len(selected) + len(rejects) >= limit:
            break
    write_versioned(output_path, jsonl_bytes(selected), resume=resume)
    write_versioned(reject_path, jsonl_bytes(rejects), resume=resume)
    counts = Counter(row["reject_code"] for row in rejects)
    inputs = {str(parsed_changes): sha256_file(parsed_changes)}
    if object_catalog:
        inputs[str(object_catalog)] = sha256_file(object_catalog)
    official_catalog = catalog is None or catalog.get("source_type") in OFFICIAL_SOURCE_TYPES
    return {
        "status": "TARGET_RESOLUTION_VALID" if official_catalog else "TARGET_RESOLUTION_PROVISIONAL",
        "action": "resolve-targets",
        "resolved_count": len(selected), "rejected_count": len(rejects),
        "reject_code_counts": dict(sorted(counts.items())),
        "annotation_catalog_available": object_catalog is not None,
        "output": str(output_path), "reject_output": str(reject_path),
        "input_hashes": inputs,
        "output_hashes": {str(output_path): sha256_file(output_path), str(reject_path): sha256_file(reject_path)},
    }


def build_foundation_report(
    *, branch_index: Path, parsed_changes: Path, post_oracles: Path,
    target_resolutions: Path, output_dir: Path, dry_run: bool, resume: bool,
) -> dict[str, Any]:
    output_json = output_dir / "foundation_status.v2.json"
    output_markdown = output_dir / "foundation_status.v2.md"
    inputs = [branch_index, parsed_changes, post_oracles, target_resolutions]
    if dry_run:
        return {
            "status": "PLANNED", "action": "report",
            "inputs": [str(path) for path in inputs],
            "outputs": [str(output_json), str(output_markdown)],
        }
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        return {"status": "BLOCKED_SOURCE", "action": "report", "missing_inputs": missing}
    branches = _read_jsonl(branch_index)
    parsed = _read_jsonl(parsed_changes)
    oracles = _read_jsonl(post_oracles)
    resolutions = _read_jsonl(target_resolutions)
    def key(row: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(row["scene_id"]), str(row["change_id"]),
            str(row.get("question_id") or row.get("source_question_id")),
        )
    branch_by_key = {key(row): row for row in branches}
    parsed_keys = {key(row) for row in parsed}
    oracle_keys = {key(row) for row in oracles}
    resolution_keys = {key(row) for row in resolutions}
    structural_keys = parsed_keys & oracle_keys
    grounded_structural_keys = structural_keys & resolution_keys
    structural_by_change = Counter(branch_by_key[item]["change_type"] for item in structural_keys)
    grounded_by_change = Counter(branch_by_key[item]["change_type"] for item in grounded_structural_keys)
    oracle_predicates = Counter(
        atom["predicate"] for row in oracles for atom in row.get("normalized_atoms", [])
    )
    report = {
        "schema_version": "hypo3d_l4_foundation_status_v2",
        "status": "FOUNDATION_VALID_PRESTATE_BLOCKED",
        "branch_record_count": len(branches),
        "parsed_change_qa_count": len(parsed),
        "post_oracle_count": len(oracles),
        "target_resolution_count": len(resolutions),
        "parsed_and_oracle_count": len(structural_keys),
        "parsed_oracle_and_target_count": len(grounded_structural_keys),
        "parsed_and_oracle_by_change_type": dict(sorted(structural_by_change.items())),
        "parsed_oracle_and_target_by_change_type": dict(sorted(grounded_by_change.items())),
        "oracle_predicate_distribution": dict(sorted(oracle_predicates.items())),
        "structured_object_catalog_available": False,
        "question_scoped_prestate_count": 0,
        "transition_valid_count": 0,
        "l4_core_auto_accepted": 0,
        "l4_calibration_auto_accepted": 0,
        "candidate_semantics": "Structural overlap is not an accepted L4 count.",
        "blocking_gates": [
            "STRUCTURED_OBJECT_CATALOG_MISSING",
            "ANNOTATION_ALIGNED_PRESTATE_BUILDER_NOT_RUN",
            "ACCESSIBLE_REASONING_CERTIFICATE_NOT_AVAILABLE",
            "DEPENDENCY_ABLATION_NOT_RUN",
        ],
        "next_required_source_fields": [
            "scene_id", "object_id", "object_class_or_label", "object_aliases_or_descriptions",
            "optional_source_relations_with_reference_frame",
        ],
    }
    markdown = "\n".join([
        "# Hypo3D L4 v2 foundation status",
        "",
        f"- Branch QA records: {len(branches)}",
        f"- Parsed changes: {len(parsed)}",
        f"- Reversible post-state oracles: {len(oracles)}",
        f"- Parsed + oracle structural overlap: {len(structural_keys)}",
        f"- Current target resolutions: {len(resolutions)}（仅 addition branch-local new entity）",
        "- Structured object catalog: missing",
        "- Question-scoped prestates: 0",
        "- AUTO_ACCEPTED L4-Core: 0",
        "- AUTO_ACCEPTED L4-Calibration: 0",
        "",
        "结构交集不是已接受 L4；在获得官方对象/实例标注并完成 pre-state、proof 和 dependency gates 前不得提升为 benchmark 样本。",
        "",
    ]).encode("utf-8")
    json_payload = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    write_versioned(output_json, json_payload, resume=resume)
    write_versioned(output_markdown, markdown, resume=resume)
    return {
        **report,
        "action": "report",
        "outputs": {"json": str(output_json), "markdown": str(output_markdown)},
        "input_hashes": {str(path): sha256_file(path) for path in inputs},
        "output_hashes": {str(output_json): sha256_file(output_json), str(output_markdown): sha256_file(output_markdown)},
    }


def build_object_catalog(
    *, annotation_path: Path, info_paths: list[Path], output_dir: Path,
    source_type: str, dry_run: bool, resume: bool,
) -> dict[str, Any]:
    artifact = "object_catalog.v2.json" if source_type == OFFICIAL_SOURCE_TYPE else "object_catalog.provisional_mirror_v2.json"
    output_path = output_dir / artifact
    if dry_run:
        return {
            "status": "PLANNED", "action": "build-object-catalog",
            "annotation": str(annotation_path), "embodiedscan_infos": [str(path) for path in info_paths],
            "source_type": source_type, "output": str(output_path),
        }
    if not info_paths:
        return {
            "status": "BLOCKED_SOURCE", "action": "build-object-catalog",
            "reason": "EMBODIEDSCAN_INFO_PKL_MISSING",
        }
    missing = [str(path) for path in info_paths if not path.is_file()]
    if missing:
        return {"status": "BLOCKED_SOURCE", "action": "build-object-catalog", "missing_inputs": missing}
    annotations = load_annotations(annotation_path)
    catalog = extract_embodiedscan_object_catalog(
        info_paths, selected_scene_ids=set(annotations), source_type=source_type,
    )
    _validate_rows([catalog], "hypo3d_object_catalog.schema.json")
    payload = (json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    write_versioned(output_path, payload, resume=resume)
    return {
        "status": "OBJECT_CATALOG_VALID" if source_type == OFFICIAL_SOURCE_TYPE else "OBJECT_CATALOG_PROVISIONAL",
        "action": "build-object-catalog", "source_type": source_type,
        "scene_count": len(catalog["scenes"]),
        "object_count": sum(len(scene["objects"]) for scene in catalog["scenes"].values()),
        "output": str(output_path),
        "input_hashes": {str(path): sha256_file(path) for path in [annotation_path, *info_paths]},
        "output_hashes": {str(output_path): sha256_file(output_path)},
    }


def build_prestates(
    *, branch_index: Path, parsed_changes: Path, post_oracles: Path,
    target_resolutions: Path, object_catalog: Path | None, output_dir: Path,
    dry_run: bool, resume: bool, limit: int | None,
) -> dict[str, Any]:
    output_path = output_dir / "prestates.count_v2.jsonl"
    reject_path = ROOT / f"rejected/hypo3d_l4_v2/prestate_rejects.{output_dir.name}.count_v2.jsonl"
    inputs = [branch_index, parsed_changes, post_oracles, target_resolutions]
    if dry_run:
        return {
            "status": "PLANNED", "action": "build-prestates", "inputs": [str(path) for path in inputs],
            "object_catalog": str(object_catalog) if object_catalog else None,
            "output": str(output_path), "reject_output": str(reject_path),
        }
    if object_catalog is None or not object_catalog.is_file():
        return {
            "status": "BLOCKED_SOURCE", "action": "build-prestates",
            "reason": "STRUCTURED_OBJECT_CATALOG_MISSING",
            "required_input": str(object_catalog) if object_catalog else None,
        }
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        return {"status": "BLOCKED_SOURCE", "action": "build-prestates", "missing_inputs": missing}
    catalog = json.loads(object_catalog.read_text(encoding="utf-8"))
    if catalog.get("source_type") not in OFFICIAL_SOURCE_TYPES:
        return {
            "status": "BLOCKED_SOURCE", "action": "build-prestates",
            "reason": "OBJECT_CATALOG_NOT_OFFICIAL",
            "catalog_source_type": catalog.get("source_type"),
        }
    branches = _read_jsonl(branch_index)
    parsed = _read_jsonl(parsed_changes)
    oracles = _read_jsonl(post_oracles)
    resolutions = _read_jsonl(target_resolutions)
    def key(row: dict[str, Any]) -> tuple[str, str, str]:
        return (str(row["scene_id"]), str(row["change_id"]), str(row.get("question_id") or row.get("source_question_id")))
    branch_map = {key(row): row for row in branches}
    parsed_map = {key(row): row for row in parsed}
    oracle_map = {key(row): row for row in oracles}
    resolution_map = {key(row): row for row in resolutions}
    common_keys = sorted(branch_map.keys() & parsed_map.keys() & oracle_map.keys() & resolution_map.keys())
    selected: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    for current_key in common_keys:
        bundle, reject_code = build_count_prestate(
            branch=branch_map[current_key], parsed=parsed_map[current_key],
            oracle=oracle_map[current_key], resolution=resolution_map[current_key], catalog=catalog,
        )
        if bundle is None:
            rejects.append({
                "scene_id": current_key[0], "change_id": current_key[1],
                "question_id": current_key[2], "reject_code": reject_code,
            })
        else:
            selected.append(bundle)
        if limit is not None and len(selected) + len(rejects) >= limit:
            break
    write_versioned(output_path, jsonl_bytes(selected), resume=resume)
    write_versioned(reject_path, jsonl_bytes(rejects), resume=resume)
    counts = Counter(row["reject_code"] for row in rejects)
    all_inputs = [*inputs, object_catalog]
    return {
        "status": "PRESTATE_VALID" if selected else "PRESTATE_SHORTFALL",
        "action": "build-prestates", "candidate_count": len(selected),
        "rejected_count": len(rejects), "reject_code_counts": dict(sorted(counts.items())),
        "output": str(output_path), "reject_output": str(reject_path),
        "input_hashes": {str(path): sha256_file(path) for path in all_inputs},
        "output_hashes": {str(output_path): sha256_file(output_path), str(reject_path): sha256_file(reject_path)},
    }


def audit_provisional_coverage(
    *, branch_index: Path, parsed_changes: Path, post_oracles: Path,
    target_resolutions: Path, object_catalog: Path | None, output_dir: Path,
    dry_run: bool, resume: bool,
) -> dict[str, Any]:
    """Count mirror-backed possibilities without emitting formal prestate artifacts."""
    output_json = output_dir / "provisional_coverage.v2.json"
    output_markdown = output_dir / "provisional_coverage.v2.md"
    inputs = [branch_index, parsed_changes, post_oracles, target_resolutions]
    if object_catalog is not None:
        inputs.append(object_catalog)
    if dry_run:
        return {
            "status": "PLANNED", "action": "audit-provisional-coverage",
            "inputs": [str(path) for path in inputs], "output": str(output_json),
        }
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        return {"status": "BLOCKED_SOURCE", "action": "audit-provisional-coverage", "missing_inputs": missing}
    if object_catalog is None:
        return {
            "status": "BLOCKED_SOURCE", "action": "audit-provisional-coverage",
            "reason": "STRUCTURED_OBJECT_CATALOG_MISSING",
        }
    catalog = json.loads(object_catalog.read_text(encoding="utf-8"))
    if catalog.get("source_type") != UNVERIFIED_MIRROR_SOURCE_TYPE:
        return {
            "status": "BLOCKED_SOURCE", "action": "audit-provisional-coverage",
            "reason": "PROVISIONAL_AUDIT_REQUIRES_QUARANTINED_MIRROR_CATALOG",
            "catalog_source_type": catalog.get("source_type"),
        }

    def row_key(row: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(row["scene_id"]), str(row["change_id"]),
            str(row.get("question_id") or row.get("source_question_id")),
        )

    branches = {row_key(row): row for row in _read_jsonl(branch_index)}
    parsed = {row_key(row): row for row in _read_jsonl(parsed_changes)}
    oracles = {row_key(row): row for row in _read_jsonl(post_oracles)}
    resolutions = {row_key(row): row for row in _read_jsonl(target_resolutions)}
    common_keys = sorted(branches.keys() & parsed.keys() & oracles.keys() & resolutions.keys())
    candidates = Counter()
    rejects = Counter()
    for current_key in common_keys:
        bundle, reject_code = build_count_prestate(
            branch=branches[current_key], parsed=parsed[current_key],
            oracle=oracles[current_key], resolution=resolutions[current_key], catalog=catalog,
        )
        if bundle is None:
            rejects[str(reject_code)] += 1
        else:
            candidates[str(parsed[current_key]["intervention"]["type"])] += 1
    report = {
        "schema_version": "hypo3d_l4_provisional_coverage_v2",
        "status": "PROVISIONAL_COVERAGE_AUDITED",
        "catalog_source_type": UNVERIFIED_MIRROR_SOURCE_TYPE,
        "truth_boundary": "DIAGNOSTIC_ONLY_NOT_FORMAL_PRESTATE_OR_BENCHMARK_TRUTH",
        "structural_target_overlap_count": len(common_keys),
        "would_pass_count_rule_count": sum(candidates.values()),
        "would_pass_by_change_type": dict(sorted(candidates.items())),
        "reject_code_counts": dict(sorted(rejects.items())),
        "formal_prestate_count": 0,
        "auto_accepted_l4_count": 0,
        "input_hashes": {str(path): sha256_file(path) for path in inputs},
    }
    markdown = "\n".join([
        "# Hypo3D L4 provisional mirror coverage",
        "",
        f"- Structural target overlap: {len(common_keys)}",
        f"- Would pass current count rule: {sum(candidates.values())}",
        f"- Formal prestates: 0",
        f"- AUTO_ACCEPTED L4: 0",
        "",
        "该报告只用于第三方镜像覆盖率诊断，不是正式对象标注、pre-state 或 benchmark truth。",
        "",
    ]).encode("utf-8")
    write_versioned(
        output_json, (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        resume=resume,
    )
    write_versioned(output_markdown, markdown, resume=resume)
    return {
        **report, "action": "audit-provisional-coverage",
        "outputs": {"json": str(output_json), "markdown": str(output_markdown)},
        "output_hashes": {str(output_json): sha256_file(output_json), str(output_markdown): sha256_file(output_markdown)},
    }


def generate_l4_count_claims(
    *, prestates: Path, output_dir: Path, dry_run: bool, resume: bool, limit: int | None,
    calibration_limit: int = 0,
) -> dict[str, Any]:
    output_path = output_dir / "pairs.count_l4_core_v2.jsonl"
    if dry_run:
        return {"status": "PLANNED", "action": "generate-claim-graphs", "input": str(prestates), "output": str(output_path)}
    if not prestates.is_file():
        return {"status": "BLOCKED_SOURCE", "action": "generate-claim-graphs", "reason": "PRESTATE_INPUT_MISSING", "input": str(prestates)}
    bundles = _read_jsonl(prestates)
    if limit is not None:
        bundles = bundles[:limit]
    core_pairs = [build_count_pair(bundle) for bundle in bundles]
    calibration_pairs = select_existence_calibration_pairs(
        bundles, requested_limit=calibration_limit, core_pair_count=len(core_pairs),
    )
    pairs = [*core_pairs, *calibration_pairs]
    write_versioned(output_path, jsonl_bytes(pairs), resume=resume)
    return {
        "status": "CLAIM_GRAPH_VALID" if pairs else "CLAIM_GRAPH_SHORTFALL",
        "action": "generate-claim-graphs", "pair_count": len(pairs),
        "core_pair_count": len(core_pairs), "calibration_pair_count": len(calibration_pairs),
        "auto_accepted_count": sum(pair["validation"]["final_status"] == "AUTO_ACCEPTED" for pair in pairs),
        "output": str(output_path),
        "input_hashes": {str(prestates): sha256_file(prestates)},
        "output_hashes": {str(output_path): sha256_file(output_path)},
    }


def run_action(
    action: str, *, raw_root: Path = DEFAULT_RAW_ROOT, output: Path | None = None,
    media_root: Path | None = None, branch_index: Path | None = None,
    parsed_changes: Path | None = None, object_catalog: Path | None = None,
    post_oracles: Path | None = None, target_resolutions: Path | None = None,
    grounding_metadata: Path | None = None,
    catalog_source_type: str = OFFICIAL_SOURCE_TYPE,
    embodiedscan_infos: list[Path] | None = None,
    prestates: Path | None = None, pairs: Path | None = None, calibration_limit: int = 0,
    dry_run: bool, resume: bool, limit: int | None, scene_id: str | None,
    change_id: str | None, question_id: str | None,
) -> dict[str, Any]:
    if action == "audit-source":
        return audit_source(
            raw_root=raw_root, output_dir=output or DEFAULT_REPORT_DIR, media_root=media_root,
            dry_run=dry_run, resume=resume, limit=limit, scene_id=scene_id,
        )
    if action == "audit-grounding":
        if grounding_metadata is None:
            return {
                "status": "BLOCKED_SOURCE", "action": "audit-grounding",
                "reason": "GROUNDING_METADATA_PATH_REQUIRED",
            }
        return audit_grounding_metadata(
            metadata_path=grounding_metadata,
            annotation_path=resolve_annotation_path(raw_root),
            output_dir=output or DEFAULT_REPORT_DIR / "grounding",
            dry_run=dry_run, resume=resume,
        )
    if action == "build-object-catalog":
        return build_object_catalog(
            annotation_path=resolve_annotation_path(raw_root),
            info_paths=embodiedscan_infos or [],
            output_dir=output or DEFAULT_CANONICAL_DIR,
            source_type=catalog_source_type,
            dry_run=dry_run, resume=resume,
        )
    index_path = branch_index or DEFAULT_CANONICAL_DIR / "branches.jsonl"
    if action == "build-branch-index":
        return build_branch_index(
            raw_root=raw_root, output_dir=output or DEFAULT_CANONICAL_DIR, dry_run=dry_run,
            resume=resume, limit=limit, scene_id=scene_id, change_id=change_id,
            question_id=question_id,
        )
    if action == "parse-changes":
        return parse_changes(
            branch_index=index_path, output_dir=output or DEFAULT_MICROGRAPH_DIR,
            dry_run=dry_run, resume=resume, limit=limit, scene_id=scene_id,
            change_id=change_id, question_id=question_id,
        )
    if action == "normalize-post-qa":
        return normalize_post_qa(
            branch_index=index_path, output_dir=output or DEFAULT_MICROGRAPH_DIR,
            dry_run=dry_run, resume=resume, limit=limit, scene_id=scene_id,
            change_id=change_id, question_id=question_id,
        )
    if action == "resolve-targets":
        default_parsed = DEFAULT_MICROGRAPH_DIR / f"parsed_changes.{PARSER_VERSION.removeprefix('hypo3d_change_parser_')}.jsonl"
        return resolve_targets(
            parsed_changes=parsed_changes or default_parsed,
            object_catalog=object_catalog,
            output_dir=output or DEFAULT_MICROGRAPH_DIR,
            dry_run=dry_run, resume=resume, limit=limit, scene_id=scene_id,
            change_id=change_id, question_id=question_id,
        )
    if action == "build-prestates":
        default_parsed = DEFAULT_MICROGRAPH_DIR / f"parsed_changes.{PARSER_VERSION.removeprefix('hypo3d_change_parser_')}.jsonl"
        default_oracles = DEFAULT_MICROGRAPH_DIR / f"post_state_oracles.{NORMALIZER_VERSION.removeprefix('hypo3d_post_qa_normalizer_')}.jsonl"
        default_resolution_version = RESOLVER_VERSION.removeprefix("hypo3d_target_resolver_") if object_catalog is not None else "v2"
        return build_prestates(
            branch_index=index_path,
            parsed_changes=parsed_changes or default_parsed,
            post_oracles=post_oracles or default_oracles,
            target_resolutions=target_resolutions or DEFAULT_MICROGRAPH_DIR / f"target_resolutions.{default_resolution_version}.jsonl",
            object_catalog=object_catalog,
            output_dir=output or DEFAULT_MICROGRAPH_DIR,
            dry_run=dry_run, resume=resume, limit=limit,
        )
    if action == "audit-provisional-coverage":
        default_parsed = DEFAULT_MICROGRAPH_DIR / f"parsed_changes.{PARSER_VERSION.removeprefix('hypo3d_change_parser_')}.jsonl"
        default_oracles = DEFAULT_MICROGRAPH_DIR / f"post_state_oracles.{NORMALIZER_VERSION.removeprefix('hypo3d_post_qa_normalizer_')}.jsonl"
        return audit_provisional_coverage(
            branch_index=index_path,
            parsed_changes=parsed_changes or default_parsed,
            post_oracles=post_oracles or default_oracles,
            target_resolutions=target_resolutions or DEFAULT_MICROGRAPH_DIR / "target_resolutions.provisional_mirror_v2.jsonl",
            object_catalog=object_catalog,
            output_dir=output or DEFAULT_REPORT_DIR / "provisional_mirror_v2",
            dry_run=dry_run, resume=resume,
        )
    if action == "build-transitions":
        return {
            "status": "BLOCKED_SOURCE" if not (prestates or DEFAULT_MICROGRAPH_DIR / "prestates.count_v2.jsonl").is_file() else "TRANSITION_INPUT_VALID",
            "action": "build-transitions",
            "input": str(prestates or DEFAULT_MICROGRAPH_DIR / "prestates.count_v2.jsonl"),
            "note": "Count prestate bundles already contain replayed authorized local transitions.",
        }
    if action == "generate-claim-graphs":
        return generate_l4_count_claims(
            prestates=prestates or DEFAULT_MICROGRAPH_DIR / "prestates.count_v2.jsonl",
            output_dir=output or ROOT / "claim_graphs/hypo3d_l4_v2",
            dry_run=dry_run, resume=resume, limit=limit, calibration_limit=calibration_limit,
        )
    if action == "verify":
        if media_root is None:
            return {
                "status": "BLOCKED_SOURCE", "action": "verify",
                "reason": "MEDIA_ROOT_REQUIRED",
            }
        return verify_official_count_pairs(
            branch_index=index_path,
            post_oracles=post_oracles or DEFAULT_MICROGRAPH_DIR / f"post_state_oracles.{NORMALIZER_VERSION.removeprefix('hypo3d_post_qa_normalizer_')}.jsonl",
            prestates=prestates or ROOT / "transition_micrographs/hypo3d_l4_v2_official/prestates.count_v2.jsonl",
            pairs=pairs or ROOT / "claim_graphs/hypo3d_l4_v2_official/pairs.count_l4_core_v2.jsonl",
            media_root=media_root,
            output_dir=output or ROOT / "accepted/hypo3d_l4_v2_official",
            dry_run=dry_run, resume=resume,
        )
    if action == "report":
        default_parsed = DEFAULT_MICROGRAPH_DIR / f"parsed_changes.{PARSER_VERSION.removeprefix('hypo3d_change_parser_')}.jsonl"
        default_oracles = DEFAULT_MICROGRAPH_DIR / f"post_state_oracles.{NORMALIZER_VERSION.removeprefix('hypo3d_post_qa_normalizer_')}.jsonl"
        return build_foundation_report(
            branch_index=index_path,
            parsed_changes=parsed_changes or default_parsed,
            post_oracles=post_oracles or default_oracles,
            target_resolutions=target_resolutions or DEFAULT_MICROGRAPH_DIR / "target_resolutions.v2.jsonl",
            output_dir=output or DEFAULT_REPORT_DIR,
            dry_run=dry_run, resume=resume,
        )
    return {
        "status": "BLOCKED_IMPLEMENTATION", "action": action,
        "reason": "FOUNDATION_STAGES_MUST_PASS_BEFORE_TARGET_PRESTATE_OR_TRANSITION_BUILD",
    }
