from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import SOURCE_REVISION


CHANGE_TYPES = ("REMOVAL", "ADDITION", "REPLACEMENT", "MOVEMENT", "ATTRIBUTE")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def object_hash(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_json(value)).hexdigest()}"


def normalize_change_type(value: Any) -> str:
    text = " ".join(str(value or "").casefold().replace("_", " ").split())
    for token, normalized in (
        ("remov", "REMOVAL"),
        ("add", "ADDITION"),
        ("replace", "REPLACEMENT"),
        ("replacement", "REPLACEMENT"),
        ("mov", "MOVEMENT"),
        ("relocat", "MOVEMENT"),
        ("attribute", "ATTRIBUTE"),
    ):
        if token in text:
            return normalized
    return "UNKNOWN"


def resolve_annotation_path(raw_root: Path) -> Path:
    raw_root = raw_root.resolve()
    if raw_root.is_file():
        if raw_root.name != "hypo3d.json":
            raise ValueError(f"Expected hypo3d.json, got {raw_root}")
        return raw_root
    direct_candidates = (
        raw_root / "hypo3d.json",
        raw_root / SOURCE_REVISION / "hypo3d.json",
    )
    for path in direct_candidates:
        if path.is_file():
            return path
    matches = sorted(raw_root.glob("*/hypo3d.json"))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected exactly one hypo3d.json below {raw_root}; found {len(matches)}")
    return matches[0]


def load_annotations(annotation_path: Path) -> dict[str, list[dict[str, Any]]]:
    value = json.loads(annotation_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Hypo3D annotation root must be an object keyed by scene ID")
    return value


def make_change_id(branch_index: int, change_type_raw: Any, context_change: Any) -> str:
    digest = hashlib.sha256(canonical_json({
        "branch_index": branch_index,
        "change_type": change_type_raw,
        "context_change": context_change,
    })).hexdigest()[:12]
    return f"change_{branch_index:04d}_{digest}"


def iter_branch_records(
    annotations: dict[str, list[dict[str, Any]]],
    *,
    scene_id: str | None = None,
    change_id: str | None = None,
    question_id: str | None = None,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    emitted = 0
    for base_scene_id in sorted(annotations):
        if scene_id is not None and base_scene_id != scene_id:
            continue
        branches = annotations[base_scene_id]
        if not isinstance(branches, list):
            raise ValueError(f"Scene {base_scene_id!r} must contain a list of branches")
        for branch_index, branch in enumerate(branches):
            if not isinstance(branch, dict):
                raise ValueError(f"Branch {base_scene_id}:{branch_index} must be an object")
            current_change_id = make_change_id(
                branch_index, branch.get("change_type"), branch.get("context_change")
            )
            if change_id is not None and current_change_id != change_id:
                continue
            qas = branch.get("questions_answers")
            if not isinstance(qas, list):
                qas = []
            for qa_index, qa in enumerate(qas):
                if not isinstance(qa, dict):
                    continue
                raw_question_id = str(qa.get("question_id", "")).strip()
                stable_question_id = raw_question_id or f"qa_index_{qa_index:04d}"
                if question_id is not None and stable_question_id != question_id:
                    continue
                source_payload = {
                    "base_scene_id": base_scene_id,
                    "branch_index": branch_index,
                    "change_type": branch.get("change_type"),
                    "context_change": branch.get("context_change"),
                    "qa_index": qa_index,
                    "qa": qa,
                }
                yield {
                    "schema_version": "hypo3d_branch_record_v2",
                    "scene_id": base_scene_id,
                    "branch_index": branch_index,
                    "change_id": current_change_id,
                    "question_id": stable_question_id,
                    "global_world_id": f"hypo3d:{base_scene_id}",
                    "branch_id": f"hypo3d:{base_scene_id}:{current_change_id}",
                    "change_type": normalize_change_type(branch.get("change_type")),
                    "context_change_raw": str(branch.get("context_change") or "").strip(),
                    "source_question_raw": str(qa.get("question") or "").strip(),
                    "source_answer_raw": str(qa.get("answer") or "").strip(),
                    "question_type": str(qa.get("question_type") or "").strip(),
                    "source_revision": SOURCE_REVISION,
                    "source_hash": object_hash(source_payload),
                    "source_field_paths": [
                        f"{base_scene_id}[{branch_index}].change_type",
                        f"{base_scene_id}[{branch_index}].context_change",
                        f"{base_scene_id}[{branch_index}].questions_answers[{qa_index}].question",
                        f"{base_scene_id}[{branch_index}].questions_answers[{qa_index}].answer",
                    ],
                    "media": {
                        "scene_id": base_scene_id,
                        "roles": [
                            "camera_view", "top_view_label", "top_view_no_label",
                            "top_view_no_label_rotated", "top_view_with_label_rotated",
                        ],
                    },
                }
                emitted += 1
                if limit is not None and emitted >= limit:
                    return


def jsonl_bytes(rows: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json(row) + b"\n" for row in rows)


def write_versioned(path: Path, payload: bytes, *, resume: bool) -> None:
    if path.exists():
        current = path.read_bytes()
        if current != payload:
            if resume:
                raise ValueError(f"Non-deterministic resume output: {path}")
            raise FileExistsError(f"Output exists: {path}; use --resume")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)

