from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..registry import ROOT


MAX_LOGIN_NODE_METADATA_BYTES = 5_000_000


@dataclass(frozen=True)
class MetadataAsset:
    dataset: str
    source_uri: str
    source_revision: str
    relative_path: str
    license_id: str
    expected_size: int | None = None
    expected_sha256: str | None = None


def assets_for(dataset: str) -> list[MetadataAsset]:
    definitions: dict[str, list[MetadataAsset]] = {
        "sti_bench": [
            MetadataAsset(
                dataset="sti_bench",
                source_uri="https://huggingface.co/datasets/MINT-SJTU/STI-Bench/resolve/6b1009261689d3d5244bc2338ab5f83e3fb55875/qa.parquet?download=true",
                source_revision="6b1009261689d3d5244bc2338ab5f83e3fb55875",
                relative_path="qa.parquet",
                license_id="Apache-2.0_dataset_card",
                expected_size=377484,
                expected_sha256="bb2746998c2e49eddf9e7c4b2d8cc902333522f2e64606e2bb0b8b2aa7685382",
            ),
            MetadataAsset(
                dataset="sti_bench",
                source_uri="https://huggingface.co/datasets/MINT-SJTU/STI-Bench/resolve/6b1009261689d3d5244bc2338ab5f83e3fb55875/README.md?download=true",
                source_revision="6b1009261689d3d5244bc2338ab5f83e3fb55875",
                relative_path="README.md",
                license_id="Apache-2.0_dataset_card",
                expected_size=6272,
            ),
        ],
        "vsi_bench": [
            MetadataAsset(
                dataset="vsi_bench",
                source_uri="https://huggingface.co/datasets/nyu-visionx/VSI-Bench/resolve/bdcadb3fea447621a828a24911801faba3587c12/test.jsonl?download=true",
                source_revision="bdcadb3fea447621a828a24911801faba3587c12",
                relative_path="test.jsonl",
                license_id="Apache-2.0",
                expected_size=1632679,
            ),
            MetadataAsset(
                dataset="vsi_bench",
                source_uri="https://huggingface.co/datasets/nyu-visionx/VSI-Bench/resolve/bdcadb3fea447621a828a24911801faba3587c12/pruned_ids.txt?download=true",
                source_revision="bdcadb3fea447621a828a24911801faba3587c12",
                relative_path="pruned_ids.txt",
                license_id="Apache-2.0",
                expected_size=13132,
            ),
            MetadataAsset(
                dataset="vsi_bench",
                source_uri="https://huggingface.co/datasets/nyu-visionx/VSI-Bench/resolve/bdcadb3fea447621a828a24911801faba3587c12/README.md?download=true",
                source_revision="bdcadb3fea447621a828a24911801faba3587c12",
                relative_path="README.md",
                license_id="Apache-2.0",
                expected_size=10215,
            ),
        ],
        "spar": [
            MetadataAsset(
                dataset="spar",
                source_uri="https://huggingface.co/datasets/jasonzhango/SPAR-Bench-Tiny/resolve/ae9bbc5297fd277123c42b0628d1f40bf72f89f1/README.md?download=true",
                source_revision="ae9bbc5297fd277123c42b0628d1f40bf72f89f1",
                relative_path="README.md",
                license_id="UNVERIFIED_DATA_LICENSE",
                expected_size=1983,
            ),
            MetadataAsset(
                dataset="spar",
                source_uri="https://datasets-server.huggingface.co/info?dataset=jasonzhango%2FSPAR-Bench-Tiny",
                source_revision="ae9bbc5297fd277123c42b0628d1f40bf72f89f1",
                relative_path="dataset_info.json",
                license_id="UNVERIFIED_DATA_LICENSE",
            ),
            MetadataAsset(
                dataset="spar",
                source_uri="https://datasets-server.huggingface.co/first-rows?dataset=jasonzhango%2FSPAR-Bench-Tiny&config=default&split=test",
                source_revision="ae9bbc5297fd277123c42b0628d1f40bf72f89f1",
                relative_path="first_rows.json",
                license_id="UNVERIFIED_DATA_LICENSE",
            ),
            MetadataAsset(
                dataset="spar",
                source_uri="https://datasets-server.huggingface.co/filter?dataset=jasonzhango%2FSPAR-Bench-Tiny&config=default&split=test&where=%22task%22%20%3D%20%27obj_spatial_relation_oc_mv%27&length=100",
                source_revision="ae9bbc5297fd277123c42b0628d1f40bf72f89f1",
                relative_path="filtered_obj_spatial_relation_oc_mv.json",
                license_id="UNVERIFIED_DATA_LICENSE",
            ),
        ],
    }
    return definitions.get(dataset, [])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_existing(path: Path, asset: MetadataAsset) -> tuple[int, str]:
    size = path.stat().st_size
    sha256 = _sha256(path)
    if asset.expected_size is not None and size != asset.expected_size:
        raise ValueError(f"Existing raw file size mismatch: {path}")
    if asset.expected_sha256 is not None and sha256 != asset.expected_sha256:
        raise ValueError(f"Existing raw file hash mismatch: {path}")
    return size, sha256


