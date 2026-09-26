from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import pyarrow.parquet as pq

from .common import AdapterResult
from .ca_vqa import ADAPTER_VERSION as CA_ADAPTER_VERSION, adapt as adapt_ca
from .hypo3d import ADAPTER_VERSION as HYPO3D_ADAPTER_VERSION, adapt as adapt_hypo3d
from .omnispatial import ADAPTER_VERSION as OMNI_ADAPTER_VERSION, adapt as adapt_omni
from .spar import ADAPTER_VERSION as SPAR_ADAPTER_VERSION, adapt as adapt_spar
from .sti_bench import ADAPTER_VERSION as STI_ADAPTER_VERSION, adapt as adapt_sti
from .vsi_bench import ADAPTER_VERSION as VSI_ADAPTER_VERSION, adapt as adapt_vsi
from ..profiling.profile import REVISIONS
from ..registry import ROOT


ADAPTER_VERSIONS = {
    "ca_vqa": CA_ADAPTER_VERSION,
    "hypo3d": HYPO3D_ADAPTER_VERSION,
    "sti_bench": STI_ADAPTER_VERSION,
    "vsi_bench": VSI_ADAPTER_VERSION,
    "spar": SPAR_ADAPTER_VERSION,
    "omnispatial": OMNI_ADAPTER_VERSION,
}


def _load_rows(dataset: str, root: Path) -> list[dict[str, Any]]:
    revision = REVISIONS[dataset]
    raw = root / "data" / "raw" / dataset / revision
    if dataset == "ca_vqa":
        staging = root / "data/staging/ca_vqa" / revision / "ca_vqa_val_metadata_v1"
        rows: list[dict[str, Any]] = []
        for task in ("binary", "cardinality", "multichoice"):
            with (staging / f"{task}.jsonl").open("r", encoding="utf-8") as handle:
                rows.extend(json.loads(line) for line in handle if line.strip())
        return rows
    if dataset == "sti_bench":
        return pq.read_table(raw / "qa.parquet").to_pylist()
    if dataset == "vsi_bench":
        with (raw / "test.jsonl").open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    if dataset == "spar":
        first = [item["row"] for item in json.loads((raw / "first_rows.json").read_text(encoding="utf-8"))["rows"]]
        relations = [item["row"] for item in json.loads((raw / "filtered_obj_spatial_relation_oc_mv.json").read_text(encoding="utf-8"))["rows"]]
        return first + relations
    if dataset == "omnispatial":
        return json.loads((raw / "data.json").read_text(encoding="utf-8"))
    if dataset == "hypo3d":
        annotations = json.loads((raw / "hypo3d.json").read_text(encoding="utf-8"))
        rows: list[dict[str, Any]] = []
        for base_scene_id, branches in annotations.items():
            for branch_index, branch in enumerate(branches):
                for qa in branch.get("questions_answers", []):
                    rows.append({
                        "base_scene_id": base_scene_id,
                        "branch_index": branch_index,
                        "context_change": branch.get("context_change"),
                        "change_type": branch.get("change_type"),
                        **qa,
                    })
        return rows
    raise KeyError(dataset)


def _adapter(dataset: str) -> Callable[[dict[str, Any], int], AdapterResult]:
    return {
        "ca_vqa": adapt_ca,
        "hypo3d": adapt_hypo3d,
        "sti_bench": adapt_sti, "vsi_bench": adapt_vsi, "spar": adapt_spar,
        "omnispatial": adapt_omni,
    }[dataset]


def _valid_media_report(dataset: str, root: Path) -> Path | None:
    report_dir = root / "reports" / dataset
    for path in sorted(report_dir.glob("media_validation.*.json"), reverse=True):
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("status") == "PILOT_MEDIA_VALID":
            return path
    return None


