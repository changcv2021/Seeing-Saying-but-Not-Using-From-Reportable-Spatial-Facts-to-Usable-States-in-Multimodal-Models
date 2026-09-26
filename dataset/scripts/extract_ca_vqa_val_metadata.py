from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.ipc as ipc


EXTRACT_VERSION = "ca_vqa_val_metadata_v1"
MEDIA_VALIDATOR_VERSION = "ca_vqa_val_media_v1"
TASKS = ("binary", "cardinality", "multichoice")
ID_PATTERN = re.compile(r"^(?P<capture>[^_]+)_(?P<reference>[^_]+)_(?P<qa>.+)$")
ROLES = ("reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4")


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def write_versioned(path: Path, payload: bytes, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume:
            raise FileExistsError(f"Output exists: {path}; use --resume")
        if path.read_bytes() != payload:
            raise ValueError(f"NON_DETERMINISTIC_OUTPUT:{path}")
    else:
        path.write_bytes(payload)


def safe_media_path(dataset_root: Path, relative: str) -> Path | None:
    candidate = (dataset_root / relative).resolve()
    try:
        candidate.relative_to(dataset_root.resolve())
    except ValueError:
        return None
    return candidate


def role_paths(batch: pa.RecordBatch, role: str) -> list[str | None]:
    column = batch.column(batch.schema.get_field_index(role))
    image = column.field("image")
    return image.field("path").to_pylist()


def extract_task(task: str, dataset_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str]:
    arrow_path = dataset_root / task / "data-00000-of-00001.arrow"
    if not arrow_path.exists():
        raise FileNotFoundError(f"MISSING_ARROW:{arrow_path}")
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    schema_text = ""
    with pa.memory_map(str(arrow_path), "r") as source:
        reader = ipc.open_stream(source)
        schema_text = str(reader.schema)
        required = {"id", "question", "answer", *ROLES}
        missing = sorted(required - set(reader.schema.names))
        if missing:
            raise ValueError(f"MISSING_REQUIRED_ARROW_FIELDS:{task}:{missing}")
        row_index = 0
        for batch in reader:
            ids = batch.column(batch.schema.get_field_index("id")).to_pylist()
            questions = batch.column(batch.schema.get_field_index("question")).to_pylist()
            answers = batch.column(batch.schema.get_field_index("answer")).to_pylist()
            paths_by_role = {role: role_paths(batch, role) for role in ROLES}
            for local_index, raw_id in enumerate(ids):
                source_id = str(raw_id or "")
                match = ID_PATTERN.fullmatch(source_id)
                reject_codes: list[str] = []
                if match is None:
                    reject_codes.append("MALFORMED_STABLE_ID")
                question = questions[local_index]
                answer = answers[local_index]
                if not isinstance(question, str) or not question.strip() or not isinstance(answer, str):
                    reject_codes.append("MISSING_SOURCE_FIELD")
                media_roles: dict[str, str] = {}
                for role in ROLES:
                    relative = paths_by_role[role][local_index]
                    if not isinstance(relative, str):
                        reject_codes.append("MISSING_MEDIA")
                        continue
                    resolved = safe_media_path(dataset_root, relative)
                    if resolved is None:
                        reject_codes.append("UNSAFE_MEDIA_PATH")
                    elif not resolved.is_file() or resolved.stat().st_size <= 0:
                        reject_codes.append("MISSING_MEDIA")
                    else:
                        media_roles[role] = relative
                if reject_codes:
                    rejected.append({
                        "task": task, "row_index": row_index, "source_id": source_id,
                        "reject_codes": sorted(set(reject_codes)),
                    })
                else:
                    assert match is not None
                    core = {
                        "task": task, "id": source_id, "capture_id": match.group("capture"),
                        "reference_index": match.group("reference"), "qa_index": match.group("qa"),
                        "question": question.strip(), "answer": answer.strip(), "media_roles": media_roles,
                    }
                    core["source_record_hash"] = sha256_bytes(json_bytes(core))
                    accepted.append(core)
                row_index += 1
    return accepted, rejected, str(arrow_path), schema_text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extracted-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256-file", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    dataset_root = args.extracted_root / "cavqa_val"
    project_root = args.project_root.resolve()
    output_root = project_root / "data/staging/ca_vqa" / args.source_revision / EXTRACT_VERSION
    mapping_path = project_root / "data/media_index/ca_vqa" / args.source_revision / f"{MEDIA_VALIDATOR_VERSION}.jsonl"
    reject_path = project_root / "rejected/metadata/ca_vqa" / args.source_revision / f"{EXTRACT_VERSION}.jsonl"
    report_path = project_root / "reports/ca_vqa" / f"metadata_extract.{EXTRACT_VERSION}.json"
    media_report_path = project_root / "reports/ca_vqa" / f"media_validation.{MEDIA_VALIDATOR_VERSION}.json"

    all_rows: list[dict[str, Any]] = []
    all_rejects: list[dict[str, Any]] = []
    arrow_inputs: dict[str, str] = {}
    schema_hashes: dict[str, str] = {}
    output_hashes: dict[str, str] = {}
    task_counts: Counter[str] = Counter()
    for task in TASKS:
        rows, rejects, arrow_name, schema_text = extract_task(task, dataset_root)
        if args.limit is not None:
            rows = rows[: args.limit]
        rows.sort(key=lambda row: row["id"])
        payload = b"".join(json_bytes(row) + b"\n" for row in rows)
        path = output_root / f"{task}.jsonl"
        write_versioned(path, payload, args.resume)
        output_hashes[str(path.relative_to(project_root))] = sha256_bytes(payload)
        all_rows.extend(rows)
        all_rejects.extend(rejects)
        task_counts[task] = len(rows)
        arrow_path = Path(arrow_name)
        arrow_inputs[str(arrow_path)] = sha256_file(arrow_path)
        schema_hashes[task] = sha256_bytes(schema_text.encode("utf-8"))

    mappings = []
    for row in sorted(all_rows, key=lambda item: (item["task"], item["id"])):
        source_item_id = f"ca_vqa:{row['task']}:{row['id']}"
        mappings.append({
            "source_item_id": source_item_id,
            "status": "VALID",
            "reject_codes": [],
            "resolved_global_world_id": f"arkitscenes:{row['capture_id']}",
            "media_type": "multi_view_images",
            "archive_member": row["media_roles"]["reference_frame"],
            "support_archive_members": [row["media_roles"][role] for role in ROLES[1:]],
            "frame_roles": row["media_roles"],
            "validation_scope": "ARCHIVE_HASH_AND_EXTRACTED_FILE_PRESENCE",
        })
    mapping_payload = b"".join(json_bytes(row) + b"\n" for row in mappings)
    reject_payload = b"".join(json_bytes(row) + b"\n" for row in sorted(all_rejects, key=lambda item: (item["task"], item["row_index"])))
    write_versioned(mapping_path, mapping_payload, args.resume)
    write_versioned(reject_path, reject_payload, args.resume)
    output_hashes[str(mapping_path.relative_to(project_root))] = sha256_bytes(mapping_payload)
    output_hashes[str(reject_path.relative_to(project_root))] = sha256_bytes(reject_payload)

    archive_hash_line = args.archive_sha256_file.read_text(encoding="utf-8").strip().split()[0]
    archive_hash = archive_hash_line if archive_hash_line.startswith("sha256:") else f"sha256:{archive_hash_line}"
    if args.archive.stat().st_size != 31_650_263_144:
        raise ValueError("CA_VQA_VAL_ARCHIVE_SIZE_MISMATCH")
    report = {
        "schema_version": "1.0", "dataset": "ca_vqa", "extract_version": EXTRACT_VERSION,
        "status": "VAL_METADATA_VALID" if all_rows and not all_rejects else ("PARTIAL" if all_rows else "REJECTED"),
        "source_revision": args.source_revision, "task_counts": dict(sorted(task_counts.items())),
        "accepted_record_count": len(all_rows), "rejected_record_count": len(all_rejects),
        "reject_code_counts": dict(sorted(Counter(code for row in all_rejects for code in row["reject_codes"]).items())),
        "capture_count": len({row["capture_id"] for row in all_rows}),
        "reference_frame_bundle_count": len({(row["capture_id"], row["reference_index"]) for row in all_rows}),
        "stable_id_present_in_all_accepted_records": all(bool(ID_PATTERN.fullmatch(row["id"])) for row in all_rows),
        "reference_support_roles_preserved": all(set(row["media_roles"]) == set(ROLES) for row in all_rows),
        "input_hashes": {**arrow_inputs, str(args.archive): archive_hash, str(args.archive_sha256_file): sha256_file(args.archive_sha256_file)},
        "arrow_schema_hashes": schema_hashes, "output_hashes": dict(sorted(output_hashes.items())),
        "next_gate": "CA_VQA_DETERMINISTIC_ADAPTER_PENDING",
    }
    write_versioned(report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n", args.resume)
    media_report = {
        "schema_version": "1.0", "dataset": "ca_vqa", "validator_version": MEDIA_VALIDATOR_VERSION,
        "status": "PILOT_MEDIA_VALID" if all_rows and not all_rejects else "PARTIAL",
        "source_revision": args.source_revision, "validated_source_item_count": len(mappings),
        "archive": str(args.archive), "archive_bytes": args.archive.stat().st_size, "archive_sha256": archive_hash,
        "media_validation_policy": "ARCHIVE_HASH_PATH_SAFETY_AND_EXTRACTED_FILE_PRESENCE",
        "outputs": {"mapping": str(mapping_path.relative_to(project_root))},
        "next_gate": "WORLD_ID_VALID" if all_rows and not all_rejects else "MEDIA_REJECTS_PRESENT",
    }
    write_versioned(media_report_path, json.dumps(media_report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n", args.resume)
    print(json.dumps({
        "status": report["status"], "accepted_record_count": len(all_rows),
        "rejected_record_count": len(all_rejects), "capture_count": report["capture_count"],
        "next_gate": report["next_gate"],
    }, sort_keys=True))
    return 0 if report["status"] == "VAL_METADATA_VALID" else 2


if __name__ == "__main__":
    raise SystemExit(main())
