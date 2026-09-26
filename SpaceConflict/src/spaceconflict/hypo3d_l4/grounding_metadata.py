from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterator, TextIO

from jsonschema import Draft202012Validator

from ..hashing import sha256_file
from ..registry import ROOT
from .common import load_annotations, write_versioned


GROUNDING_AUDITOR_VERSION = "hypo3d_grounding_auditor_v2_1"


def _read_more(handle: TextIO, buffer: str, *, chunk_size: int) -> tuple[str, bool]:
    chunk = handle.read(chunk_size)
    return buffer + chunk, not chunk


def iter_top_level_object(
    path: Path, *, chunk_size: int = 1024 * 1024,
) -> Iterator[tuple[str, Any]]:
    """Stream a JSON object one top-level value at a time."""
    decoder = json.JSONDecoder()
    with path.open("r", encoding="utf-8") as handle:
        buffer = ""
        position = 0
        eof = False

        def ensure_content() -> None:
            nonlocal buffer, eof
            while position >= len(buffer) and not eof:
                buffer, eof = _read_more(handle, buffer, chunk_size=chunk_size)

        def skip_space() -> None:
            nonlocal position, buffer, eof
            while True:
                ensure_content()
                while position < len(buffer) and buffer[position].isspace():
                    position += 1
                if position < len(buffer) or eof:
                    return
                buffer, eof = _read_more(handle, buffer, chunk_size=chunk_size)

        def decode_next() -> tuple[Any, int]:
            nonlocal buffer, eof
            while True:
                try:
                    return decoder.raw_decode(buffer, position)
                except json.JSONDecodeError:
                    if eof:
                        raise
                    buffer, eof = _read_more(handle, buffer, chunk_size=chunk_size)

        skip_space()
        if position >= len(buffer) or buffer[position] != "{":
            raise ValueError("Grounding metadata root must be a JSON object")
        position += 1
        while True:
            skip_space()
            if position < len(buffer) and buffer[position] == "}":
                position += 1
                break
            key, position = decode_next()
            if not isinstance(key, str):
                raise ValueError("Grounding metadata scene key must be a string")
            skip_space()
            if position >= len(buffer) or buffer[position] != ":":
                raise ValueError(f"Missing ':' after scene key {key!r}")
            position += 1
            skip_space()
            value, position = decode_next()
            yield key, value
            # Drop the decoded scene so peak memory is bounded by one scene.
            buffer = buffer[position:]
            position = 0
            skip_space()
            if position < len(buffer) and buffer[position] == ",":
                position += 1
                continue
            if position < len(buffer) and buffer[position] == "}":
                position += 1
                break
            raise ValueError(f"Expected ',' or '}}' after scene {key!r}")
        skip_space()
        if position != len(buffer) or not eof:
            remainder = buffer[position:] + handle.read()
            if remainder.strip():
                raise ValueError("Unexpected trailing content in grounding metadata")


def _valid_pose(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(
            isinstance(row, list)
            and len(row) == 4
            and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in row)
            for row in value
        )
    )


def _representative_frames(frames: dict[str, Any]) -> list[dict[str, Any]]:
    paths = sorted(frames)
    if not paths:
        return []
    result = []
    for index in sorted({0, len(paths) // 2, len(paths) - 1}):
        rgb_path = paths[index]
        record = frames[rgb_path] if isinstance(frames[rgb_path], dict) else {}
        result.append({
            "rgb_path": rgb_path,
            "depth_path": record.get("depth"),
            "pose": record.get("pose"),
        })
    return result


def audit_grounding_metadata(
    *, metadata_path: Path, annotation_path: Path, output_dir: Path,
    dry_run: bool, resume: bool,
) -> dict[str, Any]:
    output_path = output_dir / "grounding_inventory.v2_1.json"
    if dry_run:
        return {
            "status": "PLANNED", "action": "audit-grounding",
            "metadata": str(metadata_path), "annotation": str(annotation_path),
            "output": str(output_path),
        }
    if not metadata_path.is_file():
        return {
            "status": "BLOCKED_SOURCE", "action": "audit-grounding",
            "reason": "GROUNDING_METADATA_MISSING", "input": str(metadata_path),
        }
    selected = set(load_annotations(annotation_path))
    covered: dict[str, dict[str, Any]] = {}
    source_types: Counter[str] = Counter()
    total_source_scenes = 0
    for source_scene_id, raw_frames in iter_top_level_object(metadata_path):
        total_source_scenes += 1
        source_type = source_scene_id.split("/", 1)[0] if "/" in source_scene_id else "unknown"
        source_types[source_type] += 1
        scene_id = source_scene_id.rsplit("/", 1)[-1]
        if scene_id not in selected:
            continue
        if not isinstance(raw_frames, dict):
            raise ValueError(f"Grounding scene {source_scene_id!r} must map frame paths to records")
        frames = {
            str(key): value for key, value in raw_frames.items()
            if Path(str(key)).suffix.casefold() in {".jpg", ".jpeg", ".png"}
        }
        pose_count = sum(
            isinstance(value, dict) and _valid_pose(value.get("pose"))
            for value in frames.values()
        )
        depth_count = sum(
            isinstance(value, dict) and isinstance(value.get("depth"), str) and bool(value["depth"])
            for value in frames.values()
        )
        covered[scene_id] = {
            "source_scene_id": source_scene_id,
            "frame_count": len(frames),
            "valid_pose_count": pose_count,
            "depth_path_count": depth_count,
            "representative_frames": _representative_frames(frames),
        }
    missing = sorted(selected - covered.keys())
    malformed = sorted(
        scene_id for scene_id, row in covered.items()
        if row["frame_count"] == 0
        or row["valid_pose_count"] != row["frame_count"]
        or row["depth_path_count"] != row["frame_count"]
    )
    inventory = {
        "schema_version": "hypo3d_grounding_inventory_v2_1",
        "auditor_version": GROUNDING_AUDITOR_VERSION,
        "status": "GROUNDING_AUDITED" if not missing and not malformed else "GROUNDING_COVERAGE_INCOMPLETE",
        "truth_boundary": "FRAME_DEPTH_POSE_GROUNDING_ONLY_NOT_OBJECT_OR_TRANSITION_TRUTH",
        "metadata_path": str(metadata_path),
        "metadata_bytes": metadata_path.stat().st_size,
        "metadata_sha256": sha256_file(metadata_path),
        "total_source_scene_count": total_source_scenes,
        "source_type_distribution": dict(sorted(source_types.items())),
        "requested_scene_count": len(selected),
        "covered_scene_count": len(covered),
        "missing_scene_ids": missing,
        "malformed_scene_ids": malformed,
        "scenes": dict(sorted(covered.items())),
    }
    schema = json.loads((ROOT / "schemas/hypo3d_grounding_inventory.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(inventory)
    payload = (json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    write_versioned(output_path, payload, resume=resume)
    return {
        "status": inventory["status"], "action": "audit-grounding",
        "total_source_scene_count": total_source_scenes,
        "requested_scene_count": len(selected), "covered_scene_count": len(covered),
        "missing_scene_count": len(missing), "malformed_scene_count": len(malformed),
        "output": str(output_path),
        "input_hashes": {
            str(metadata_path): inventory["metadata_sha256"],
            str(annotation_path): sha256_file(annotation_path),
        },
        "output_hashes": {str(output_path): sha256_file(output_path)},
    }
