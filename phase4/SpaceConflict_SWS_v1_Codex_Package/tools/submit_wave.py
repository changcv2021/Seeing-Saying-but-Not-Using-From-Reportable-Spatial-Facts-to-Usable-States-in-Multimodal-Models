#!/usr/bin/env python3
"""Validate and submit READY Slurm arrays. Default is dry-run; never polls the scheduler.

This is a scheduling template, not an institution permission checker or a model worker.
The evidence and site resource values must be populated from real project records.
"""
from __future__ import annotations
import argparse
import json
import math
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from research_utils import strict_json_loads, sha256_file


def positive_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return float(value)


def nonnegative_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return float(value)


def positive_int(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def require_evidence(path: Any, expected_sha: Any, name: str) -> Path:
    if not isinstance(path, str) or not Path(path).is_file():
        raise ValueError(f"Missing {name} file")
    p = Path(path).resolve()
    if not isinstance(expected_sha, str) or sha256_file(p) != expected_sha:
        raise ValueError(f"SHA256 mismatch for {name}")
    return p


def validate_wave(plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("authorization_status") != "CONFIRMED_EXISTING_OR_CURRENT_USER":
        raise ValueError("Total resource authorization is unresolved; obtain one consolidated authorization")
    if plan.get("site_limits_verified") is not True:
        raise ValueError("Current site/account limits must be verified")
    if plan.get("status") != "READY_FROZEN_WAVE":
        raise ValueError("Wave is not a frozen READY wave")
    require_evidence(plan.get("authorization_evidence"), plan.get("authorization_sha256"), "authorization")
    for key in ("account", "partition", "qos"):
        if not isinstance(plan.get(key), str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", plan[key]):
            raise ValueError(f"Unresolved or invalid {key}")
    cap = positive_number(plan.get("total_gpu_hours_ceiling"), "total_gpu_hours_ceiling")
    spent = nonnegative_number(plan.get("spent_gpu_hours", 0), "spent_gpu_hours")
    reserved = nonnegative_number(plan.get("reserved_gpu_hours_outside_wave", 0), "reserved_gpu_hours_outside_wave")
    allowed_slots = positive_int(plan.get("concurrent_gpu_ceiling"), "concurrent_gpu_ceiling")
    slots = nonnegative_number(plan.get("outside_wave_gpu_slots", 0), "outside_wave_gpu_slots")
    max_workers = positive_int(plan.get("site_array_running_tasks_ceiling"), "site_array_running_tasks_ceiling")
    workers = nonnegative_number(plan.get("outside_wave_running_task_slots", 0), "outside_wave_running_task_slots")
    max_submitted = positive_int(plan.get("site_submitted_tasks_ceiling"), "site_submitted_tasks_ceiling")
    submitted = nonnegative_number(plan.get("outside_wave_submitted_tasks", 0), "outside_wave_submitted_tasks")
    arrays = plan.get("arrays")
    if not isinstance(arrays, list) or not arrays:
        raise ValueError("No ready arrays")
    names: set[str] = set()
    requested_hours = 0.0
    for a in arrays:
        name = a.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in names:
            raise ValueError("Invalid or repeated array name")
        names.add(name)
        if a.get("scientific_gate_pass") is not True or a.get("smoke_pass") is not True:
            raise ValueError(f"{name}: review/freeze or per-model smoke gate incomplete")
        require_evidence(a.get("gate_file"), a.get("gate_sha256"), f"{name} gate")
        require_evidence(a.get("shard_table"), a.get("shard_table_sha256"), f"{name} shards")
        n = positive_int(a.get("shards"), "shards")
        parallel = positive_int(a.get("parallelism"), "parallelism")
        gpus = positive_int(a.get("gpus"), "gpus")
        if parallel > n:
            raise ValueError(f"{name}: parallelism exceeds shard count")
        hours = positive_number(a.get("wall_hours"), "wall_hours")
        if hours > positive_number(plan.get("site_max_wall_hours"), "site_max_wall_hours"):
            raise ValueError("Walltime exceeds site profile limit")
        positive_int(a.get("cpus"), "cpus")
        positive_int(a.get("mem_gb"), "mem_gb")
        if a.get("dependency_type", "afterok") not in {"afterok", "aftercorr"}:
            raise ValueError("Inference dependency must require predecessor success")
        for dep in a.get("dependencies", []):
            if not re.fullmatch(r"\d+(?:_\d+)?", str(dep)):
                raise ValueError("Dependency must be an actual Slurm job ID")
        slots += min(n, parallel) * gpus
        workers += min(n, parallel)
        submitted += n
        requested_hours += n * hours * gpus
    if slots > allowed_slots:
        raise ValueError("Combined waves exceed concurrent GPU ceiling")
    if workers > max_workers or submitted > max_submitted:
        raise ValueError("Combined waves exceed verified running/submitted task limits")
    if spent + reserved + requested_hours > cap:
        raise ValueError("Reserved GPU-hour envelope exceeds remaining authorized budget")
    return {"max_concurrent_gpu_slots_with_other_waves": slots,
            "reserved_new_gpu_hours": requested_hours, "arrays": len(arrays)}


def walltime(hours: float) -> str:
    seconds = math.ceil(hours * 3600)
    h, seconds = divmod(seconds, 3600)
    m, s = divmod(seconds, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def commands(plan: dict[str, Any], worker: Path, repo_root: Path, run_root: Path) -> list[tuple[str, list[str]]]:
    out = []
    for a in plan["arrays"]:
        cmd = ["sbatch", "--parsable", f"--account={plan['account']}",
               f"--partition={plan['partition']}", f"--qos={plan['qos']}",
               f"--job-name=sws_{a['name']}", f"--array=0-{a['shards']-1}%{a['parallelism']}",
               f"--gres=gpu:{a['gpus']}", f"--cpus-per-task={a['cpus']}",
               f"--mem={a['mem_gb']}G", f"--time={walltime(a['wall_hours'])}",
               f"--output={run_root / 'scheduler' / 'logs' / (a['name'] + '_%A_%a.out')}",
               f"--error={run_root / 'scheduler' / 'logs' / (a['name'] + '_%A_%a.err')}"]
        if a.get("dependencies"):
            cmd.append("--dependency=" + a.get("dependency_type", "afterok") + ":" +
                       ":".join(str(d) for d in a["dependencies"]))
        cmd.extend([str(worker.resolve()), str(repo_root.resolve()), str(run_root.resolve()),
                    a["model_id"], str(Path(a["shard_table"]).resolve())])
        out.append((a["name"], cmd))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("plan", type=Path)
    ap.add_argument("--repo-root", required=True, type=Path)
    ap.add_argument("--run-root", required=True, type=Path)
    ap.add_argument("--worker", type=Path, default=Path(__file__).with_name("slurm_array_worker.sh"))
    ap.add_argument("--submit", action="store_true")
    args = ap.parse_args()
    try:
        plan = strict_json_loads(args.plan.read_text(encoding="utf-8"))
        check = validate_wave(plan)
        if not args.worker.is_file() or not args.repo_root.is_dir():
            raise ValueError("Worker template or repository missing")
        wave_commands = commands(plan, args.worker, args.repo_root, args.run_root)
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(f"BLOCKED: {exc}") from exc
    print(json.dumps({"mode": "SUBMIT" if args.submit else "DRY_RUN", **check}, ensure_ascii=False))
    if args.submit:
        (args.run_root / "scheduler" / "logs").mkdir(parents=True, exist_ok=True)
    for name, cmd in wave_commands:
        print(shlex.join(cmd))
        if not args.submit:
            continue
        result = subprocess.run(cmd, text=True, capture_output=True, check=False)
        entry = {"time_utc": datetime.now(timezone.utc).isoformat(), "array_name": name,
                 "command": cmd, "returncode": result.returncode,
                 "stdout": result.stdout.strip(), "stderr": result.stderr.strip(),
                 "plan_sha256": sha256_file(args.plan)}
        with (args.run_root / "scheduler" / "submitted_jobs.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if result.returncode != 0:
            raise SystemExit("Submission failed; existing accepted arrays remain logged. Do not resubmit the whole wave.")
        job_id = result.stdout.strip().split(";", 1)[0]
        if not re.fullmatch(r"\d+", job_id):
            raise SystemExit("Unexpected sbatch output; inspect ledger before any retry")
        print(f"ACCEPTED {name} job_id={job_id}; this does not mean the job has started or completed.")


if __name__ == "__main__":
    main()
