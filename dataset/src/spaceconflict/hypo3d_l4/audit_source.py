from __future__ import annotations

import csv
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ..hashing import sha256_file
from . import SOURCE_REVISION
from .common import load_annotations, normalize_change_type, resolve_annotation_path, write_versioned
from .parse_changes import parse_change


EXPECTED_FILES = (
    "hypo3d.json",
    "contextvqa.json",
    "contextvqa_ordered.json",
    "embodiedscan_infos_full_updated.json",
    "scanrefer_captions_by_scene.pkl",
    "3rscan_scene_cap.json",
)
MEDIA_ROLES = (
    "camera_view", "top_view_label", "top_view_no_label",
    "top_view_no_label_rotated", "top_view_with_label_rotated",
)
DIRECTION_ANSWERS = {
    "left", "right", "front", "back", "above", "below", "higher", "lower",
    "front left", "front right", "back left", "back right",
}


def _csv_bytes(header: list[str], rows: list[list[Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _inventory_paths(annotation_path: Path) -> dict[str, list[str]]:
    root = annotation_path.parent
    inventory: dict[str, list[str]] = {}
    for name in EXPECTED_FILES:
        matches = []
        direct = root / name
        if direct.is_file():
            matches.append(str(direct))
        for level_one in sorted(root.glob("*")):
            candidate = level_one / name
            if candidate.is_file() and str(candidate) not in matches:
                matches.append(str(candidate))
        inventory[name] = matches
    id_label_files = [str(path) for path in sorted(root.glob("*/*_id2labels.json"))]
    inventory["*_id2labels.json"] = id_label_files
    return inventory


def _materializable_scene_count(scene_ids: list[str], media_root: Path) -> tuple[int, dict[str, int]]:
    requested = set(scene_ids)
    scene_keys_by_role: dict[str, set[str]] = {}
    for role in MEDIA_ROLES:
        directory = media_root / role
        scene_keys_by_role[role] = (
            {path.stem for path in directory.glob("*.png")} & requested if directory.is_dir() else set()
        )
    role_counts = {role: len(keys) for role, keys in scene_keys_by_role.items()}
    complete_keys = requested.copy()
    for keys in scene_keys_by_role.values():
        complete_keys &= keys
    complete = len(complete_keys)
    return complete, role_counts


def audit_source(
    *, raw_root: Path, output_dir: Path, media_root: Path | None, dry_run: bool,
    resume: bool, limit: int | None, scene_id: str | None,
) -> dict[str, Any]:
    annotation_path = resolve_annotation_path(raw_root)
    if dry_run:
        return {
            "status": "PLANNED", "action": "audit-source", "annotation": str(annotation_path),
            "output_dir": str(output_dir), "limit": limit, "scene_id": scene_id,
        }
    annotations = load_annotations(annotation_path)
    selected_scene_ids = sorted(annotations)
    if scene_id is not None:
        selected_scene_ids = [item for item in selected_scene_ids if item == scene_id]
    if limit is not None:
        selected_scene_ids = selected_scene_ids[:limit]
    change_counts: Counter[str] = Counter()
    question_counts: Counter[str] = Counter()
    missing_counts: Counter[str] = Counter()
    answer_counts: Counter[str] = Counter()
    branch_count = qa_count = parseable_change_count = explicit_target_count = 0
    source_object_list_count = stable_object_id_count = 0
    examples: list[dict[str, Any]] = []
    for current_scene_id in selected_scene_ids:
        branches = annotations[current_scene_id]
        if not isinstance(branches, list):
            missing_counts["malformed_scene_branch_list"] += 1
            continue
        for branch_index, branch in enumerate(branches):
            branch_count += 1
            if not isinstance(branch, dict):
                missing_counts["malformed_branch"] += 1
                continue
            change_type = normalize_change_type(branch.get("change_type"))
            change_counts[change_type] += 1
            context_change = str(branch.get("context_change") or "").strip()
            if not context_change:
                missing_counts["context_change"] += 1
            qas = branch.get("questions_answers")
            if not isinstance(qas, list):
                missing_counts["questions_answers"] += 1
                continue
            probe = {
                "scene_id": current_scene_id,
                "change_id": f"audit_{branch_index}",
                "branch_id": f"hypo3d:{current_scene_id}:audit_{branch_index}",
                "change_type": change_type,
                "context_change_raw": context_change,
            }
            parsed, _ = parse_change(probe)
            if parsed is not None:
                parseable_change_count += 1
                if parsed.get("target_ref_texts") or parsed.get("new_entity_ref_texts"):
                    explicit_target_count += 1
            if any(key in branch for key in ("objects", "object_list", "instances", "annotations")):
                source_object_list_count += 1
            if any(key in branch for key in ("object_id", "instance_id", "target_id", "annotation_id")):
                stable_object_id_count += 1
            for qa in qas:
                qa_count += 1
                if not isinstance(qa, dict):
                    missing_counts["malformed_qa"] += 1
                    continue
                for field in ("question_id", "question_type", "question", "answer"):
                    if qa.get(field) is None or qa.get(field) == "":
                        missing_counts[field] += 1
                question_counts[str(qa.get("question_type") or "<MISSING>")] += 1
                answer = str(qa.get("answer") or "").strip().casefold()
                if answer.isdigit():
                    answer_counts["exact_integer"] += 1
                elif answer in DIRECTION_ANSWERS:
                    answer_counts["categorical_direction"] += 1
                elif answer in {"yes", "no"}:
                    answer_counts["yes_no"] += 1
                else:
                    answer_counts["other"] += 1
                if len(examples) < 10:
                    examples.append({
                        "scene_id": current_scene_id, "branch_index": branch_index,
                        "change_type": change_type, "context_change": context_change,
                        "question_type": qa.get("question_type"), "question": qa.get("question"),
                        "answer": qa.get("answer"),
                    })
    inventory_paths = _inventory_paths(annotation_path)
    actual_media_root = media_root.resolve() if media_root else annotation_path.resolve().parent
    materializable_scenes, media_role_counts = _materializable_scene_count(selected_scene_ids, actual_media_root)
    source_inventory = {
        "schema_version": "hypo3d_l4_source_inventory_v2",
        "status": "SOURCE_AUDITED",
        "source_revision": SOURCE_REVISION,
        "annotation_path": str(annotation_path),
        "media_root": str(actual_media_root),
        "official_or_packaged_files": inventory_paths,
        "base_scene_count": len(selected_scene_ids),
        "context_change_count": branch_count,
        "qa_pair_count": qa_count,
        "records_with_explicit_target_description": explicit_target_count,
        "records_with_source_object_lists": source_object_list_count,
        "records_with_stable_object_index_or_annotation_id": stable_object_id_count,
        "records_with_unique_target_candidates": 0,
        "unique_target_note": "Requires structured object annotations; text parsing alone never establishes uniqueness.",
        "materializable_scene_count_all_five_roles": materializable_scenes,
        "media_role_scene_counts": media_role_counts,
    }
    schema_profile = {
        "schema_version": "hypo3d_l4_schema_profile_v2",
        "top_level_type": "scene_id_to_branch_list",
        "observed_branch_fields": ["change_type", "context_change", "questions_answers"],
        "observed_qa_fields": ["question_id", "question_type", "question", "answer"],
        "change_parseable_branch_count": parseable_change_count,
        "answer_type_distribution": dict(sorted(answer_counts.items())),
        "missing_field_counts": dict(sorted(missing_counts.items())),
        "examples": examples,
    }
    hash_rows = []
    for matches in inventory_paths.values():
        for raw_path in matches:
            path = Path(raw_path)
            hash_rows.append({"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    hash_rows = sorted(hash_rows, key=lambda row: row["path"])
    markdown = "\n".join([
        "# Hypo3D L4 v2 source inventory",
        "",
        f"- 状态：`{source_inventory['status']}`",
        f"- 场景：{len(selected_scene_ids)}",
        f"- context changes：{branch_count}",
        f"- QA：{qa_count}",
        f"- 可解析 change：{parseable_change_count}",
        f"- 具有结构化 object list 的 branch：{source_object_list_count}",
        f"- 具有稳定 object/instance ID 的 branch：{stable_object_id_count}",
        f"- 五类媒体均可 materialize 的场景：{materializable_scenes}",
        "",
        "注意：target 描述可解析不等于 target 唯一解析；没有结构化对象标注时 unique target 仍为 0。",
        "",
    ]).encode("utf-8")
    outputs = {
        "source_inventory.json": _json_bytes(source_inventory),
        "source_inventory.md": markdown,
        "schema_profile.json": _json_bytes(schema_profile),
        "change_type_profile.csv": _csv_bytes(["change_type", "count"], [[key, value] for key, value in sorted(change_counts.items())]),
        "question_type_profile.csv": _csv_bytes(["question_type", "count"], [[key, value] for key, value in sorted(question_counts.items())]),
        "missing_field_profile.csv": _csv_bytes(["field", "missing_count"], [[key, value] for key, value in sorted(missing_counts.items())]),
        "source_hash_manifest.jsonl": b"".join(json.dumps(row, sort_keys=True).encode("utf-8") + b"\n" for row in hash_rows),
    }
    for name, payload in outputs.items():
        write_versioned(output_dir / name, payload, resume=resume)
    return {
        "status": "SOURCE_AUDITED", "action": "audit-source",
        "scene_count": len(selected_scene_ids), "branch_count": branch_count, "qa_count": qa_count,
        "parseable_change_count": parseable_change_count,
        "structured_object_list_branch_count": source_object_list_count,
        "stable_object_id_branch_count": stable_object_id_count,
        "materializable_scene_count": materializable_scenes,
        "output_paths": {name: str(output_dir / name) for name in outputs},
        "input_hashes": {str(annotation_path): sha256_file(annotation_path)},
        "output_hashes": {str(output_dir / name): sha256_file(output_dir / name) for name in outputs},
    }
