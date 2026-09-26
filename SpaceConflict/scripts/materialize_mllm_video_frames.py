#!/usr/bin/env python3
"""Convert materialized videos to deterministic ordered frame lists for robust MLLM input."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


FORBIDDEN_KEYS = {"label", "gold", "proof", "certificate"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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


def write_versioned(path: Path, payload: bytes, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume:
            raise FileExistsError(f"OUTPUT_EXISTS:{path}")
        if path.read_bytes() != payload:
            raise ValueError(f"NONDETERMINISTIC_OUTPUT:{path}")
        return
    path.write_bytes(payload)


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


def duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    value = float(result.stdout.strip())
    if value <= 0:
        raise ValueError(f"VIDEO_DURATION_INVALID:{path}:{value}")
    return value


def extract_frames(video: Path, destination: Path, frame_count: int, resume: bool) -> tuple[list[Path], float]:
    existing = sorted(destination.glob("frame_*.jpg")) if destination.exists() else []
    if existing:
        if not resume:
            raise FileExistsError(f"VIDEO_FRAME_CACHE_EXISTS:{destination}")
        if len(existing) != frame_count or any(path.stat().st_size == 0 for path in existing):
            raise ValueError(f"VIDEO_FRAME_CACHE_INVALID:{destination}:{len(existing)}")
        return existing, duration(video)
    destination.parent.mkdir(parents=True, exist_ok=True)
    video_duration = duration(video)
    sample_fps = frame_count / video_duration
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        command = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-threads", "1", "-filter_threads", "1",
            "-i", str(video), "-vf", f"fps={sample_fps:.12f}", "-frames:v", str(frame_count), "-q:v", "2",
            str(temporary / "frame_%03d.jpg"),
        ]
        subprocess.run(command, check=True)
        frames = sorted(temporary.glob("frame_*.jpg"))
        if not frames:
            raise ValueError(f"VIDEO_FRAME_EXTRACTION_EMPTY:{video}")
        while len(frames) < frame_count:
            target = temporary / f"frame_{len(frames) + 1:03d}.jpg"
            shutil.copyfile(frames[-1], target)
            frames.append(target)
        if len(frames) != frame_count or any(path.stat().st_size == 0 for path in frames):
            raise ValueError(f"VIDEO_FRAME_EXTRACTION_INVALID:{video}:{len(frames)}")
        temporary.rename(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return sorted(destination.glob("frame_*.jpg")), video_duration


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--frame-count", type=int, default=16)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260903)
    parser.add_argument("--run-id", default="qwen25vl7b_v10_video_frames_20260903")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.frame_count < 2 or args.frame_count % 2:
        raise ValueError("FRAME_COUNT_MUST_BE_EVEN_AND_AT_LEAST_TWO")
    rows = read_jsonl(args.input)
    if args.limit is not None:
        rows = rows[:args.limit]
    video_paths = sorted({media["path"] for row in rows for media in row.get("media") or [] if media.get("kind") == "video"})
    missing = [path for path in video_paths if not Path(path).is_file()]
    if missing:
        raise ValueError(f"SOURCE_VIDEO_MISSING:{len(missing)}")
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "run_id": args.run_id, "samples": len(rows), "videos": len(video_paths), "frame_count": args.frame_count}, sort_keys=True))
        return 0

    cache: dict[str, dict[str, Any]] = {}
    for raw_path in video_paths:
        path = Path(raw_path)
        digest = sha256_file(path)
        destination = args.cache_root / digest[:24]
        frames, video_duration = extract_frames(path, destination, args.frame_count, args.resume)
        cache[raw_path] = {
            "kind": "video_frames", "paths": [str(frame) for frame in frames],
            "frame_sha256": [sha256_file(frame) for frame in frames],
            "source_video_path": raw_path, "source_video_sha256": digest,
            "source_video_duration_seconds": round(video_duration, 6),
            "sample_fps": args.frame_count / video_duration, "frame_count": args.frame_count,
        }

    transformed = []
    for row in rows:
        value = dict(row)
        media_rows = []
        for media in row.get("media") or []:
            if media.get("kind") == "video":
                replacement = dict(cache[media["path"]])
                replacement["role"] = media.get("role")
                media_rows.append(replacement)
            else:
                media_rows.append(media)
        value["media"] = media_rows
        transformed.append(value)
    forbidden = set().union(*(contains_forbidden(row) for row in transformed)) if transformed else set()
    if forbidden:
        raise ValueError(f"GOLD_LEAKAGE_KEYS:{sorted(forbidden)}")
    payload = jsonl_bytes(transformed)
    report = {
        "schema_version": "spaceconflict_mllm_video_frame_materialization_v1", "status": "PASS",
        "run_id": args.run_id, "seed": args.seed, "sample_count": len(transformed),
        "source_video_count": len(video_paths), "frame_count_per_video": args.frame_count,
        "materialized_frame_count": len(video_paths) * args.frame_count,
        "input_sha256": sha256_file(args.input), "output_sha256": hashlib.sha256(payload).hexdigest(),
        "forbidden_gold_keys": [], "videos": cache,
    }
    write_versioned(args.output, payload, args.resume)
    write_versioned(args.report, (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(), args.resume)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
