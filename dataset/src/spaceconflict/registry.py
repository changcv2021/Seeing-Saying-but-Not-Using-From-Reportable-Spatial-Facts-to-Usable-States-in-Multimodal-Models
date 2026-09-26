from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_REQUIRED_KEYS = {
    "contract_version",
    "world_unit",
    "native_gt_sources",
    "node_types",
    "native_fact_rules",
    "qa_to_fact_rules",
    "identity_policy",
    "reference_frame_policy",
    "time_scope_policy",
    "state_branch_policy",
    "observability_policy",
    "allowed_predicates",
    "authorized_rules",
    "allowed_levels",
    "allowed_tracks",
    "valid_level_track_cells",
    "allowed_operators",
    "forbidden_tasks",
    "reject_conditions",
    "redistribution_policy",
}


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: YAML root must be an object")
    return value


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return value


def load_registry(root: Path = ROOT) -> dict[str, Any]:
    return load_yaml(root / "datasets.yaml")


def select_datasets(registry: dict[str, Any], selector: str) -> list[str]:
    datasets = registry.get("datasets", {})
    if selector == "all":
        return sorted(datasets)
    requested = [part.strip() for part in selector.split(",") if part.strip()]
    unknown = sorted(set(requested) - set(datasets))
    if unknown:
        raise ValueError(f"Unknown dataset(s): {', '.join(unknown)}")
    return requested


def contract_path(dataset: str, root: Path = ROOT) -> Path:
    configured = load_registry(root).get("datasets", {}).get(dataset, {}).get("contract_file")
    if configured:
        return root / str(configured)
    suffix = ".stub.yaml" if dataset in {"scope", "embodiedbench"} else ".yaml"
    return root / "contracts" / f"{dataset}{suffix}"


def validate_contract(dataset: str, root: Path = ROOT) -> list[str]:
    path = contract_path(dataset, root)
    if not path.exists():
        return [f"MISSING_CONTRACT:{path}"]
    contract = load_yaml(path)
    missing = sorted(CONTRACT_REQUIRED_KEYS - set(contract))
    errors = [f"MISSING_CONTRACT_KEY:{key}" for key in missing]
    if contract.get("dataset_name") != dataset:
        errors.append("CONTRACT_DATASET_NAME_MISMATCH")
    return errors


def source_report_path(dataset: str, root: Path = ROOT) -> Path:
    return root / "reports" / dataset / "source_discovery.json"


def iter_source_reports(datasets: Iterable[str], root: Path = ROOT):
    for dataset in datasets:
        path = source_report_path(dataset, root)
        if not path.exists():
            yield dataset, {"status": "BLOCKED_SOURCE", "error": "MISSING_SOURCE_REPORT"}
            continue
        yield dataset, load_json(path)
