#!/usr/bin/env python3
"""Gate on the Qwen smoke report, then submit the full L4 array and scorer."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "runs/mllm/qwen2_5_vl_7b/l4_balanced_test_v3_20260903"
STATUS_PATH = RUN_ROOT / "deployment_status.json"


def write_status(value: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def submit(*arguments: str) -> str:
    result = subprocess.run(
        ["sbatch", "--parsable", *arguments], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    )
    return result.stdout.strip().split(";", 1)[0]


def main() -> int:
    smoke_path = RUN_ROOT / "smoke_score.json"
    if not smoke_path.is_file():
        raise SystemExit(f"Smoke score is missing: {smoke_path}")
    smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    gates = {
        "evaluated_16": smoke.get("evaluated_count") == 16,
        "missing_predictions_zero": smoke.get("missing_prediction_count") == 0,
        "runtime_errors_zero": smoke.get("runtime_error_count") == 0,
        "strict_json_rate_one": smoke.get("strict_json_valid_rate") == 1.0,
        "schema_valid_rate_one": smoke.get("schema_valid_rate") == 1.0,
    }
    base = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "smoke_job_id": "8143524",
        "smoke_score": str(smoke_path),
        "gates": gates,
    }
    if not all(gates.values()):
        write_status({**base, "status": "BLOCKED_SMOKE_GATE", "full_job_id": None, "score_job_id": None})
        return 2
    full_job_id = submit("scripts/run_qwen25vl7b_l4_full.sbatch")
    try:
        score_job_id = submit(
            f"--dependency=afterok:{full_job_id}",
            "scripts/score_qwen25vl7b_l4_full.sbatch",
        )
    except Exception:
        write_status({**base, "status": "FULL_SUBMITTED_SCORE_SUBMISSION_FAILED", "full_job_id": full_job_id, "score_job_id": None})
        raise
    write_status({
        **base,
        "status": "FULL_AND_SCORE_SUBMITTED",
        "full_job_id": full_job_id,
        "score_job_id": score_job_id,
    })
    print(STATUS_PATH.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

