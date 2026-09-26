from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.ipc as ipc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def serializable(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"bytes_length": len(value)}
    if isinstance(value, dict):
        return {key: serializable(item) for key, item in value.items() if key not in {"bytes", "array"}}
    if isinstance(value, list):
        return [serializable(item) for item in value[:8]]
    return value


def first_text_row(path: Path) -> tuple[str, dict[str, Any]]:
    with pa.memory_map(str(path), "r") as source:
        reader = ipc.open_stream(source)
        schema = str(reader.schema)
        batch = reader.read_next_batch()
        keep = [name for name in ("id", "question", "answer", "reference_frame") if name in batch.schema.names]
        if not keep:
            return schema, {}
        row = batch.select(keep).slice(0, 1).to_pylist()[0]
        return schema, serializable(row)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extracted-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    arrows = sorted(args.extracted_root.rglob("*.arrow"))
    json_files = sorted(args.extracted_root.rglob("*.json"))
    if not arrows:
        raise RuntimeError("NO_ARROW_FILES_IN_VAL_ARCHIVE")
    profiles = []
    seen_parents = set()
    for path in arrows:
        parent = str(path.parent)
        if parent in seen_parents:
            continue
        seen_parents.add(parent)
        schema, first_row = first_text_row(path)
        profiles.append({
            "relative_path": str(path.relative_to(args.extracted_root)), "bytes": path.stat().st_size,
            "arrow_schema": schema, "first_text_row": first_row,
        })
    report = {
        "schema_version": "1.0", "dataset": "ca_vqa", "profile_version": "ca_vqa_val_profile_v1",
        "status": "PROFILED", "source_revision": "080812355c21a40f437ed03d4ae558d35bfa2929",
        "archive": str(args.archive), "archive_bytes": args.archive.stat().st_size,
        "archive_sha256": sha256(args.archive), "inventory": str(args.inventory), "inventory_sha256": sha256(args.inventory),
        "arrow_file_count": len(arrows), "json_metadata_file_count": len(json_files),
        "dataset_profiles": profiles,
        "stable_id_present_in_all_profiled_datasets": bool(profiles) and all("id" in item["first_text_row"] for item in profiles),
        "next_gate": "CA_VQA_VAL_ADAPTER_PILOT_PENDING",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output.exists() and args.output.read_text() != payload:
        raise ValueError(f"NON_DETERMINISTIC_OUTPUT:{args.output}")
    args.output.write_text(payload)
    print(json.dumps({key: report[key] for key in ("status", "arrow_file_count", "json_metadata_file_count", "stable_id_present_in_all_profiled_datasets", "next_gate")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
