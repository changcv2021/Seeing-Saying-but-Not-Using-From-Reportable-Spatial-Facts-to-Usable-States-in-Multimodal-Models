#!/usr/bin/env python3
"""Finalize an internal SpaceConflict evaluation bundle with only release-used media."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = Path("external/project/iclr/spacebenchmark/SpaceConflict_Evaluation_Bundle_v1_20260903")
DEFAULT_HYPO_MEDIA = Path("external/upstream/data/full_media_incoming/hypo3d/ffb21ab198e8d666b63e062d931ed33b60c67d0f")
RUN_ID = "spaceconflict_evaluation_bundle_v1_20260903"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_versioned(path: Path, payload: bytes, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume:
            raise FileExistsError(f"OUTPUT_EXISTS:{path}")
        if path.read_bytes() != payload:
            raise ValueError(f"NONDETERMINISTIC_OUTPUT:{path}")
        return
    path.write_bytes(payload)


def copy_file(source: Path, target: Path, resume: bool) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"SOURCE_FILE_MISSING:{source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not resume:
            raise FileExistsError(f"OUTPUT_EXISTS:{target}")
        if source.stat().st_size != target.stat().st_size or sha256_file(source) != sha256_file(target):
            raise ValueError(f"EXISTING_COPY_MISMATCH:{target}")
        return
    shutil.copy2(source, target)


def copy_tree(source: Path, target: Path, resume: bool) -> int:
    copied = 0
    for path in sorted(source.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        copy_file(path, target / path.relative_to(source), resume)
        copied += 1
    return copied


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"NON_OBJECT_JSONL:{path}:{line_number}")
            yield value


def safe_relative(raw: str) -> Path:
    value = PurePosixPath(raw)
    if value.is_absolute() or ".." in value.parts or not value.parts:
        raise ValueError(f"UNSAFE_RELATIVE_MEDIA_PATH:{raw}")
    return Path(*value.parts)


def directory_stats(path: Path) -> dict[str, int]:
    files = [value for value in path.rglob("*") if value.is_file()]
    return {"files": len(files), "bytes": sum(value.stat().st_size for value in files)}


def human_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if abs(amount) < 1024.0 or unit == units[-1]:
            return f"{amount:.2f} {unit}"
        amount /= 1024.0
    raise AssertionError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--hypo-media-root", type=Path, default=DEFAULT_HYPO_MEDIA)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260903)
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    bundle = args.bundle_root.resolve()
    l1_eval = bundle / "benchmark/l1_l3/evaluation"
    l1_report_path = l1_eval / "media_resolution_report.json"
    frames_report_path = l1_eval / "video_frame_materialization_report.json"
    plan = {
        "status": "PLANNED", "run_id": args.run_id, "seed": args.seed,
        "bundle_root": str(bundle), "l4_expected_media": 2205,
        "static_sections": ["benchmark", "documentation", "software", "model_results"],
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    if not l1_report_path.is_file() or not frames_report_path.is_file():
        raise FileNotFoundError("L1_L3_MATERIALIZATION_PREREQUISITE_MISSING")
    l1_report = json.loads(l1_report_path.read_text(encoding="utf-8"))
    frames_report = json.loads(frames_report_path.read_text(encoding="utf-8"))
    if l1_report.get("status") != "PARTIAL_KNOWN_REJECTS":
        raise ValueError(f"UNEXPECTED_L1_L3_STATUS:{l1_report.get('status')}")
    expected = {
        "selected_binary_pairs": 9812, "selected_binary_claims": 19624,
        "selected_unknown_claims": 2000, "request_count": 14713, "reject_count": 6911,
    }
    for key, value in expected.items():
        if l1_report.get(key) != value:
            raise ValueError(f"L1_L3_COUNT_MISMATCH:{key}:{l1_report.get(key)}:{value}")
    if frames_report.get("status") != "PASS" or frames_report.get("sample_count") != 14713:
        raise ValueError("VIDEO_FRAME_REPORT_INVALID")

    static_counts: dict[str, int] = {}
    static_counts["l1_l3_release"] = copy_tree(
        ROOT / "release/production_available_v10", bundle / "benchmark/l1_l3/release", args.resume,
    )
    static_counts["l4_release"] = copy_tree(
        ROOT / "l4/v3_3/release", bundle / "benchmark/l4/release", args.resume,
    )
    static_counts["l4_derived_annotations"] = copy_tree(
        ROOT / "l4/v3_3/derived_annotations", bundle / "benchmark/l4/derived_annotations", args.resume,
    )
    for name in ("reports", "problem", "visresult"):
        static_counts[name] = copy_tree(ROOT / name, bundle / "documentation" / name, args.resume)
    for name in ("src", "scripts", "contracts", "configs", "schemas", "operators", "tests"):
        static_counts[name] = copy_tree(ROOT / name, bundle / "software" / name, args.resume)
    for name in (
        "AGENTS.md", "PROJECT_SPEC.md", "README.md", "EVALUATION.md", "datasets.yaml", "pyproject.toml", "Makefile",
        "SpaceConflict_Codex_Benchmark_Build_Guide_CN.md", "SpaceConflict_Hypo3D_L4_Rebuild_Guide_CN.md",
        "SpaceConflict_L4_Three_Part_Build_Guide_CN.md", "SpaceConflict_Table_Visualization_Results_Guide_CN.md",
        "SpaceConflict_Project_Handoff_and_MLLM_Evaluation_Report_CN.md",
    ):
        copy_file(ROOT / name, bundle / "documentation" / name, args.resume)
    static_counts["qwen_results"] = copy_tree(
        ROOT / "runs/mllm/qwen2_5_vl_7b", bundle / "model_results/qwen2_5_vl_7b", args.resume,
    )

    l4_inputs = (
        ROOT / "l4/v3_3/release/model_inputs.l4_three_part_v3.jsonl",
        ROOT / "l4/v3_3/release/model_inputs.l4_unknown_v3.jsonl",
    )
    l4_media: dict[str, str] = {}
    for input_path in l4_inputs:
        for row in read_jsonl(input_path):
            for media in (row.get("media") or {}).values():
                relative = str(media["path"])
                expected_hash = str(media["sha256"]).removeprefix("sha256:")
                previous = l4_media.setdefault(relative, expected_hash)
                if previous != expected_hash:
                    raise ValueError(f"L4_MEDIA_HASH_CONFLICT:{relative}")
    l4_items = sorted(l4_media.items())
    if args.limit is not None:
        l4_items = l4_items[:args.limit]
    elif len(l4_items) != 2205:
        raise ValueError(f"L4_MEDIA_COUNT_MISMATCH:{len(l4_items)}")
    l4_index = []
    for relative, expected_hash in l4_items:
        relative_path = safe_relative(relative)
        source = args.hypo_media_root / relative_path
        actual_hash = sha256_file(source)
        if actual_hash != expected_hash:
            raise ValueError(f"L4_MEDIA_SOURCE_HASH_MISMATCH:{source}")
        target = bundle / "media/l4" / relative_path
        copy_file(source, target, args.resume)
        l4_index.append({
            "source_relative_path": relative,
            "bundle_relative_path": str(target.relative_to(bundle)),
            "sha256": f"sha256:{expected_hash}", "bytes": target.stat().st_size,
        })
    l4_index_payload = b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        for row in l4_index
    )
    write_versioned(bundle / "benchmark/l4/evaluation/media_index.jsonl", l4_index_payload, args.resume)

    absolute_request = l1_eval / "requested_samples.available.frames.jsonl"
    portable_rows = []
    for row in read_jsonl(absolute_request):
        value = json.loads(json.dumps(row))
        for media in value.get("media") or []:
            for key in ("path", "source_video_path"):
                raw = media.get(key)
                if raw:
                    path = Path(raw).resolve()
                    if not path.is_relative_to(bundle):
                        raise ValueError(f"MEDIA_OUTSIDE_BUNDLE:{path}")
                    media[key] = str(path.relative_to(bundle))
            if media.get("paths"):
                portable = []
                for raw in media["paths"]:
                    path = Path(raw).resolve()
                    if not path.is_relative_to(bundle):
                        raise ValueError(f"FRAME_OUTSIDE_BUNDLE:{path}")
                    portable.append(str(path.relative_to(bundle)))
                media["paths"] = portable
        portable_rows.append(value)
    portable_payload = b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        for row in portable_rows
    )
    write_versioned(l1_eval / "requested_samples.available.portable.jsonl", portable_payload, args.resume)

    section_stats = {
        name: directory_stats(bundle / name)
        for name in ("benchmark", "media", "documentation", "software", "model_results")
    }
    l4_media_bytes = sum(row["bytes"] for row in l4_index)
    l1_media_bytes = int(l1_report["materialized_bytes"])
    frame_bytes = directory_stats(bundle / "media/l1_l3_video_frames")["bytes"]
    total_before_reports = sum(stats["bytes"] for stats in section_stats.values())
    ca_download_bytes = 11575534117935
    ca_bundle_bytes = int((l1_report.get("materialized_by_dataset") or {}).get("ca_vqa", {}).get("bytes", 0))
    storage_lines = [
        "# SpaceConflict 实际使用数据与长期保存包容量报告", "",
        "生成日期：2026-09-03", "",
        "## 结论", "",
        "本目录不是上游数据集的完整镜像。它保存全部 SpaceConflict 冻结题目与 gold，",
        "以及当前发布实际引用且本地可取得的媒体；未被当前发布引用的 CA-VQA、OmniSpatial、VSI、STI、SPAR 内容没有复制。", "",
        "| 项目 | 数量/容量 |", "|---|---:|",
        "| L1–L3 全部 binary questions | 19,624 |",
        "| L1–L3 全部 Unknown questions | 2,000 |",
        "| L1–L3 可物化媒体输入 | 14,713 |",
        "| L1–L3 SPAR-7M 媒体缺失输入 | 6,911 |",
        f"| L1–L3 去重源媒体 | {l1_report['materialized_unique_files']} files / {human_bytes(l1_media_bytes)} |",
        f"| 视频帧缓存 | {frames_report['materialized_frame_count']} frames / {human_bytes(frame_bytes)} |",
        "| L4 binary questions | 2,272 |",
        "| L4 Unknown questions | 300 |",
        f"| L4 去重媒体 | {len(l4_index)} files / {human_bytes(l4_media_bytes)} |",
        f"| 打包报告生成前总量 | {human_bytes(total_before_reports)} |", "",
        "## CA-VQA 节省量", "",
        f"完整 CA-VQA 下载为 {human_bytes(ca_download_bytes)}；当前发布实际物化的 CA-VQA 图像为 {human_bytes(ca_bundle_bytes)}。",
        "完整下载仍保留在 Slate-Scratch，本包没有复制未引用的 shard 或任务族。", "",
        "## 使用边界", "",
        "- `benchmark/`：全部问题、pair、Unknown、gold、track 标注和盲测输入；",
        "- `media/`：发布引用的可取得媒体和用于 Qwen 的确定性视频帧；",
        "- `documentation/`：构建、审计、问题、可视化和交接信息；",
        "- `software/`：解析、验证、推理和评分代码；",
        "- `model_results/`：已完成的 Qwen2.5-VL-7B 结果；",
        "- SPAR-7M 的题目和 gold 已包含，但缺失媒体仅以 locator/reject 记录，不伪造图像。", "",
        "本目录中的上游媒体只用于实验室内部复现，不代表获得公开再分发授权。", "",
    ]
    write_versioned(
        bundle / "STORAGE_USAGE_REPORT_CN.md", "\n".join(storage_lines).encode(), args.resume,
    )
    readme_lines = [
        "# SpaceConflict Evaluation Bundle v1", "",
        "这是 SpaceConflict 的实验室内部长期保存与 MLLM 评测包。", "",
        "- 从本目录运行相对路径版本：`benchmark/l1_l3/evaluation/requested_samples.available.portable.jsonl`；",
        "- L1–L3 gold：`benchmark/l1_l3/release/claims.jsonl` 与 `unknown_challenge.jsonl`；",
        "- L4 blind input/gold：`benchmark/l4/release/`；",
        "- L4 媒体根：`media/l4/`；",
        "- 缺失媒体清单：`benchmark/l1_l3/evaluation/media_unavailable.jsonl`；",
        "- 完整容量与覆盖说明：`STORAGE_USAGE_REPORT_CN.md`；",
        "- 文件校验：`SHA256SUMS`。", "",
        "重要：媒体为内部复现副本，不得把此目录整体作为公开 benchmark 媒体发布。", "",
    ]
    write_versioned(bundle / "README_CN.md", "\n".join(readme_lines).encode(), args.resume)

    manifest = {
        "schema_version": "spaceconflict_evaluation_bundle_manifest_v1",
        "status": "PASS" if args.limit is None else "PARTIAL_LIMITED",
        "run_id": args.run_id, "seed": args.seed,
        "created_on": "2026-09-03",
        "bundle_root": str(bundle),
        "code_commit": "NOT_AVAILABLE_WORKTREE_NOT_GIT_REPOSITORY",
        "release_counts": {
            "l1_l3_pairs": 9812, "l1_l3_binary_claims": 19624, "l1_l3_unknown": 2000,
            "l4_pairs": 1136, "l4_binary_claims": 2272, "l4_unknown": 300,
        },
        "media_counts": {
            "l1_l3_available_inputs": 14713, "l1_l3_unavailable_inputs": 6911,
            "l1_l3_unique_source_files": l1_report["materialized_unique_files"],
            "l1_l3_video_frames": frames_report["materialized_frame_count"],
            "l4_unique_files": len(l4_index),
        },
        "static_file_counts": static_counts,
        "section_stats_before_manifest_and_checksums": section_stats,
        "input_hashes": {
            "config": sha256_file(ROOT / "configs/evaluation_bundle_v1_20260903.yaml"),
            "l1_l3_manifest": sha256_file(ROOT / "release/production_available_v10/manifest.json"),
            "l4_manifest": sha256_file(ROOT / "l4/v3_3/release/manifest.json"),
            "materialization_report": sha256_file(l1_report_path),
            "video_frame_report": sha256_file(frames_report_path),
        },
        "public_media_redistribution_authorized": False,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
    }
    write_versioned(
        bundle / "MANIFEST.json",
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        args.resume,
    )

    checksum_target = bundle / "SHA256SUMS"
    checksum_rows = []
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and path != checksum_target:
            checksum_rows.append(f"{sha256_file(path)}  {path.relative_to(bundle)}")
    checksum_payload = ("\n".join(checksum_rows) + "\n").encode()
    write_versioned(checksum_target, checksum_payload, args.resume)
    final_stats = directory_stats(bundle)
    print(json.dumps({
        "status": manifest["status"], "bundle_root": str(bundle),
        "files": final_stats["files"], "bytes": final_stats["bytes"],
        "human_bytes": human_bytes(final_stats["bytes"]),
        "checksummed_files": len(checksum_rows),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
