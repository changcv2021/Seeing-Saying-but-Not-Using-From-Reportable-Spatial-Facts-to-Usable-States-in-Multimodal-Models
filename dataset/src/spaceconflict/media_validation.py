from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import tarfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

import pyarrow.dataset as pads
from PIL import Image

from .adapters.pipeline import ADAPTER_VERSIONS
from .hashing import sha256_file
from .profiling.profile import REVISIONS
from .registry import ROOT


DEFAULT_STORAGE_ROOT = Path("external/upstream")
VALIDATOR_VERSION = "media_validator_v1"


def _load_candidates(dataset: str, root: Path) -> list[dict[str, Any]]:
    path = (
        root / "data" / "staging" / "adapters" / dataset / REVISIONS[dataset]
        / ADAPTER_VERSIONS[dataset] / "fact_candidates.jsonl"
    )
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _recorded_hashes(paths: list[Path]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            header = next(handle).rstrip("\n").split("\t")
            for line in handle:
                row = dict(zip(header, line.rstrip("\n").split("\t")))
                local_path = row.get("local_path") or row.get("destination")
                digest = row.get("sha256") or row.get("content_sha256")
                if local_path and digest and digest != "NOT_COMPUTED":
                    result[local_path] = f"sha256:{digest.removeprefix('sha256:')}"
    return result


def _zip_inventory(archive: Path) -> tuple[list[dict[str, Any]], str | None]:
    rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(archive) as handle:
        for item in handle.infolist():
            if not item.is_dir():
                rows.append({
                    "archive": str(archive), "member": item.filename,
                    "compressed_bytes": item.compress_size, "uncompressed_bytes": item.file_size,
                    "crc32": f"{item.CRC:08x}",
                })
        bad_member = handle.testzip()
    return rows, bad_member


def _match_path(members: list[str], expected: str) -> tuple[str | None, str | None]:
    normalized = expected.lstrip("/")
    matches = [name for name in members if name == normalized or name.endswith("/" + normalized)]
    if not matches:
        basename = PurePosixPath(normalized).name
        matches = [name for name in members if PurePosixPath(name).name == basename]
    if len(matches) == 1:
        return matches[0], None
    return None, "MEDIA_MEMBER_NOT_FOUND" if not matches else "AMBIGUOUS_MEDIA_MEMBER"


def _match_scene(members: list[str], scene: str) -> tuple[str | None, str | None]:
    matches = [name for name in members if PurePosixPath(name).stem == scene]
    if len(matches) == 1:
        return matches[0], None
    return None, "MEDIA_MEMBER_NOT_FOUND" if not matches else "AMBIGUOUS_MEDIA_MEMBER"


def _extract(archive: Path, member: str, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        partial = destination.with_suffix(destination.suffix + ".part")
        with zipfile.ZipFile(archive) as handle, handle.open(member) as source, partial.open("wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
        partial.replace(destination)
        destination.chmod(0o400)
    return sha256_file(destination)


def _ffprobe(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,size:stream=index,codec_type,codec_name,width,height,avg_frame_rate,nb_frames",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        return None, "VIDEO_PROBE_FAILED"
    payload = json.loads(result.stdout)
    duration_text = payload.get("format", {}).get("duration")
    duration = float(duration_text) if duration_text not in {None, "N/A"} else None
    return {
        "duration_seconds": duration,
        "container_bytes": int(payload.get("format", {}).get("size", path.stat().st_size)),
        "streams": payload.get("streams", []),
    }, None


def _save(
    dataset: str, run_id: str, report: dict[str, Any], mappings: list[dict[str, Any]],
    inventory: list[dict[str, Any]], root: Path,
) -> dict[str, Any]:
    report_dir = root / "reports" / dataset
    mapping_path = report_dir / f"media_mapping.{run_id}.jsonl"
    inventory_path = report_dir / f"media_inventory.{run_id}.jsonl"
    report_path = report_dir / f"media_validation.{run_id}.json"
    _write_jsonl(mapping_path, mappings)
    _write_jsonl(inventory_path, inventory)
    report["outputs"] = {
        "mapping": str(mapping_path.relative_to(root)), "mapping_sha256": sha256_file(mapping_path),
        "inventory": str(inventory_path.relative_to(root)), "inventory_sha256": sha256_file(inventory_path),
    }
    _write_json(report_path, report)
    return {**report, "report": str(report_path.relative_to(root)), "report_sha256": sha256_file(report_path)}


def _validate_sti(storage_root: Path, root: Path, run_id: str, limit: int) -> dict[str, Any]:
    revision = REVISIONS["sti_bench"]
    archive = storage_root / "data/pilot_media_incoming/sti_bench" / revision / "video.zip"
    candidates = _load_candidates("sti_bench", root)
    inventory, bad_member = _zip_inventory(archive)
    members = [row["member"] for row in inventory]
    expected_paths = sorted({item["media_locator"]["relative_path"] for item in candidates})
    selected = set(expected_paths[:limit])
    staging = storage_root / "data/staging/media_pilot/sti_bench" / revision / VALIDATOR_VERSION
    details: dict[str, dict[str, Any]] = {}
    failures: Counter[str] = Counter()
    for expected in expected_paths:
        member, error = _match_path(members, expected)
        detail: dict[str, Any] = {"archive_member": member, "selected": expected in selected, "reject_codes": []}
        if error:
            detail["reject_codes"] = [error]
            failures[error] += 1
        elif expected in selected and member:
            destination = staging / PurePosixPath(member).name
            detail["sha256"] = _extract(archive, member, destination)
            detail["extracted_path"] = str(destination)
            detail["probe"], error = _ffprobe(destination)
            if error:
                detail["reject_codes"] = [error]
                failures[error] += 1
        details[expected] = detail
    mappings: list[dict[str, Any]] = []
    for item in candidates:
        locator = item["media_locator"]
        detail = details[locator["relative_path"]]
        reject_codes = list(detail["reject_codes"])
        duration = (detail.get("probe") or {}).get("duration_seconds")
        if detail["selected"] and duration is not None and float(locator["time_end"]) > duration + 0.05:
            reject_codes.append("TIME_SCOPE_OUT_OF_RANGE")
            failures["TIME_SCOPE_OUT_OF_RANGE"] += 1
        mappings.append({
            "source_item_id": item["source_item_id"], "global_world_id": item["global_world_id"],
            "media_locator": locator, "archive_member": detail["archive_member"],
            "selected_for_pilot": detail["selected"],
            "status": "VALID" if not reject_codes else "REJECTED", "reject_codes": reject_codes,
        })
    if bad_member:
        failures["ARCHIVE_CRC_FAILURE"] += 1
    valid = sum(item["status"] == "VALID" for item in mappings)
    report = {
        "schema_version": "1.0", "validator_version": VALIDATOR_VERSION,
        "dataset": "sti_bench", "source_revision": revision,
        "candidate_count": len(candidates), "resolved_candidate_count": valid,
        "missing_media_rate": 1 - valid / len(candidates), "unique_candidate_media": len(expected_paths),
        "pilot_world_limit": limit, "pilot_media_selected": len(selected),
        "archive_crc_status": "PASS" if not bad_member else "FAIL",
        "failure_counts": dict(sorted(failures.items())),
        "input_hashes": _recorded_hashes([root / "runs/stage_pilot_slurm_8073074/results.tsv"]),
        "status": "PILOT_MEDIA_VALID" if not failures and valid == len(candidates) else "FAIL",
    }
    return _save("sti_bench", run_id, report, mappings, inventory, root)


def _validate_hypo3d(
    storage_root: Path, root: Path, run_id: str, limit: int,
) -> dict[str, Any]:
    revision = REVISIONS["hypo3d"]
    media_root = storage_root / "data/full_media_incoming/hypo3d" / revision
    candidates = _load_candidates("hypo3d", root)
    worlds = sorted({item["global_world_id"] for item in candidates})
    selected_worlds = set(worlds[:limit])
    locators: dict[str, dict[str, str]] = {}
    for item in candidates:
        locators.setdefault(item["global_world_id"], item["media_locator"]["media_roles"])
    world_details: dict[str, dict[str, Any]] = {}
    inventory: list[dict[str, Any]] = []
    failures: Counter[str] = Counter()
    for world_id, roles in sorted(locators.items()):
        reject_codes: list[str] = []
        resolved = {role: media_root / relative for role, relative in roles.items()}
        for role, path in resolved.items():
            if not path.is_file():
                reject_codes.append("MEDIA_FILE_NOT_FOUND")
                continue
            if world_id not in selected_worlds:
                continue
            try:
                with Image.open(path) as image:
                    image.verify()
                with Image.open(path) as image:
                    width, height = image.size
                    image_format = image.format
                inventory.append({
                    "global_world_id": world_id,
                    "role": role,
                    "relative_path": roles[role],
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "width": width,
                    "height": height,
                    "format": image_format,
                })
            except Exception:
                reject_codes.append("IMAGE_DECODE_FAILED")
        for code in set(reject_codes):
            failures[code] += 1
        world_details[world_id] = {
            "media_roles": roles,
            "selected_for_pilot": world_id in selected_worlds,
            "status": "VALID" if not reject_codes else "REJECTED",
            "reject_codes": sorted(set(reject_codes)),
        }
    mappings = []
    for item in candidates:
        detail = world_details[item["global_world_id"]]
        mappings.append({
            "source_item_id": item["source_item_id"],
            "global_world_id": item["global_world_id"],
            "media_locator": item["media_locator"],
            "media_roles": detail["media_roles"],
            "selected_for_pilot": detail["selected_for_pilot"],
            "validation_scope": "decoded_pilot" if detail["selected_for_pilot"] else "file_presence",
            "status": detail["status"],
            "reject_codes": detail["reject_codes"],
        })
    valid = sum(item["status"] == "VALID" for item in mappings)
    annotation = root / "data/raw/hypo3d" / revision / "hypo3d.json"
    download_results = root / "runs/download_hypo3d_slurm_8073072/results.tsv"
    report = {
        "schema_version": "1.0",
        "validator_version": VALIDATOR_VERSION,
        "dataset": "hypo3d",
        "source_revision": revision,
        "candidate_count": len(candidates),
        "resolved_candidate_count": valid,
        "world_count": len(worlds),
        "pilot_world_limit": limit,
        "pilot_worlds_selected": len(selected_worlds),
        "decoded_pilot_images": len(inventory),
        "missing_media_rate": 1 - valid / (len(candidates) or 1),
        "failure_counts": dict(sorted(failures.items())),
        "input_hashes": {
            str(annotation): sha256_file(annotation),
            **_recorded_hashes([download_results]),
        },
        "status": "PILOT_MEDIA_VALID" if not failures and valid == len(candidates) else "FAIL",
        "next_gate": "CANONICAL_READY" if not failures and valid == len(candidates) else "BLOCKED_MEDIA",
    }
    return _save("hypo3d", run_id, report, mappings, inventory, root)


def _validate_vsi(storage_root: Path, root: Path, run_id: str, limit: int) -> dict[str, Any]:
    revision = REVISIONS["vsi_bench"]
    media_root = storage_root / "data/pilot_media_incoming/vsi_bench" / revision
    candidates = _load_candidates("vsi_bench", root)
    archive_names = ["arkitscenes.zip", "scannet.zip", "scannetpp.zip"]
    inventory: list[dict[str, Any]] = []
    members: dict[str, list[str]] = {}
    failures: Counter[str] = Counter()
    for name in archive_names:
        rows, bad_member = _zip_inventory(media_root / name)
        inventory.extend(rows)
        members[name] = [row["member"] for row in rows]
        if bad_member:
            failures[f"ARCHIVE_CRC_FAILURE:{name}"] += 1
    pilot_archive = "scannetpp.zip"
    selected = set(sorted({
        str(item["media_locator"]["scene_name"]) for item in candidates
        if item["media_locator"]["archive"] == pilot_archive
    })[:limit])
    staging = storage_root / "data/staging/media_pilot/vsi_bench" / revision / VALIDATOR_VERSION
    details: dict[tuple[str, str], dict[str, Any]] = {}
    for item in candidates:
        archive_name = item["media_locator"]["archive"]
        scene = str(item["media_locator"]["scene_name"])
        key = (archive_name, scene)
        if key in details:
            continue
        member, error = _match_scene(members[archive_name], scene)
        is_selected = archive_name == pilot_archive and scene in selected
        detail: dict[str, Any] = {"archive_member": member, "selected": is_selected, "reject_codes": []}
        if error:
            detail["reject_codes"] = [error]
            failures[error] += 1
        elif is_selected and member:
            destination = staging / scene / PurePosixPath(member).name
            detail["sha256"] = _extract(media_root / archive_name, member, destination)
            detail["extracted_path"] = str(destination)
            detail["probe"], error = _ffprobe(destination)
            if error:
                detail["reject_codes"] = [error]
                failures[error] += 1
        details[key] = detail
    mappings = []
    for item in candidates:
        archive_name = item["media_locator"]["archive"]
        scene = str(item["media_locator"]["scene_name"])
        detail = details[(archive_name, scene)]
        mappings.append({
            "source_item_id": item["source_item_id"], "global_world_id": item["global_world_id"],
            "media_locator": item["media_locator"], "archive_member": detail["archive_member"],
            "selected_for_pilot": detail["selected"],
            "status": "VALID" if not detail["reject_codes"] else "REJECTED",
            "reject_codes": detail["reject_codes"],
        })
    valid = sum(item["status"] == "VALID" for item in mappings)
    report = {
        "schema_version": "1.0", "validator_version": VALIDATOR_VERSION,
        "dataset": "vsi_bench", "source_revision": revision,
        "candidate_count": len(candidates), "resolved_candidate_count": valid,
        "missing_media_rate": 1 - valid / len(candidates), "unique_candidate_worlds": len(details),
        "pilot_source_archive": pilot_archive, "pilot_world_limit": limit,
        "pilot_media_selected": len(selected), "archive_crc_status": "PASS" if not failures else "FAIL",
        "failure_counts": dict(sorted(failures.items())),
        "input_hashes": _recorded_hashes([
            root / "runs/download_vsi_bench_slurm_8073071/results.tsv",
            root / "runs/stage_pilot_slurm_8073074/results.tsv",
        ]),
        "status": "PILOT_MEDIA_VALID" if not failures and valid == len(candidates) else "FAIL",
    }
    return _save("vsi_bench", run_id, report, mappings, inventory, root)


def _validate_omnispatial(storage_root: Path, root: Path, run_id: str, limit: int) -> dict[str, Any]:
    revision = REVISIONS["omnispatial"]
    archive = storage_root / "data/full_media_incoming/omnispatial" / revision / "OmniSpatial-full.zip"
    candidates = _load_candidates("omnispatial", root)
    inventory, bad_member = _zip_inventory(archive)
    supported_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".avi", ".gif"}
    members_by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in inventory:
        path = PurePosixPath(row["member"])
        if row["member"].startswith("__MACOSX/") or path.suffix.casefold() not in supported_suffixes:
            continue
        if len(path.parts) >= 3:
            members_by_key[(path.parts[-2], path.stem)].append(row["member"])
    world_keys = sorted({
        (str(item["media_locator"]["task_type"]), str(item["media_locator"]["item_id"]))
        for item in candidates
    })
    selected = set(world_keys[:limit])
    staging = storage_root / "data/staging/media_pilot/omnispatial" / revision / VALIDATOR_VERSION
    details: dict[tuple[str, str], dict[str, Any]] = {}
    failures: Counter[str] = Counter()
    pilot_type_counts: Counter[str] = Counter()
    for key in world_keys:
        matches = members_by_key.get(key, [])
        detail: dict[str, Any] = {"selected": key in selected, "reject_codes": []}
        if len(matches) != 1:
            code = "MEDIA_MEMBER_NOT_FOUND" if not matches else "AMBIGUOUS_MEDIA_MEMBER"
            detail.update({"archive_member": None, "reject_codes": [code]})
            failures[code] += 1
        else:
            member = matches[0]
            suffix = PurePosixPath(member).suffix.casefold()
            media_type = "video" if suffix in {".mp4", ".mov", ".avi", ".gif"} else "image"
            detail.update({"archive_member": member, "media_type": media_type})
            if key in selected:
                destination = staging / key[0] / PurePosixPath(member).name
                detail["sha256"] = _extract(archive, member, destination)
                detail["extracted_path"] = str(destination)
                if media_type == "image":
                    try:
                        with Image.open(destination) as image:
                            image.verify()
                        with Image.open(destination) as image:
                            detail["probe"] = {
                                "width": image.width, "height": image.height, "format": image.format,
                            }
                    except Exception:
                        detail["reject_codes"].append("IMAGE_DECODE_FAILED")
                        failures["IMAGE_DECODE_FAILED"] += 1
                else:
                    detail["probe"], error = _ffprobe(destination)
                    if error:
                        detail["reject_codes"].append(error)
                        failures[error] += 1
                pilot_type_counts[media_type] += 1
        details[key] = detail
    mappings = []
    for item in candidates:
        locator = item["media_locator"]
        key = (str(locator["task_type"]), str(locator["item_id"]))
        detail = details[key]
        mappings.append({
            "source_item_id": item["source_item_id"], "global_world_id": item["global_world_id"],
            "media_locator": locator, "archive_member": detail.get("archive_member"),
            "media_type": detail.get("media_type"), "selected_for_pilot": detail["selected"],
            "status": "VALID" if not detail["reject_codes"] else "REJECTED",
            "reject_codes": detail["reject_codes"],
        })
    if bad_member:
        failures["ARCHIVE_CRC_FAILURE"] += 1
    valid = sum(row["status"] == "VALID" for row in mappings)
    report = {
        "schema_version": "1.0", "validator_version": VALIDATOR_VERSION,
        "dataset": "omnispatial", "source_revision": revision,
        "candidate_count": len(candidates), "resolved_candidate_count": valid,
        "missing_media_rate": 1 - valid / len(candidates), "unique_candidate_worlds": len(world_keys),
        "pilot_world_limit": limit, "pilot_media_selected": len(selected),
        "pilot_media_type_counts": dict(sorted(pilot_type_counts.items())),
        "archive_crc_status": "PASS" if not bad_member else "FAIL",
        "failure_counts": dict(sorted(failures.items())),
        "input_hashes": _recorded_hashes([root / "runs/download_omnispatial_slurm_8073073/results.tsv"]),
        "status": "PILOT_MEDIA_VALID" if not failures and valid == len(candidates) else "FAIL",
    }
    return _save("omnispatial", run_id, report, mappings, inventory, root)


def _image_bytes(value: Any) -> bytes | None:
    if isinstance(value, bytes):
        return value
    if isinstance(value, dict) and isinstance(value.get("bytes"), bytes):
        return value["bytes"]
    return None


def _scan_spar_annotation_archive(
    archive: Path, targets: set[tuple[str, str]],
) -> tuple[dict[tuple[str, str], dict[str, Any]], set[tuple[str, str]]]:
    matches: dict[tuple[str, str], dict[str, Any]] = {}
    ambiguous: set[tuple[str, str]] = set()
    with tarfile.open(archive, "r:gz") as handle:
        for member in handle:
            if not member.isfile() or not member.name.endswith(".jsonl"):
                continue
            stream = handle.extractfile(member)
            if stream is None:
                continue
            for payload in stream:
                try:
                    row = json.loads(payload)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                question = row.get("question")
                answer = row.get("answer")
                if question is None and isinstance(row.get("conversations"), list):
                    turns = row["conversations"]
                    question = turns[0].get("value") if turns else None
                    answer = turns[1].get("value") if len(turns) > 1 else None
                key = (str(question), str(answer))
                if key not in targets:
                    continue
                source_row = {
                    "id": row.get("id"), "question": question, "answer": answer,
                    "image": row.get("image") or row.get("images") or [],
                    "annotation_archive_member": member.name,
                }
                previous = matches.get(key)
                if previous is not None and previous.get("image") != source_row.get("image"):
                    ambiguous.add(key)
                else:
                    matches[key] = source_row
    return matches, ambiguous


def _validate_spar(storage_root: Path, root: Path, run_id: str, limit: int) -> dict[str, Any]:
    revision = "ee122877c25c8bb08539b07e06d872152c9968f1"
    shard_root = storage_root / "data/full_media_incoming/spar" / revision / "SPAR-Bench/data"
    shards = sorted(shard_root.glob("*.parquet"))
    candidates = _load_candidates("spar", root)
    candidate_ids = {str(item["media_locator"]["row_id"]) for item in candidates}
    sampled_payload = json.loads((
        root / "data/raw/spar/ae9bbc5297fd277123c42b0628d1f40bf72f89f1"
        / "filtered_obj_spatial_relation_oc_mv.json"
    ).read_text(encoding="utf-8"))
    sampled_rows = {str(item["row"]["id"]): item["row"] for item in sampled_payload["rows"]}
    sampled_keys = {
        (row["question"], str(row["answer"]), row["task"]): sampled_id
        for sampled_id, row in sampled_rows.items()
    }
    parquet = pads.dataset([str(path) for path in shards], format="parquet")
    required = {"id", "image", "task", "question", "answer", "source"}
    if not required.issubset(parquet.schema.names):
        raise ValueError(f"SPAR schema missing {sorted(required - set(parquet.schema.names))}")
    table = parquet.to_table(
        columns=["id", "image", "task", "question", "answer", "source"],
        filter=pads.field("task") == "obj_spatial_relation_oc_mv",
    )
    rows: dict[str, dict[str, Any]] = {}
    ambiguous_keys: set[tuple[str, str, str]] = set()
    for row in table.to_pylist():
        key = (row["question"], str(row["answer"]), row["task"])
        sampled_id = sampled_keys.get(key)
        if sampled_id is None:
            continue
        if sampled_id in rows:
            ambiguous_keys.add(key)
        else:
            rows[sampled_id] = row
    training_parquet = (
        storage_root / "data/full_media_incoming/spar"
        / "0fe664cbada1e7c1173fd743e0f781882eebf777/SPAR-7M/spar-dataset-train.parquet"
    )
    source_matches: dict[tuple[str, str], dict[str, Any]] = {}
    source_ambiguous: set[tuple[str, str]] = set()
    target_qa = {(row["question"], str(row["answer"])) for row in sampled_rows.values()}
    if training_parquet.exists():
        training = pads.dataset(str(training_parquet), format="parquet")
        scanner = training.scanner(
            columns=["id", "qa_type", "image", "question", "answer"],
            filter=pads.field("qa_type") == "obj_spatial_relation_oc_mv",
            batch_size=8192,
        )
        for batch in scanner.to_batches():
            for source_row in batch.to_pylist():
                key = (source_row["question"], str(source_row["answer"]))
                if key not in target_qa:
                    continue
                previous = source_matches.get(key)
                if previous is not None and previous.get("image") != source_row.get("image"):
                    source_ambiguous.add(key)
                else:
                    source_matches[key] = source_row
    unresolved_targets = target_qa - set(source_matches)
    annotation_archive = (
        storage_root / "data/full_media_incoming/spar"
        / "0fe664cbada1e7c1173fd743e0f781882eebf777/SPAR-7M/scannet.tar.gz"
    )
    if unresolved_targets and annotation_archive.exists():
        archive_matches, archive_ambiguous = _scan_spar_annotation_archive(
            annotation_archive, unresolved_targets,
        )
        source_matches.update(archive_matches)
        source_ambiguous.update(archive_ambiguous)
    selected = set(sorted(candidate_ids, key=int)[:limit])
    staging = storage_root / "data/staging/media_pilot/spar" / revision / VALIDATOR_VERSION
    mappings: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []
    failures: Counter[str] = Counter()
    for item in candidates:
        row_id = str(item["media_locator"]["row_id"])
        row = rows.get(row_id)
        reject_codes: list[str] = []
        images = row.get("image") if row else None
        source_key = (row["question"], str(row["answer"])) if row else None
        source_row = source_matches.get(source_key) if source_key else None
        source_image_paths = list(source_row.get("image") or []) if source_row else []
        scene_ids = sorted({
            match.group(1)
            for path in source_image_paths
            if (match := re.search(r"(scene\d{4}_\d{2})", str(path)))
        })
        resolved_world_id = f"scannet:{scene_ids[0]}" if len(scene_ids) == 1 else None
        if row is None:
            reject_codes.append("MEDIA_ROW_NOT_FOUND")
        elif (row["question"], str(row["answer"]), row["task"]) in ambiguous_keys:
            reject_codes.append("AMBIGUOUS_SOURCE_ROW_MATCH")
        elif row.get("task") != item["source_task"]:
            reject_codes.append("SOURCE_TASK_MISMATCH")
        elif not isinstance(images, list) or len(images) != int(item["media_locator"]["view_count"]):
            reject_codes.append("MEDIA_VIEW_COUNT_MISMATCH")
        if not reject_codes and row_id in selected:
            for index, value in enumerate(images or []):
                payload = _image_bytes(value)
                if payload is None:
                    reject_codes.append("MEDIA_BYTES_MISSING")
                    continue
                try:
                    with Image.open(io.BytesIO(payload)) as image:
                        image.verify()
                    with Image.open(io.BytesIO(payload)) as image:
                        width, height, image_format = *image.size, image.format
                    suffix = ".jpg" if image_format == "JPEG" else f".{str(image_format).lower()}"
                    destination = staging / row_id / f"view_{index:02d}{suffix}"
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if not destination.exists():
                        destination.write_bytes(payload)
                        destination.chmod(0o400)
                    inventory.append({
                        "row_id": row_id, "view_index": index, "width": width, "height": height,
                        "format": image_format, "bytes": len(payload),
                        "sha256": f"sha256:{hashlib.sha256(payload).hexdigest()}",
                        "extracted_path": str(destination),
                    })
                except Exception:
                    reject_codes.append("IMAGE_DECODE_FAILED")
        for code in set(reject_codes):
            failures[code] += 1
        mappings.append({
            "source_item_id": item["source_item_id"], "global_world_id": item["global_world_id"],
            "media_locator": item["media_locator"], "selected_for_pilot": row_id in selected,
            "full_benchmark_row_id": row.get("id") if row else None,
            "underlying_source": row.get("source") if row else None,
            "spar7m_annotation_id": source_row.get("id") if source_row else None,
            "spar7m_annotation_archive_member": source_row.get("annotation_archive_member") if source_row else None,
            "source_image_paths": source_image_paths,
            "resolved_global_world_id": resolved_world_id,
            "world_id_resolution_status": (
                "AMBIGUOUS" if source_key in source_ambiguous else
                ("RESOLVED" if resolved_world_id else "UNRESOLVED")
            ),
            "resolved_view_count": len(images or []) if row else 0,
            "status": "VALID" if not reject_codes else "REJECTED", "reject_codes": sorted(set(reject_codes)),
        })
    valid = sum(item["status"] == "VALID" for item in mappings)
    resolved_worlds = sum(item["world_id_resolution_status"] == "RESOLVED" for item in mappings)
    report = {
        "schema_version": "1.0", "validator_version": VALIDATOR_VERSION,
        "dataset": "spar", "source_revision": revision,
        "candidate_count": len(candidates), "resolved_candidate_count": valid,
        "missing_media_rate": 1 - valid / len(candidates), "pilot_world_limit": limit,
        "pilot_media_selected": len(selected), "decoded_pilot_views": len(inventory),
        "resolved_world_id_count": resolved_worlds,
        "failure_counts": dict(sorted(failures.items())),
        "input_hashes": _recorded_hashes([root / "runs/download_spar_slurm_8073070/results.tsv"]),
        "status": "PILOT_MEDIA_VALID" if not failures and valid == len(candidates) else "FAIL",
        "next_gate": "WORLD_ID_VALID" if resolved_worlds == len(candidates) else "BLOCKED_UNRESOLVED_WORLD_ID",
    }
    return _save("spar", run_id, report, mappings, inventory, root)


def validate_media(
    dataset: str, *, dry_run: bool, resume: bool, run_id: str, limit: int | None,
    storage_root: Path = DEFAULT_STORAGE_ROOT, root: Path = ROOT,
) -> dict[str, Any]:
    if dataset not in {"sti_bench", "vsi_bench", "spar", "omnispatial", "hypo3d"}:
        return {"dataset": dataset, "status": "BLOCKED_SOURCE", "reason": "MEDIA_VALIDATOR_NOT_IMPLEMENTED"}
    world_limit = limit or (20 if dataset == "spar" else 10)
    output = root / "reports" / dataset / f"media_validation.{run_id}.json"
    if dry_run:
        return {
            "dataset": dataset, "status": "PLANNED", "storage_root": str(storage_root),
            "world_limit": world_limit, "output": str(output.relative_to(root)),
        }
    if output.exists():
        if not resume:
            raise FileExistsError(f"Output exists: {output}; use --resume")
        return json.loads(output.read_text(encoding="utf-8"))
    validators = {
        "sti_bench": _validate_sti, "vsi_bench": _validate_vsi, "spar": _validate_spar,
        "omnispatial": _validate_omnispatial, "hypo3d": _validate_hypo3d,
    }
    return validators[dataset](storage_root, root, run_id, world_limit)
