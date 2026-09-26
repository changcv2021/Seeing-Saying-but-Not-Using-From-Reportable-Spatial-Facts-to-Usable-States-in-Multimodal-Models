#!/usr/bin/env python3
"""Build a blind, cross-source L1-L3 smoke set and materialize its media read-only."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import tarfile
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORAGE = Path("external/upstream")
CA_REV = "080812355c21a40f437ed03d4ae558d35bfa2929"
SPAR_REV = "0fe664cbada1e7c1173fd743e0f781882eebf777"
SPAR_BENCH_REV = "ee122877c25c8bb08539b07e06d872152c9968f1"
OMNI_REV = "6691f3288bb1ff207d6ead4d841b505de08a6fd8"
VSI_REV = "bdcadb3fea447621a828a24911801faba3587c12"
STI_REV = "6b1009261689d3d5244bc2338ab5f83e3fb55875"
FORBIDDEN_KEYS = {"label", "gold", "certificate", "proof", "proof_nodes", "proof_edges"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"NON_OBJECT_JSONL:{path}:{line_number}")
            rows.append(value)
    return rows


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        for row in rows
    )


def write_versioned(path: Path, payload: bytes, *, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume:
            raise FileExistsError(f"OUTPUT_EXISTS:{path}")
        if path.read_bytes() != payload:
            raise ValueError(f"NONDETERMINISTIC_OUTPUT:{path}")
        return
    path.write_bytes(payload)


def safe_member(member: str) -> str:
    value = member.removeprefix("./")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"UNSAFE_ARCHIVE_MEMBER:{member}")
    return value


def extension_for(payload: bytes, fallback: str = ".bin") -> str:
    if payload.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if len(payload) > 12 and payload[4:8] == b"ftyp":
        return ".mp4"
    return fallback


def contains_forbidden(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                found.add(key)
            found.update(contains_forbidden(child))
    elif isinstance(value, list):
        for child in value:
            found.update(contains_forbidden(child))
    return found


def hashed_order(identifier: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}\0{identifier}".encode()).hexdigest()


def is_tfrecord(reference: dict[str, Any]) -> bool:
    return str(reference.get("relative_path") or "").startswith("tfrecord://")


def select_pairs(pairs: list[dict[str, Any]], seed: int) -> list[tuple[str, dict[str, Any]]]:
    strata = (
        ("ca_vqa_val_L1", lambda row: row["source"]["source_dataset"] == "ca_vqa" and not is_tfrecord(row["media"]["source_references"][0])),
        ("ca_vqa_train_L1", lambda row: row["source"]["source_dataset"] == "ca_vqa" and is_tfrecord(row["media"]["source_references"][0])),
        ("omnispatial_L1", lambda row: row["source"]["source_dataset"] == "omnispatial"),
        ("spar_bench_L1_multiview", lambda row: row["source"]["source_dataset"] == "spar" and row["source"]["source_revision"] == SPAR_BENCH_REV),
        ("spar_L1_single", lambda row: row["source"]["source_dataset"] == "spar" and row["task"]["level"] == "L1" and row["media"]["media_type"] == "single_image" and row["source"]["source_revision"] == SPAR_REV),
        ("spar_L2_single", lambda row: row["source"]["source_dataset"] == "spar" and row["task"]["level"] == "L2" and row["media"]["media_type"] == "single_image"),
        ("spar_L3_multiview", lambda row: row["source"]["source_dataset"] == "spar" and row["task"]["level"] == "L3"),
        ("vsi_bench_L2_video", lambda row: row["source"]["source_dataset"] == "vsi_bench" and row["task"]["level"] == "L2"),
        ("vsi_bench_L3_video", lambda row: row["source"]["source_dataset"] == "vsi_bench" and row["task"]["level"] == "L3"),
        ("sti_bench_L3_video", lambda row: row["source"]["source_dataset"] == "sti_bench"),
    )
    selected: list[tuple[str, dict[str, Any]]] = []
    for name, predicate in strata:
        candidates = [row for row in pairs if predicate(row)]
        if not candidates:
            raise ValueError(f"EMPTY_SMOKE_STRATUM:{name}")
        chosen = min(candidates, key=lambda row: hashed_order(str(row["pair_id"]), seed))
        selected.append((name, chosen))
    if len({row["pair_id"] for _, row in selected}) != len(selected):
        raise ValueError("DUPLICATE_SELECTED_PAIR")
    return selected


def infer_unknown_source(row: dict[str, Any]) -> str:
    references = row.get("media", {}).get("source_references") or []
    locators = "\n".join(str(ref.get("archive_member") or ref.get("relative_path") or "") for ref in references)
    if "tfrecord://train/cavqa_" in locators:
        return "ca_vqa_train"
    if "cavqa_val/" in locators:
        return "ca_vqa_val"
    if "spar/" in locators or "SPAR-Bench/" in locators:
        return "spar"
    return "other"


def tfrecord_index(row: dict[str, Any]) -> int:
    references = row.get("media", {}).get("source_references") or []
    values = []
    for ref in references:
        parsed = urlparse(str(ref.get("archive_member") or ""))
        query = parse_qs(parsed.fragment)
        if "record" in query:
            values.append(int(query["record"][0]))
    return min(values) if values else 10**9


def select_unknown(rows: list[dict[str, Any]], seed: int) -> list[tuple[str, dict[str, Any]]]:
    selected: list[tuple[str, dict[str, Any]]] = []
    for source in ("ca_vqa_val", "ca_vqa_train", "spar"):
        candidates = [row for row in rows if infer_unknown_source(row) == source]
        if source == "spar":
            candidates = [
                row for row in candidates
                if all("SPAR-Bench/" not in str(ref.get("archive_member") or "") for ref in row["media"]["source_references"])
            ]
        if not candidates:
            raise ValueError(f"EMPTY_UNKNOWN_SMOKE_STRATUM:{source}")
        if source == "ca_vqa_train":
            chosen = min(candidates, key=lambda row: (tfrecord_index(row), hashed_order(str(row["sample_id"]), seed)))
        else:
            chosen = min(candidates, key=lambda row: hashed_order(str(row["sample_id"]), seed))
        selected.append((f"unknown_{source}", chosen))
    return selected


def select_all_pairs(rows: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (
            "_".join((
                str(row["source"]["source_dataset"]), str(row["task"]["level"]),
                str(row["source"].get("source_revision") or "unknown")[:8],
            )),
            row,
        )
        for row in rows
    ]


def select_all_unknown(rows: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    return [(f"unknown_{infer_unknown_source(row)}", row) for row in rows]


def tfrecord_locators(media: dict[str, Any]) -> list[str]:
    references = media.get("source_references") or []
    if not references:
        return []
    first = references[0]
    if first.get("frame_roles"):
        values = list(first["frame_roles"].values())
    else:
        values = [reference.get("archive_member") for reference in references]
    return [str(value) for value in values if str(value).startswith("tfrecord://")]


class Materializer:
    def __init__(self, storage: Path, cache_root: Path, spar_manifest: Path, resume: bool):
        self.storage = storage.resolve()
        self.cache_root = cache_root.resolve()
        self.resume = resume
        self.zip_files: dict[Path, zipfile.ZipFile] = {}
        self.tar_files: dict[Path, tarfile.TarFile] = {}
        self.tar_members: dict[Path, dict[str, tarfile.TarInfo]] = {}
        self.tfrecord_cache: dict[tuple[Path, int], list[bytes]] = {}
        self.tfrecord_prefetch_stats: dict[str, Any] = {
            "shard_count": 0, "record_count": 0, "container_bytes": 0,
        }
        self.spar_bench_rows: dict[int, list[bytes]] = {}
        self.output_by_locator: dict[str, dict[str, Any]] = {}
        self.written_paths: set[Path] = set()
        wanted_media_ids: set[str] = set()
        self.spar_frames: dict[str, list[str]] = {}
        with spar_manifest.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                media_id = str(row.get("media_id") or "")
                if media_id and media_id not in wanted_media_ids:
                    self.spar_frames[media_id] = [str(path) for path in row.get("ordered_frame_paths") or []]

    def close(self) -> None:
        for archive in self.zip_files.values():
            archive.close()
        for archive in self.tar_files.values():
            archive.close()

    def _persist(self, locator: str, payload: bytes, fallback: str, role: str) -> dict[str, Any]:
        if locator in self.output_by_locator:
            value = dict(self.output_by_locator[locator])
            value["role"] = role
            return value
        digest = sha256_bytes(payload)
        suffix = extension_for(payload, fallback)
        path = self.cache_root / f"{digest[:24]}{suffix}"
        if path in self.written_paths:
            if sha256_file(path) != digest:
                raise ValueError(f"MATERIALIZED_MEDIA_HASH_MISMATCH:{path}")
        else:
            write_versioned(path, payload, resume=self.resume)
            self.written_paths.add(path)
        value = {"role": role, "kind": "video" if suffix == ".mp4" else "image", "path": str(path), "sha256": digest}
        self.output_by_locator[locator] = dict(value)
        return value

    def _zip_bytes(self, archive_path: Path, member: str) -> bytes:
        member = safe_member(member)
        archive = self.zip_files.setdefault(archive_path, zipfile.ZipFile(archive_path))
        try:
            return archive.read(member)
        except KeyError as exc:
            raise ValueError(f"ZIP_MEMBER_MISSING:{archive_path}:{member}") from exc

    def _tar_bytes(self, archive_path: Path, member: str) -> bytes:
        member = safe_member(member)
        if archive_path not in self.tar_files:
            archive = tarfile.open(archive_path, "r:gz")
            self.tar_files[archive_path] = archive
            self.tar_members[archive_path] = {item.name.removeprefix("./"): item for item in archive.getmembers() if item.isfile()}
        candidates = (member, member.removeprefix("spar/"), f"SPAR-7M/{member}")
        info = next((self.tar_members[archive_path].get(value) for value in candidates if value in self.tar_members[archive_path]), None)
        if info is None:
            raise ValueError(f"TAR_MEMBER_MISSING:{archive_path}:{member}")
        stream = self.tar_files[archive_path].extractfile(info)
        if stream is None:
            raise ValueError(f"TAR_MEMBER_NOT_FILE:{archive_path}:{member}")
        return stream.read()

    def _tfrecord_images(self, relative_path: str, record_index: int) -> list[bytes]:
        path = self.storage / "data/full_media_incoming/ca_vqa" / CA_REV / relative_path
        key = (path, record_index)
        if key in self.tfrecord_cache:
            return self.tfrecord_cache[key]
        from tensorflow.train import Example
        with path.open("rb") as handle:
            current = 0
            while True:
                length_bytes = handle.read(8)
                if len(length_bytes) != 8 or len(handle.read(4)) != 4:
                    raise ValueError(f"TFRECORD_RECORD_MISSING:{path}:{record_index}")
                length = struct.unpack("<Q", length_bytes)[0]
                payload = handle.read(length)
                if len(payload) != length or len(handle.read(4)) != 4:
                    raise ValueError(f"TFRECORD_TRUNCATED:{path}:{current}")
                if current == record_index:
                    example = Example.FromString(payload)
                    images = list(example.features.feature["images"].bytes_list.value)
                    self.tfrecord_cache[key] = images
                    return images
                current += 1

    def preload_tfrecord_locators(self, locators: list[str]) -> None:
        targets: dict[Path, set[int]] = {}
        for locator in sorted(set(locators)):
            parsed = urlparse(locator)
            relative = parsed.netloc + parsed.path
            query = parse_qs(parsed.fragment)
            if "record" not in query:
                raise ValueError(f"TFRECORD_RECORD_INDEX_MISSING:{locator}")
            path = self.storage / "data/full_media_incoming/ca_vqa" / CA_REV / relative
            targets.setdefault(path, set()).add(int(query["record"][0]))
        for path, record_indexes in sorted(targets.items(), key=lambda item: str(item[0])):
            if not path.is_file():
                raise ValueError(f"TFRECORD_SHARD_MISSING:{path}")
            maximum = max(record_indexes)
            with path.open("rb") as handle:
                current = 0
                while current <= maximum:
                    length_bytes = handle.read(8)
                    if len(length_bytes) != 8 or len(handle.read(4)) != 4:
                        raise ValueError(f"TFRECORD_RECORD_MISSING:{path}:{current}")
                    length = struct.unpack("<Q", length_bytes)[0]
                    payload = handle.read(length)
                    if len(payload) != length or len(handle.read(4)) != 4:
                        raise ValueError(f"TFRECORD_TRUNCATED:{path}:{current}")
                    if current in record_indexes:
                        from tensorflow.train import Example
                        example = Example.FromString(payload)
                        self.tfrecord_cache[(path, current)] = list(example.features.feature["images"].bytes_list.value)
                    current += 1
            missing = sorted(index for index in record_indexes if (path, index) not in self.tfrecord_cache)
            if missing:
                raise ValueError(f"TFRECORD_PREFETCH_MISSING:{path}:{missing[:10]}")
        self.tfrecord_prefetch_stats = {
            "shard_count": len(targets),
            "record_count": sum(len(indexes) for indexes in targets.values()),
            "container_bytes": sum(path.stat().st_size for path in targets),
        }

    def tfrecord_locator(self, locator: str, role: str) -> dict[str, Any]:
        parsed = urlparse(locator)
        relative = parsed.netloc + parsed.path
        query = parse_qs(parsed.fragment)
        record_index = int(query["record"][0])
        image_index = int(query["index"][0])
        images = self._tfrecord_images(relative, record_index)
        if not 0 <= image_index < len(images):
            raise ValueError(f"TFRECORD_IMAGE_INDEX_INVALID:{locator}")
        payload = images[image_index]
        expected = query.get("sha256", [""])[0]
        if expected and sha256_bytes(payload) != expected:
            raise ValueError(f"TFRECORD_IMAGE_HASH_MISMATCH:{locator}")
        return self._persist(locator, payload, ".jpg", role)

    def spar_bench_images(self, row_id: int) -> list[bytes]:
        if row_id in self.spar_bench_rows:
            return self.spar_bench_rows[row_id]
        import pyarrow.dataset as pads

        data_root = self.storage / "data/full_media_incoming/spar" / SPAR_BENCH_REV / "SPAR-Bench/data"
        shards = sorted(data_root.glob("*.parquet"))
        if not shards:
            raise ValueError(f"SPAR_BENCH_SHARDS_MISSING:{data_root}")
        dataset = pads.dataset([str(path) for path in shards], format="parquet")
        table = dataset.to_table(columns=["id", "image"], filter=pads.field("id") == row_id)
        if table.num_rows != 1:
            raise ValueError(f"SPAR_BENCH_ROW_CARDINALITY:{row_id}:{table.num_rows}")
        images = [bytes(item.get("bytes") or b"") for item in table.to_pylist()[0]["image"]]
        if not images or any(not payload for payload in images):
            raise ValueError(f"SPAR_BENCH_EMPTY_IMAGE:{row_id}")
        self.spar_bench_rows[row_id] = images
        return images

    def resolve_member(self, dataset: str, member: str, role: str, relative_path: str = "") -> dict[str, Any]:
        if member.startswith("tfrecord://"):
            return self.tfrecord_locator(member, role)
        member = safe_member(member)
        if dataset == "ca_vqa":
            path = self.storage / "data/full_media_incoming/ca_vqa" / CA_REV / "val/cavqa_val_extracted" / member
            if not path.is_file():
                raise ValueError(f"CA_VAL_MEDIA_MISSING:{path}")
            return self._persist(f"file:{path}", path.read_bytes(), path.suffix or ".jpg", role)
        if dataset == "omnispatial":
            archive = self.storage / "data/full_media_incoming/omnispatial" / OMNI_REV / "OmniSpatial-full.zip"
            return self._persist(f"zip:{archive}#{member}", self._zip_bytes(archive, member), Path(member).suffix, role)
        if dataset == "spar":
            parts = PurePosixPath(member).parts
            if len(parts) < 2 or parts[0] != "spar":
                raise ValueError(f"SPAR_MEMBER_UNROUTABLE:{member}")
            archive = self.storage / "data/full_media_incoming/spar" / SPAR_REV / "SPAR-7M" / f"{parts[1]}.tar.gz"
            return self._persist(f"tar:{archive}#{member}", self._tar_bytes(archive, member), Path(member).suffix, role)
        if dataset == "vsi_bench":
            archive_name = relative_path.split("#", 1)[0]
            archive = self.storage / "data/pilot_media_incoming/vsi_bench" / VSI_REV / archive_name
            return self._persist(f"zip:{archive}#{member}", self._zip_bytes(archive, member), Path(member).suffix, role)
        if dataset == "sti_bench":
            archive = self.storage / "data/pilot_media_incoming/sti_bench" / STI_REV / "video.zip"
            return self._persist(f"zip:{archive}#{member}", self._zip_bytes(archive, member), Path(member).suffix, role)
        raise ValueError(f"UNSUPPORTED_DATASET:{dataset}")

    def resolve(self, dataset: str, media: dict[str, Any]) -> list[dict[str, Any]]:
        references = media.get("source_references") or []
        if not references:
            raise ValueError("EMPTY_MEDIA_REFERENCES")
        first = references[0]
        if dataset == "spar" and first.get("source_revision") == SPAR_BENCH_REV:
            member = str(first.get("archive_member") or "")
            marker = "#row="
            if marker not in member:
                raise ValueError(f"SPAR_BENCH_ROW_UNROUTABLE:{member}")
            row_id = int(member.rsplit(marker, 1)[1])
            return [
                self._persist(f"spar-bench:{row_id}:image:{index}", payload, ".jpg", f"view_{index + 1}")
                for index, payload in enumerate(self.spar_bench_images(row_id))
            ]
        if dataset == "ca_vqa" and first.get("frame_roles"):
            roles = first["frame_roles"]
            ordered_roles = ["reference_frame"] + sorted((key for key in roles if key != "reference_frame"), key=lambda value: int(value.rsplit("_", 1)[-1]))
            return [self.resolve_member(dataset, str(roles[role]), role) for role in ordered_roles]
        if dataset == "spar" and media.get("media_type") == "multi_view_images" and first.get("media_id") in self.spar_frames:
            members = self.spar_frames[str(first["media_id"])]
            if not members:
                raise ValueError(f"SPAR_MANIFEST_EMPTY:{first['media_id']}")
            return [self.resolve_member(dataset, member, f"frame_{index}") for index, member in enumerate(members)]
        resolved = []
        for index, reference in enumerate(references):
            member = str(reference.get("archive_member") or "")
            role = str(reference.get("role") or f"media_{index}")
            relative_path = str(reference.get("relative_path") or "")
            resolved.append(self.resolve_member(dataset, member, role, relative_path))
        return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=Path, default=ROOT / "release/production_available_v10/pairs.jsonl")
    parser.add_argument("--claims", type=Path, default=ROOT / "release/production_available_v10/claims.jsonl")
    parser.add_argument("--unknown", type=Path, default=ROOT / "release/production_available_v10/unknown_challenge.jsonl")
    parser.add_argument("--storage-root", type=Path, default=DEFAULT_STORAGE)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--allow-rejects", action="store_true", help="Write a partial diagnostic smoke set while retaining every structured reject.")
    parser.add_argument("--known-unavailable-dataset", action="append", default=[], help="Retain selected records as UPSTREAM_MEDIA_NOT_ACQUIRED rejects without attempting archive resolution.")
    parser.add_argument("--known-unavailable-revision", action="append", default=[], help="Retain selected records from a specific source revision as UPSTREAM_MEDIA_NOT_ACQUIRED rejects.")
    parser.add_argument("--selection-mode", choices=("smoke", "all"), default="smoke")
    parser.add_argument("--request-name", default="requested_samples.smoke.jsonl")
    parser.add_argument("--reject-name", default="media_rejects.smoke.jsonl")
    parser.add_argument("--report-name", default="media_resolution_report.smoke.json")
    parser.add_argument("--seed", type=int, default=20260903)
    parser.add_argument("--run-id", default="qwen25vl7b_v10_cross_source_smoke_20260903")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    pairs = read_jsonl(args.pairs)
    claims = read_jsonl(args.claims)
    unknown = read_jsonl(args.unknown)
    if len(pairs) != 9812 or len(claims) != 19624 or len(unknown) != 2000:
        raise ValueError(f"RELEASE_CARDINALITY_MISMATCH:{len(pairs)}:{len(claims)}:{len(unknown)}")
    if args.selection_mode == "all":
        selected_pairs = select_all_pairs(pairs)
        selected_unknown = select_all_unknown(unknown)
    else:
        selected_pairs = select_pairs(pairs, args.seed)
        selected_unknown = select_unknown(unknown, args.seed)
    if args.limit is not None:
        selected_pairs = selected_pairs[:args.limit]
        selected_unknown = selected_unknown[:args.limit]
    selected_pair_ids = {row["pair_id"] for _, row in selected_pairs}
    claim_rows = [row for row in claims if row["pair_id"] in selected_pair_ids]
    if len(claim_rows) != 2 * len(selected_pairs):
        raise ValueError("SELECTED_PAIR_CLAIM_CARDINALITY_MISMATCH")
    pair_by_id = {row["pair_id"]: row for _, row in selected_pairs}
    selection = [
        {
            "stratum": stratum, "pair_id": row["pair_id"],
            "dataset": row["source"]["source_dataset"], "level": row["task"]["level"],
            "track": row["task"]["primary_diagnostic_tag"], "operator_id": row["task"]["operator_id"],
            "media_type": row["media"]["media_type"],
        }
        for stratum, row in selected_pairs
    ] + [
        {"stratum": stratum, "sample_id": row["sample_id"], "component": "unknown", "media_type": row["media"]["media_type"]}
        for stratum, row in selected_unknown
    ]
    plan = {
        "status": "PLANNED" if args.dry_run else "MATERIALIZING",
        "run_id": args.run_id, "seed": args.seed, "binary_pairs": len(selected_pairs),
        "binary_claims": len(claim_rows), "unknown_claims": len(selected_unknown), "selection": selection,
    }
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    materializer = Materializer(
        args.storage_root,
        args.cache_root,
        ROOT / "data/media_index/spar" / SPAR_REV / "qualitative_relation_media.v2.jsonl",
        args.resume,
    )
    selected_media = [row["media"] for _, row in selected_pairs] + [row["media"] for _, row in selected_unknown]
    materializer.preload_tfrecord_locators([
        locator for media in selected_media for locator in tfrecord_locators(media)
    ])
    requests: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    try:
        for row in claim_rows:
            pair = pair_by_id[row["pair_id"]]
            dataset = pair["source"]["source_dataset"]
            revision = str(pair["source"].get("source_revision") or "")
            if dataset in args.known_unavailable_dataset or revision in args.known_unavailable_revision:
                rejects.append({
                    "sample_id": row["sample_id"], "reject_code": "UPSTREAM_MEDIA_NOT_ACQUIRED",
                    "detail": f"{dataset}@{revision}: release source reference requires separately acquired upstream media",
                })
                continue
            try:
                resolved = materializer.resolve(dataset, row["media"])
                requests.append({
                    "sample_id": row["sample_id"], "pair_id": row["pair_id"],
                    "component": "binary", "claim_text": row["claim"], "media": resolved,
                })
            except Exception as exc:
                rejects.append({"sample_id": row["sample_id"], "reject_code": str(exc).split(":", 1)[0], "detail": str(exc)})
        for _, row in selected_unknown:
            source = infer_unknown_source(row)
            dataset = "ca_vqa" if source.startswith("ca_vqa") else source
            revisions = {
                str(reference.get("source_revision") or "")
                for reference in row.get("media", {}).get("source_references") or []
            }
            if dataset in args.known_unavailable_dataset or bool(revisions.intersection(args.known_unavailable_revision)):
                rejects.append({
                    "sample_id": row["sample_id"], "reject_code": "UPSTREAM_MEDIA_NOT_ACQUIRED",
                    "detail": f"{dataset}@{','.join(sorted(revisions))}: release source reference requires separately acquired upstream media",
                })
                continue
            try:
                resolved = materializer.resolve(dataset, row["media"])
                requests.append({
                    "sample_id": row["sample_id"], "pair_id": row.get("pair_id"),
                    "component": "unknown", "claim_text": row["claim"], "media": resolved,
                })
            except Exception as exc:
                rejects.append({"sample_id": row["sample_id"], "reject_code": str(exc).split(":", 1)[0], "detail": str(exc)})
    finally:
        materializer.close()

    requests.sort(key=lambda row: (row["component"], row["sample_id"]))
    forbidden = set().union(*(contains_forbidden(row) for row in requests)) if requests else set()
    duplicate_ids = len(requests) - len({row["sample_id"] for row in requests})
    if forbidden:
        rejects.append({"sample_id": None, "reject_code": "GOLD_LEAKAGE_KEYS", "detail": sorted(forbidden)})
    if duplicate_ids:
        rejects.append({"sample_id": None, "reject_code": "DUPLICATE_SAMPLE_IDS", "detail": duplicate_ids})

    complete = not rejects and len(requests) == len(claim_rows) + len(selected_unknown)
    dataset_by_pair = {
        str(row["pair_id"]): str(row["source"]["source_dataset"])
        for _, row in selected_pairs
    }
    dataset_by_unknown = {
        str(row["sample_id"]): ("ca_vqa" if infer_unknown_source(row).startswith("ca_vqa") else infer_unknown_source(row))
        for _, row in selected_unknown
    }
    paths_by_dataset: dict[str, set[str]] = {}
    for request in requests:
        dataset = dataset_by_pair.get(str(request.get("pair_id"))) or dataset_by_unknown.get(str(request["sample_id"])) or "unknown"
        paths_by_dataset.setdefault(dataset, set()).update(
            str(media["path"]) for media in request.get("media") or [] if media.get("path")
        )
    report = {
        "schema_version": "spaceconflict_v10_mllm_media_smoke_v1",
        "status": "PASS" if complete else "PARTIAL_KNOWN_REJECTS" if args.allow_rejects and requests else "FAIL",
        "run_id": args.run_id, "seed": args.seed,
        "release_counts": {"pairs": len(pairs), "claims": len(claims), "unknown": len(unknown)},
        "selected_binary_pairs": len(selected_pairs), "selected_binary_claims": len(claim_rows),
        "selected_unknown_claims": len(selected_unknown), "request_count": len(requests),
        "reject_count": len(rejects), "forbidden_gold_keys": sorted(forbidden), "duplicate_sample_ids": duplicate_ids,
        "materialized_unique_files": len({value["path"] for value in materializer.output_by_locator.values()}),
        "materialized_type_counts": dict(sorted(Counter(value["kind"] for value in materializer.output_by_locator.values()).items())),
        "materialized_bytes": sum(
            Path(path).stat().st_size for path in {value["path"] for value in materializer.output_by_locator.values()}
        ),
        "materialized_by_dataset": {
            dataset: {
                "unique_files": len(paths),
                "bytes": sum(Path(path).stat().st_size for path in paths),
            }
            for dataset, paths in sorted(paths_by_dataset.items())
        },
        "tfrecord_prefetch": materializer.tfrecord_prefetch_stats,
        "selection": selection,
        "input_hashes": {
            str(args.pairs): sha256_file(args.pairs), str(args.claims): sha256_file(args.claims), str(args.unknown): sha256_file(args.unknown),
        },
    }
    request_payload = jsonl_bytes(requests)
    reject_payload = jsonl_bytes(rejects)
    report["requested_samples_sha256"] = sha256_bytes(request_payload)
    write_versioned(args.output_dir / args.request_name, request_payload, resume=args.resume)
    write_versioned(args.output_dir / args.reject_name, reject_payload, resume=args.resume)
    write_versioned(
        args.output_dir / args.report_name,
        (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        resume=args.resume,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] in {"PASS", "PARTIAL_KNOWN_REJECTS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
