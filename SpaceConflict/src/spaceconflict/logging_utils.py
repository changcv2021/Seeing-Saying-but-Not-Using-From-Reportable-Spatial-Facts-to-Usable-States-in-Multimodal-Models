from __future__ import annotations

import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hashing import sha256_file
from .registry import ROOT


def git_commit(root: Path = ROOT) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _status_counts(value: Any) -> dict[str, int]:
    counts: Counter[str] = Counter()
    def visit(item: Any) -> None:
        if isinstance(item, dict):
            if isinstance(item.get("status"), str):
                counts[item["status"]] += 1
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
    visit(value)
    return dict(sorted(counts.items()))


def _hash_fields(value: Any) -> dict[str, dict[str, str]]:
    collected: dict[str, dict[str, str]] = {"input_hashes": {}, "output_hashes": {}}
    def visit(item: Any, location: str) -> None:
        if isinstance(item, dict):
            for field in ("input_hashes", "output_hashes"):
                hashes = item.get(field)
                if isinstance(hashes, dict):
                    for path, digest in hashes.items():
                        collected[field][f"{location}:{path}"] = str(digest)
            for key, child in item.items():
                visit(child, f"{location}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{location}[{index}]")
    visit(value, "result")
    return collected


def _config_snapshot(args: Any) -> dict[str, Any]:
    snapshot = {key: _jsonable(value) for key, value in vars(args).items()}
    config = getattr(args, "config", None)
    if isinstance(config, Path) and config.is_file():
        snapshot["config_file"] = {
            "path": str(config), "sha256": sha256_file(config),
            "content": config.read_text(encoding="utf-8"),
        }
    return snapshot


def _dataset_revisions(args: Any, root: Path = ROOT) -> dict[str, Any]:
    requested = getattr(args, "dataset", None)
    if requested is None:
        return {}
    names = sorted(path.parent.name for path in (root / "reports").glob("*/source_discovery.json"))
    if requested != "all":
        names = [requested]
    revisions: dict[str, Any] = {}
    for name in names:
        path = root / "reports" / name / "source_discovery.json"
        if not path.is_file():
            revisions[name] = {"status": "MISSING_SOURCE_DISCOVERY"}
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        revisions[name] = {
            "source_revision": report.get("source_revision"),
            "data_revision": report.get("data_revision"),
            "license_id": report.get("license_id"),
        }
    return revisions


def run_envelope(
    command: str, args: Any, counts: dict[str, int] | None = None,
    result: dict[str, Any] | None = None, exception: dict[str, str] | None = None,
) -> dict[str, Any]:
    result = result or {}
    hashes = _hash_fields(result)
    return {
        "run_id": args.run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "dry_run": args.dry_run,
        "resume": args.resume,
        "seed": args.seed,
        "limit": args.limit,
        "world_id": args.world_id,
        "workers": args.workers,
        "git_commit": git_commit() or "UNVERSIONED",
        "hostname": os.uname().nodename,
        "counts": counts or {},
        "status_counts": _status_counts(result),
        "config_snapshot": _config_snapshot(args),
        "dataset_revisions": _dataset_revisions(args),
        "input_hashes": hashes["input_hashes"],
        "output_hashes": hashes["output_hashes"],
        "result_status": result.get("status"),
        "exception": exception,
    }


def write_run_log(envelope: dict[str, Any], root: Path = ROOT) -> Path:
    run_id = envelope["run_id"]
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{envelope['command']}.json"
    sequence = 1
    while path.exists():
        path = run_dir / f"{envelope['command']}_{sequence:03d}.json"
        sequence += 1
    path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
