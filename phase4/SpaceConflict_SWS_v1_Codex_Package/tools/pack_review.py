#!/usr/bin/env python3
"""Create a review ZIP with complete normalized responses and closed evidence refs.

Input files follow the guide's handoff contract. This does not convert an arbitrary
legacy CSV, verify visual ground truth, or certify a scientific mechanism.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterator
from research_utils import read_jsonl, strict_json_loads, sha256_file

COPY_FILES = [
    "00_START_HERE_CN.md", "01_REPORT_CN.md", "02_CLAIM_EVIDENCE_MATRIX.json",
    "04_ALL_PRIMARY_STATISTICS.csv", "06_PROTOCOL_PROVENANCE_AND_ACCEPTANCE.json",
    "07_MECHANISTIC_EFFECTS.csv", "08_SCHEDULER_AND_COST_SUMMARY.json",
]
COMPRESS_FILES = ["03_WORLD_DIAGNOSIS.csv", "05_MATCHED_CASES.jsonl"]
RAW_REQUIRED = ["model_id", "model_revision", "request_id", "world_cluster_id",
                "experiment", "split", "prompt", "raw_response"]


def evidence_refs(obj: Any) -> Iterator[tuple[str, str]]:
    """Canonical references: {model_id, request_id}; recurse through evidence lists."""
    if isinstance(obj, dict):
        if "model_id" in obj and "request_id" in obj:
            yield (str(obj["model_id"]), str(obj["request_id"]))
        for value in obj.values():
            yield from evidence_refs(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from evidence_refs(value)


def compress_file(src: Path, dest: Path) -> None:
    with src.open("rb") as f, gzip.GzipFile(filename=str(dest), mode="wb", mtime=0) as out:
        shutil.copyfileobj(f, out)


def case_inline_records(obj: Any) -> Iterator[dict[str, Any]]:
    if isinstance(obj, dict):
        if "model_id" in obj and "request_id" in obj and ("prompt" in obj or "raw_response" in obj):
            yield obj
        for value in obj.values():
            yield from case_inline_records(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from case_inline_records(value)


def text_hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_package(source: Path, responses: Path, output: Path, part_mib: float = 20) -> dict[str, Any]:
    source, responses, output = source.resolve(), responses.resolve(), output.resolve()
    if output.exists():
        raise ValueError("Refusing to overwrite an existing review ZIP")
    if part_mib <= 0:
        raise ValueError("part_mib must be positive")
    for name in COPY_FILES + COMPRESS_FILES:
        if not (source / name).is_file():
            raise ValueError(f"Missing mandatory handoff file: {name}")
    if not responses.is_file():
        raise ValueError("Complete normalized response JSONL is missing")
    output.parent.mkdir(parents=True, exist_ok=True)
    expected_refs: set[tuple[str, str]] = set()
    claims = strict_json_loads((source / "02_CLAIM_EVIDENCE_MATRIX.json").read_text(encoding="utf-8"))
    expected_refs.update(evidence_refs(claims))
    cases = list(read_jsonl(source / "05_MATCHED_CASES.jsonl"))
    for case in cases:
        expected_refs.update(evidence_refs(case))
    with (source / "07_MECHANISTIC_EFFECTS.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            for role in ("donor", "recipient"):
                rid, mid = row.get(f"{role}_request_id", ""), row.get(f"{role}_model_id", "")
                if rid and not mid:
                    raise ValueError(f"Mechanistic {role} reference lacks model_id")
                if rid:
                    expected_refs.add((mid, rid))
    with tempfile.TemporaryDirectory(prefix="sws_review_", dir=output.parent) as tmp:
        dest = Path(tmp)
        for name in COPY_FILES:
            shutil.copy2(source / name, dest / name)
        for name in COMPRESS_FILES:
            compress_file(source / name, dest / (name + ".gz"))
        raw_dir = dest / "09_FULL_RESPONSES"
        raw_dir.mkdir()
        seen: dict[tuple[str, str], tuple[str, str]] = {}
        world_ids: set[str] = set()
        counts: dict[str, int] = {}
        split_counts: dict[str, int] = {}
        parts = []
        out = None
        part_bytes, part_rows, total = 0, 0, 0
        part_path = None
        limit = int(part_mib * 1024 * 1024)
        try:
            for row in read_jsonl(responses):
                for key in RAW_REQUIRED:
                    if not isinstance(row.get(key), str) or (key not in {"raw_response"} and not row[key]):
                        raise ValueError(f"Response lacks string field {key}: {row.get('request_id')}")
                key = (row["model_id"], row["request_id"])
                if key in seen:
                    raise ValueError(f"Duplicate retained response: {key}")
                seen[key] = (text_hash(row["prompt"]), text_hash(row["raw_response"]))
                world_ids.add(row["world_cluster_id"])
                counts[row["model_id"]] = counts.get(row["model_id"], 0) + 1
                split_counts[row["split"]] = split_counts.get(row["split"], 0) + 1
                line = (json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
                if out is None or (part_bytes + len(line) > limit and part_rows > 0):
                    if out is not None:
                        out.close()
                        parts.append({"file": part_path.name, "rows": part_rows, "uncompressed_bytes": part_bytes})
                    part_path = raw_dir / f"responses_{len(parts):04d}.jsonl.gz"
                    out = gzip.GzipFile(filename=str(part_path), mode="wb", mtime=0)
                    part_bytes, part_rows = 0, 0
                out.write(line)
                part_bytes += len(line)
                part_rows += 1
                total += 1
        finally:
            if out is not None:
                out.close()
        if part_path is not None:
            parts.append({"file": part_path.name, "rows": part_rows, "uncompressed_bytes": part_bytes})
        missing = expected_refs - seen.keys()
        if missing:
            raise ValueError(f"Evidence references absent from complete responses: {sorted(missing)[:8]}")
        for case in cases:
            for row in case_inline_records(case):
                key = (str(row["model_id"]), str(row["request_id"]))
                prompt_hash, raw_hash = seen[key]
                if "prompt" in row and text_hash(row["prompt"]) != prompt_hash:
                    raise ValueError(f"Illustrative prompt disagrees with raw archive: {key}")
                if "raw_response" in row and text_hash(row["raw_response"]) != raw_hash:
                    raise ValueError(f"Illustrative output disagrees with raw archive: {key}")
        media = source / "10_AUDITED_MEDIA"
        media_included = media.is_dir()
        if media_included:
            shutil.copytree(media, dest / "10_AUDITED_MEDIA")
        else:
            (dest / "10_AUDITED_MEDIA").mkdir()
            (dest / "10_AUDITED_MEDIA" / "NOT_INCLUDED.txt").write_text(
                "Actual media not included. This review package cannot independently establish visual sufficiency.\n",
                encoding="utf-8")
        (raw_dir / "INDEX.json").write_text(json.dumps(parts, indent=2), encoding="utf-8")
        acceptance = {
            "packaging_status": "PASS_REFERENCES_CLOSED",
            "scientific_status": "NOT_CERTIFIED_BY_PACKAGER",
            "responses": total, "unique_world_clusters": len(world_ids), "responses_by_model": counts,
            "responses_by_split": split_counts, "case_bundles": len(cases), "evidence_refs": len(expected_refs),
            "missing_evidence_refs": 0, "media_directory_included": media_included,
            "media_review_not_independently_certified": True,
            "raw_source_sha256": sha256_file(responses), "raw_parts": len(parts),
            "hash_manifest_excludes": ["SHA256SUMS.txt"],
        }
        (dest / "REVIEW_PACKAGE_ACCEPTANCE.json").write_text(
            json.dumps(acceptance, indent=2, ensure_ascii=False), encoding="utf-8")
        lines = [f"{sha256_file(p)}  {p.relative_to(dest).as_posix()}" for p in sorted(dest.rglob("*")) if p.is_file()]
        (dest / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for p in sorted(dest.rglob("*")):
                if p.is_file():
                    z.write(p, p.relative_to(dest))
    return acceptance


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--responses", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--part-mib", type=float, default=20)
    args = ap.parse_args()
    try:
        result = build_package(args.source, args.responses, args.output, args.part_mib)
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(f"PACKAGE_BLOCKED: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