def build_adapter_outputs(dataset: str, *, dry_run: bool, limit: int | None, resume: bool, root: Path = ROOT) -> dict[str, Any]:
    if dataset not in REVISIONS:
        return {"dataset": dataset, "status": "BLOCKED_SOURCE", "reason": "NO_DETERMINISTIC_ADAPTER"}
    revision = REVISIONS[dataset]
    adapter_version = ADAPTER_VERSIONS[dataset]
    candidate_path = root / "data" / "staging" / "adapters" / dataset / revision / adapter_version / "fact_candidates.jsonl"
    reject_path = root / "rejected" / "metadata" / dataset / revision / f"{adapter_version}.jsonl"
    if dry_run:
        return {"dataset": dataset, "status": "PLANNED", "candidate_output": str(candidate_path.relative_to(root)), "reject_output": str(reject_path.relative_to(root)), "limit": limit}
    if (candidate_path.exists() or reject_path.exists()) and not resume:
        raise FileExistsError(f"Adapter output already exists for {dataset}; use --resume to verify/rebuild versioned outputs")
    rows = _load_rows(dataset, root)
    if limit is not None:
        rows = rows[:limit]
    adapter = _adapter(dataset)
    results = [adapter(row, index) for index, row in enumerate(rows)]
    candidates = [result.to_dict() for result in results if result.status == "WAITING_MEDIA"]
    rejects = [result.to_dict() for result in results if result.status == "REJECTED"]
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    reject_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_payload = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in candidates)
    reject_payload = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in rejects)
    if resume and candidate_path.exists() and candidate_path.read_text(encoding="utf-8") != candidate_payload:
        raise ValueError(f"Non-deterministic candidate adapter output for {dataset}")
    if resume and reject_path.exists() and reject_path.read_text(encoding="utf-8") != reject_payload:
        raise ValueError(f"Non-deterministic reject adapter output for {dataset}")
    if not candidate_path.exists():
        candidate_path.write_text(candidate_payload, encoding="utf-8")
    if not reject_path.exists():
        reject_path.write_text(reject_payload, encoding="utf-8")
    reject_counts = Counter(code for result in rejects for code in result["reject_codes"])
    reconstruction_failures = sum(not item["reconstruction_pass"] for item in candidates)
    return {
        "dataset": dataset, "status": "ADAPTER_VALID" if reconstruction_failures == 0 else "REJECTED",
        "profiled_rows": len(rows), "candidate_count": len(candidates), "rejected_count": len(rejects),
        "reject_code_counts": dict(sorted(reject_counts.items())),
        "candidate_reconstruction_failures": reconstruction_failures,
        "canonical_records_written": 0,
        "canonical_gate": "MISSING_MEDIA" if dataset != "spar" else "MISSING_MEDIA_AND_BLOCKED_LICENSE",
    }


def reconstruct_source_qa(dataset: str, *, dry_run: bool, root: Path = ROOT) -> dict[str, Any]:
    if dataset not in REVISIONS:
        return {"dataset": dataset, "status": "BLOCKED_SOURCE", "reason": "NO_DETERMINISTIC_ADAPTER"}
    revision = REVISIONS[dataset]
    adapter_version = ADAPTER_VERSIONS[dataset]
    candidate_path = root / "data" / "staging" / "adapters" / dataset / revision / adapter_version / "fact_candidates.jsonl"
    output_path = root / "reports" / dataset / f"source_reconstruction.{adapter_version}.json"
    latest_output_path = root / "reports" / dataset / "source_reconstruction.json"
    if dry_run:
        return {"dataset": dataset, "status": "PLANNED", "input": str(candidate_path.relative_to(root)), "output": str(output_path.relative_to(root))}
    if not candidate_path.exists():
        return {"dataset": dataset, "status": "BLOCKED_SOURCE", "reason": "ADAPTER_OUTPUT_MISSING"}
    with candidate_path.open("r", encoding="utf-8") as handle:
        candidates = [json.loads(line) for line in handle if line.strip()]
    failures = [item["source_item_id"] for item in candidates if not item["reconstruction_pass"]]
    rate = 1.0 if not candidates else (len(candidates) - len(failures)) / len(candidates)
    selected_report = _valid_media_report(dataset, root)
    media_valid = selected_report is not None
    media_validation_report = (
        str(selected_report.relative_to(root)) if selected_report is not None else None
    )
    report = {
        "dataset": dataset, "source_revision": revision, "adapter_version": adapter_version,
        "scope": "metadata_adapter_candidates_waiting_media_validation",
        "candidate_count": len(candidates), "reconstruction_pass_count": len(candidates) - len(failures),
        "reconstruction_failure_count": len(failures), "reconstruction_rate": rate,
        "failure_source_item_ids": failures,
        "status": "PASS" if rate == 1.0 else "FAIL",
        "media_validation_report": media_validation_report,
        "benchmark_acceptance_status": (
            "MEDIA_VALID_CANONICAL_READY" if media_valid and rate == 1.0
            else "BLOCKED_MISSING_MEDIA" if not media_valid
            else "BLOCKED_SOURCE_RECONSTRUCTION"
        ),
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
