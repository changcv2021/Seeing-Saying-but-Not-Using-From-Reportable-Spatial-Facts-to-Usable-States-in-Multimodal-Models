#!/usr/bin/env python3
"""Build an exact acquisition inventory for unavailable SPAR-7M release media."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SPAR_REVISION = "0fe664cbada1e7c1173fd743e0f781882eebf777"


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def locator_fields(reference: dict[str, Any]) -> tuple[str, str, str]:
    locator = str(reference.get("archive_member") or reference.get("relative_path") or "")
    parts = PurePosixPath(locator).parts
    if len(parts) < 5 or parts[0] != "spar" or parts[2] != "images":
        raise ValueError(f"UNEXPECTED_SPAR_LOCATOR:{locator}")
    return locator, parts[1], parts[3]


def add_reference(
    target: dict[str, dict[str, Any]], reference: dict[str, Any], sample_id: str,
    component: str, pair: dict[str, Any] | None, withheld: bool,
) -> None:
    revision = str(reference.get("source_revision") or "")
    if revision != SPAR_REVISION:
        raise ValueError(f"UNEXPECTED_REVISION:{sample_id}:{revision}")
    locator, base_dataset, scene_id = locator_fields(reference)
    record = target.setdefault(locator, {
        "locator": locator,
        "base_dataset": base_dataset,
        "scene_id": scene_id,
        "withheld_evidence": withheld,
        "sample_ids": [],
        "pair_ids": [],
        "roles": [],
        "levels": [],
        "tracks": [],
        "operators": [],
        "components": [],
    })
    record["sample_ids"].append(sample_id)
    record["components"].append(component)
    record["roles"].append(str(reference.get("role") or "primary"))
    if pair:
        record["pair_ids"].append(str(pair["pair_id"]))
        task = pair.get("task") or {}
        record["levels"].append(str(task.get("level") or "UNKNOWN"))
        record["tracks"].append(str(task.get("primary_diagnostic_tag") or "UNKNOWN"))
        record["operators"].append(str(task.get("operator_id") or "UNKNOWN"))


def normalize_records(records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for key in sorted(records):
        row = records[key]
        for field in ("sample_ids", "pair_ids", "roles", "levels", "tracks", "operators", "components"):
            row[field] = sorted(set(row[field]))
        output.append(row)
    return output


def summarize(
    unavailable_ids: set[str], sample_bases: dict[str, set[str]],
    accessible: list[dict[str, Any]], withheld: list[dict[str, Any]],
) -> dict[str, Any]:
    bases = sorted({row["base_dataset"] for row in accessible + withheld})
    by_base: dict[str, Any] = {}
    for base in bases:
        available_rows = [row for row in accessible if row["base_dataset"] == base]
        withheld_rows = [row for row in withheld if row["base_dataset"] == base]
        sample_ids = sorted(sample_id for sample_id, values in sample_bases.items() if base in values)
        by_base[base] = {
            "input_count": len(sample_ids),
            "unique_accessible_paths": len(available_rows),
            "unique_withheld_paths": len(withheld_rows),
            "unique_scenes": len({row["scene_id"] for row in available_rows + withheld_rows}),
            "scenes": sorted({row["scene_id"] for row in available_rows + withheld_rows}),
        }
    return {
        "schema_version": "spaceconflict_spar7m_acquisition_inventory_v1",
        "status": "PASS",
        "source_revision": SPAR_REVISION,
        "unavailable_input_count": len(unavailable_ids),
        "inputs_with_resolved_locator_count": len(sample_bases),
        "unique_accessible_paths": len(accessible),
        "unique_withheld_paths": len(withheld),
        "by_base_dataset": by_base,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--unavailable", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    pairs_path = args.release_dir / "pairs.jsonl"
    unknown_path = args.release_dir / "unknown_challenge.jsonl"
    unavailable_ids = {row["sample_id"] for row in read_jsonl(args.unavailable)}
    if len(unavailable_ids) != 6911:
        raise ValueError(f"UNEXPECTED_UNAVAILABLE_COUNT:{len(unavailable_ids)}")

    pairs: dict[str, dict[str, Any]] = {}
    for pair in read_jsonl(pairs_path):
        if str((pair.get("source") or {}).get("source_revision") or "") == SPAR_REVISION:
            pairs[pair["pair_id"]] = pair

    unknown = {row["sample_id"]: row for row in read_jsonl(unknown_path) if row["sample_id"] in unavailable_ids}
    accessible_records: dict[str, dict[str, Any]] = {}
    withheld_records: dict[str, dict[str, Any]] = {}
    sample_bases: dict[str, set[str]] = collections.defaultdict(set)

    for sample_id in sorted(unavailable_ids):
        if sample_id.startswith("sc_unknown_"):
            row = unknown.get(sample_id)
            if row is None:
                raise ValueError(f"UNKNOWN_RECORD_MISSING:{sample_id}")
            pair = pairs.get(str(row.get("pair_id") or ""))
            media = row.get("media") or {}
            for reference in media.get("source_references") or []:
                add_reference(accessible_records, reference, sample_id, "unknown", pair, False)
                _, base, _ = locator_fields(reference)
                sample_bases[sample_id].add(base)
            withheld_reference = media.get("withheld_evidence")
            if withheld_reference:
                add_reference(withheld_records, withheld_reference, sample_id, "unknown", pair, True)
                _, base, _ = locator_fields(withheld_reference)
                sample_bases[sample_id].add(base)
            continue

        if sample_id.endswith("_pos") or sample_id.endswith("_neg"):
            pair_id = sample_id[:-4]
        else:
            raise ValueError(f"UNRECOGNIZED_SAMPLE_ID:{sample_id}")
        pair = pairs.get(pair_id)
        if pair is None:
            raise ValueError(f"PAIR_RECORD_MISSING:{sample_id}:{pair_id}")
        for reference in (pair.get("media") or {}).get("source_references") or []:
            add_reference(accessible_records, reference, sample_id, "binary", pair, False)
            _, base, _ = locator_fields(reference)
            sample_bases[sample_id].add(base)

    if set(sample_bases) != unavailable_ids:
        raise ValueError(f"UNRESOLVED_INPUTS:{len(unavailable_ids - set(sample_bases))}")

    accessible = normalize_records(accessible_records)
    withheld = normalize_records(withheld_records)
    summary = summarize(unavailable_ids, sample_bases, accessible, withheld)
    summary["input_hashes"] = {
        "pairs": sha256_file(pairs_path),
        "unknown": sha256_file(unknown_path),
        "unavailable": sha256_file(args.unavailable),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    accessible_path = args.output_dir / "required_accessible_media.jsonl"
    withheld_path = args.output_dir / "required_withheld_media.jsonl"
    summary_path = args.output_dir / "inventory_summary.json"
    accessible_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in accessible), encoding="utf-8")
    withheld_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in withheld), encoding="utf-8")
    summary["output_hashes"] = {
        "required_accessible_media": sha256_file(accessible_path),
        "required_withheld_media": sha256_file(withheld_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# SpaceConflict SPAR-7M 缺失媒体取得清单",
        "",
        f"状态：`{summary['status']}`",
        "",
        f"- 缺失输入：{summary['unavailable_input_count']:,}",
        f"- 唯一可见证据路径：{summary['unique_accessible_paths']:,}",
        f"- Unknown withheld 路径：{summary['unique_withheld_paths']:,}",
        "",
        "| 底层数据集 | 输入数 | 唯一场景 | 可见路径 | Withheld 路径 |",
        "|---|---:|---:|---:|---:|",
    ]
    for base, row in summary["by_base_dataset"].items():
        lines.append(
            f"| {base} | {row['input_count']:,} | {row['unique_scenes']:,} | "
            f"{row['unique_accessible_paths']:,} | {row['unique_withheld_paths']:,} |"
        )
    lines += [
        "",
        "`required_withheld_media.jsonl` 只用于取得/完整性审计，不得加入对应 Unknown 模型输入。",
        "",
    ]
    (args.output_dir / "ACQUISITION_INVENTORY_CN.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
