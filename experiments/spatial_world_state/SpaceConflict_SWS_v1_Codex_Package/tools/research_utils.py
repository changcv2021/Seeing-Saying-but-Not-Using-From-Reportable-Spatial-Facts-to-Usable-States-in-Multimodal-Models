#!/usr/bin/env python3
"""Small, dependency-light planning and validation helpers; NOT an inference runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Sequence


def strict_json_loads(text: str) -> Any:
    """Reject duplicate keys and nonstandard NaN/Infinity instead of silently repairing."""
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"Duplicate JSON key: {key}")
            out[key] = value
        return out
    def bad_constant(value: str) -> None:
        raise ValueError(f"Non-finite JSON constant: {value}")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=bad_constant)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def typed_equal(left: Any, right: Any) -> bool:
    # bool must not be treated as integer 0/1; count normalization is a separate contract.
    return type(left) is type(right) and left == right


def exact_claim_label(compatible_values: Sequence[Any], claim_value: Any) -> str:
    """Finite, explicitly enumerated compatible states for an exact-value claim.

    Not a general spatial prover. Empty/inconsistent evidence is INVALID, not UNKNOWN.
    None represents an insufficient-value response, not an actual member of the domain.
    """
    if not compatible_values:
        raise ValueError("Empty compatible world set: resolve source inconsistency first")
    if claim_value is None or isinstance(claim_value, bool):
        raise ValueError("Claim value must be an actual typed value")
    if any(v is None or isinstance(v, bool) for v in compatible_values):
        raise ValueError("Enumerate actual compatible values, not null/bool placeholders")
    truth = [typed_equal(v, claim_value) for v in compatible_values]
    if all(truth):
        return "SUPPORTED"
    if not any(truth):
        return "CONTRADICTORY"
    return "UNKNOWN"


def validate_split_records(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Validate already-established global clusters, NOT discover near-duplicates."""
    cluster_splits: dict[str, str] = {}
    record_ids: set[str] = set()
    n = 0
    for row in records:
        n += 1
        for key in ("record_id", "world_cluster_id", "split"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"Row {n}: missing nonempty {key}")
        if row["record_id"] in record_ids:
            raise ValueError(f"Duplicate record_id: {row['record_id']}")
        record_ids.add(row["record_id"])
        if row["split"] not in {"discovery", "validation", "confirmation", "history"}:
            raise ValueError(f"Unrecognized study split: {row['split']}")
        if row.get("previously_exposed", False) and row["split"] not in {"history", "discovery"}:
            raise ValueError(f"Exposed world in non-discovery split: {row['world_cluster_id']}")
        cluster = row["world_cluster_id"]
        canonical_split = "discovery" if row["split"] == "history" else row["split"]
        old = cluster_splits.setdefault(cluster, canonical_split)
        if old != canonical_split:
            raise ValueError(f"Cross-split leakage: {cluster}: {old} vs {row['split']}")
    return {"records": n, "world_clusters": len(cluster_splits)}


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    import gzip
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                row = strict_json_loads(line)
                if not isinstance(row, dict):
                    raise ValueError("JSONL record is not an object")
            except (ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"{path.name}:{line_no}: {exc}") from exc
            yield row


def planned_counts(config: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for key, spec in config["experiments"].items():
        if key == "E0" or not spec.get("enabled", False):
            continue
        if "requests_per_model_cap" in spec:
            n = spec["requests_per_model_cap"]
        else:
            n = spec["worlds_cap"] * spec["calls_per_world_cap"]
        if type(n) is not int or n < 0:
            raise ValueError(f"Invalid nonnegative integer cap for {key}")
        counts[key] = n
    total = sum(counts.values())
    return {"status": "PLAN_NOT_EXECUTED", "logical_upper_bounds_per_model": counts,
            "per_model_total": total, "all_models_total": total * len(config["models"]),
            "excludes": ["E0 inventory-specific calls", "whitebox forwards", "infra retries"],
            "note": "Not a GPU-hour authorization and not observed response counts"}


def estimate_gpu_hours(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    total = 0.0
    for p in profiles:
        fields = ("gpus_per_worker", "forward_count", "seconds_per_forward", "shards", "load_seconds")
        if any(not isinstance(p.get(k), (int, float)) or isinstance(p[k], bool)
               or not math.isfinite(p[k]) or p[k] < 0 for k in fields):
            raise ValueError("Cost estimate requires nonnegative measured numeric fields")
        if p["gpus_per_worker"] <= 0:
            raise ValueError("GPU count must be positive")
        hours = p["gpus_per_worker"] * (
            p["forward_count"] * p["seconds_per_forward"] + p["shards"] * p["load_seconds"]
        ) / 3600.0
        total += hours
        rows.append({"profile": p.get("profile", "unknown"), "estimated_gpu_hours": hours,
                     "timing_source": p.get("timing_source", "UNSPECIFIED")})
    return {"status": "ESTIMATE_NOT_USAGE", "profiles": rows, "total_gpu_hours": total,
            "queue_wait_included": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("plan-counts")
    c.add_argument("config", type=Path)
    s = sub.add_parser("validate-splits")
    s.add_argument("manifest", type=Path)
    e = sub.add_parser("estimate")
    e.add_argument("profiles", type=Path, help="JSON array with actual smoke timing inputs")
    args = parser.parse_args()
    if args.command == "plan-counts":
        if args.config.suffix in {".yaml", ".yml"}:
            try:
                import yaml
            except ImportError as exc:
                raise SystemExit("Install PyYAML, or provide the same config as JSON") from exc
            config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
        else:
            config = strict_json_loads(args.config.read_text(encoding="utf-8"))
        result = planned_counts(config)
    elif args.command == "validate-splits":
        result = validate_split_records(read_jsonl(args.manifest))
    else:
        profiles = strict_json_loads(args.profiles.read_text(encoding="utf-8"))
        result = estimate_gpu_hours(profiles)
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