def _download(asset: MetadataAsset, target: Path) -> tuple[int, str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(asset.source_uri, headers={"User-Agent": "dataset/0.1 metadata-only"})
    temporary_path: Path | None = None
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_LOGIN_NODE_METADATA_BYTES:
                raise ValueError(f"Refusing login-node download larger than metadata cap: {content_length}")
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".metadata-", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                digest = hashlib.sha256()
                total = 0
                while chunk := response.read(64 * 1024):
                    total += len(chunk)
                    if total > MAX_LOGIN_NODE_METADATA_BYTES:
                        raise ValueError("Refusing download that exceeded metadata cap")
                    temporary.write(chunk)
                    digest.update(chunk)
        sha256 = digest.hexdigest()
        if asset.expected_size is not None and total != asset.expected_size:
            raise ValueError(f"Downloaded size mismatch for {asset.relative_path}: {total}")
        if asset.expected_sha256 is not None and sha256 != asset.expected_sha256:
            raise ValueError(f"Downloaded hash mismatch for {asset.relative_path}")
        if target.exists():
            raise FileExistsError(f"Raw target already exists: {target}")
        os.replace(temporary_path, target)
        temporary_path = None
        return total, sha256
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def acquire_metadata(dataset: str, *, dry_run: bool, resume: bool, root: Path = ROOT) -> dict[str, Any]:
    assets = assets_for(dataset)
    if not assets:
        return {"dataset": dataset, "status": "BLOCKED_SOURCE", "reason": "NO_APPROVED_METADATA_ASSETS", "files": []}
    revision = assets[0].source_revision
    manifest = root / "data" / "manifests" / dataset / f"{revision}.jsonl"
    existing_manifest_entries: dict[str, dict[str, Any]] = {}
    if manifest.exists():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                existing_manifest_entries[entry["relative_path"]] = entry
    entries: list[dict[str, Any]] = []
    for asset in assets:
        target = root / "data" / "raw" / dataset / asset.source_revision / asset.relative_path
        if dry_run:
            entries.append({"relative_path": str(target.relative_to(root)), "source_uri": asset.source_uri, "status": "planned"})
            continue
        if target.exists():
            if not resume:
                raise FileExistsError(f"Refusing to overwrite immutable raw file: {target}")
            size, sha256 = _validate_existing(target, asset)
            status = "verified_existing"
        else:
            size, sha256 = _download(asset, target)
            status = "complete"
        relative_path = str(target.relative_to(root / "data" / "raw"))
        previous = existing_manifest_entries.get(relative_path)
        entry = {
            "dataset": dataset,
            "source_type": "huggingface",
            "source_uri": asset.source_uri,
            "source_revision": asset.source_revision,
            "relative_path": relative_path,
            "file_size": size,
            "sha256": f"sha256:{sha256}",
            "download_timestamp_utc": previous.get("download_timestamp_utc") if previous else datetime.now(timezone.utc).isoformat(),
            "download_command": f"spaceconflict download --dataset {dataset} --tier metadata",
            "license_id": asset.license_id,
            "status": previous.get("status") if previous else status,
        }
        entries.append(entry)
    if not dry_run:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        serialized = "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in entries)
        if manifest.exists():
            if not resume:
                raise FileExistsError(f"Refusing to overwrite manifest: {manifest}")
            existing = manifest.read_text(encoding="utf-8")
            if existing != serialized:
                manifest.write_text(serialized, encoding="utf-8")
        else:
            manifest.write_text(serialized, encoding="utf-8")
    return {"dataset": dataset, "status": "PLANNED" if dry_run else "DOWNLOADED", "files": entries}
