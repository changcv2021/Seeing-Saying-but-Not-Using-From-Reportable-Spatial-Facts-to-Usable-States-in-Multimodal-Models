from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from spaceconflict.l4_three_part.pipeline import run_action
from spaceconflict.logging_utils import run_envelope, write_run_log


ACTIONS = (
    "freeze-native",
    "build-native",
    "build-controlled-pilot",
    "build-controlled-full",
    "build-unknown",
    "build-release",
)
SUCCESS = {
    "PLANNED", "NATIVE_BASE_FROZEN", "NATIVE_ACCEPTED", "NATIVE_SHORTFALL",
    "CONTROLLED_ACCEPTED", "UNKNOWN_ACCEPTED", "L4_THREE_PART_RELEASE_VALID",
}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="build_l4_three_part")
    value.add_argument("action", choices=ACTIONS)
    value.add_argument("--dry-run", action="store_true")
    value.add_argument("--resume", action="store_true")
    value.add_argument("--seed", type=int, default=20260829)
    value.add_argument("--run-id", default="l4_three_part_manual")
    value.add_argument("--limit", type=int)
    value.add_argument("--world-id")
    value.add_argument("--branch-id")
    value.add_argument("--workers", type=int, default=1)
    value.add_argument("--output-root", type=Path)
    value.add_argument("--media-root", type=Path)
    value.add_argument("--target-pairs", type=int)
    value.add_argument("--scene-limit", type=int)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be >= 1")
    if args.target_pairs is not None and args.target_pairs < 1:
        raise SystemExit("--target-pairs must be >= 1")
    try:
        result = run_action(args.action, args)
        exception = None
        code = 0 if result.get("status") in SUCCESS else 2
    except Exception as error:
        traceback.print_exc()
        exception = {"type": type(error).__name__, "message": str(error)}
        result = {"status": "FAILED_EXCEPTION", "exception": exception}
        code = 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if not args.dry_run:
        log = run_envelope(
            f"l4-three-part-{args.action}", args,
            {"success": int(code == 0), "failure": int(code != 0)},
            result=result, exception=exception,
        )
        path = write_run_log(log)
        print(json.dumps({"run_log": str(path)}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
