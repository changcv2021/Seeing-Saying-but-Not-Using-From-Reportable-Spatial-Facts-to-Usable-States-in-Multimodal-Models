from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from spaceconflict.hashing import sha256_file
from spaceconflict.hypo3d_l4.restricted_pickle import load_restricted_annotation_pickle


def shape(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"python_type": type(value).__name__}
    if isinstance(value, dict):
        result["length"] = len(value)
        result["key_types"] = dict(sorted(Counter(type(key).__name__ for key in value).items()))
        result["first_keys"] = [str(key) for key in list(value)[:5]]
        first = next(iter(value.values()), None)
        result["first_value_type"] = type(first).__name__
        if isinstance(first, dict):
            result["first_value_keys"] = sorted(str(key) for key in first)
        elif isinstance(first, list):
            result["first_value_length"] = len(first)
            result["first_list_item_type"] = type(first[0]).__name__ if first else None
            if first and isinstance(first[0], dict):
                result["first_list_item_keys"] = sorted(str(key) for key in first[0])
    elif isinstance(value, list):
        result["length"] = len(value)
        result["first_item_type"] = type(value[0]).__name__ if value else None
        if value and isinstance(value[0], dict):
            result["first_item_keys"] = sorted(str(key) for key in value[0])
    return result


def compact_sample(value: Any) -> Any:
    if isinstance(value, dict):
        key = next(iter(value), None)
        return {str(key): value[key]} if key is not None else {}
    if isinstance(value, list):
        return value[:1]
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rscan", type=Path, required=True)
    parser.add_argument("--nr3d", type=Path, required=True)
    parser.add_argument("--scanrefer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--run-id", default="hypo3d_llm_data_profile_v1")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.output.exists() and not args.resume:
        raise FileExistsError(args.output)
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "output": str(args.output)}, indent=2))
        return

    payloads = {
        "3rscan_scene_cap": json.loads(args.rscan.read_text(encoding="utf-8")),
        "nr3d_captions_by_scene": load_restricted_annotation_pickle(args.nr3d),
        "scanrefer_captions_by_scene": load_restricted_annotation_pickle(args.scanrefer),
    }
    report = {
        "schema_version": "hypo3d_llm_data_profile_v1",
        "status": "HYPO3D_LLM_DATA_PROFILED",
        "run_id": args.run_id,
        "seed": args.seed,
        "profiles": {name: shape(value) for name, value in payloads.items()},
        "samples": {name: compact_sample(value) for name, value in payloads.items()},
        "input_hashes": {
            str(path): sha256_file(path) for path in (args.rscan, args.nr3d, args.scanrefer)
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["profiles"], ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
