from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from spaceconflict.hashing import sha256_file
from spaceconflict.hypo3d_l4.common import canonical_json


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def key(row: dict[str, Any]) -> tuple[str, str, str]:
    return str(row["scene_id"]), str(row["change_id"]), str(row["question_id"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fusion-resolutions", type=Path, required=True)
    parser.add_argument("--preferred-resolutions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--run-id", default="hypo3d_resolution_fusion_v1")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.output.exists() and not args.resume:
        raise FileExistsError(args.output)
    fusion_rows = read_jsonl(args.fusion_resolutions)
    preferred_rows = read_jsonl(args.preferred_resolutions)
    merged = {key(row): row for row in fusion_rows}
    counts: Counter[str] = Counter()
    for row in preferred_rows[: args.limit]:
        current_key = key(row)
        existing = merged.get(current_key)
        if existing is None:
            merged[current_key] = row
            counts["preferred_only_added"] += 1
        elif row.get("resolved_targets"):
            merged[current_key] = row
            counts["preferred_grounding_selected"] += 1
        else:
            counts["fusion_resolution_retained"] += 1
    output_rows = [merged[current_key] for current_key in sorted(merged)]
    report = {
        "schema_version": "hypo3d_resolution_set_fusion_v1",
        "status": "TARGET_RESOLUTION_VALID",
        "run_id": args.run_id,
        "seed": args.seed,
        "fusion_resolution_count": len(fusion_rows),
        "preferred_resolution_count": len(preferred_rows),
        "merged_resolution_count": len(output_rows),
        "counts": dict(sorted(counts.items())),
        "input_hashes": {
            str(args.fusion_resolutions): sha256_file(args.fusion_resolutions),
            str(args.preferred_resolutions): sha256_file(args.preferred_resolutions),
        },
    }
    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(b"".join(canonical_json(row) + b"\n" for row in output_rows))
    report["output_hash"] = sha256_file(args.output)
    (args.output.parent / "target_resolution_set_fusion_report.v1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
