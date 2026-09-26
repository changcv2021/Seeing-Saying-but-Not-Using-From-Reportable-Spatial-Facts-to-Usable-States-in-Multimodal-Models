from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from spaceconflict.cli import COMMANDS, IMPLEMENTED, build_parser, validate_registry
from spaceconflict.registry import CONTRACT_REQUIRED_KEYS, ROOT, contract_path, load_registry


def test_all_json_schemas_are_valid() -> None:
    for path in sorted((ROOT / "schemas").glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_registry_validates() -> None:
    assert validate_registry(load_registry()) == []


@pytest.mark.parametrize("dataset", sorted(load_registry()["datasets"]))
def test_every_dataset_has_complete_contract(dataset: str) -> None:
    path = contract_path(dataset)
    assert path.exists()
    contract = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert contract["dataset_name"] == dataset
    assert CONTRACT_REQUIRED_KEYS <= set(contract)


@pytest.mark.parametrize("dataset", sorted(load_registry()["datasets"]))
def test_every_dataset_has_source_report(dataset: str) -> None:
    path = ROOT / "reports" / dataset / "source_discovery.json"
    assert path.exists()
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["dataset"]
    assert report["status"]


def test_disabled_sources_have_no_levels_or_operators() -> None:
    registry = load_registry()["datasets"]
    for dataset in ("scope", "embodiedbench"):
        assert registry[dataset]["enabled"] is False
        contract = yaml.safe_load(contract_path(dataset).read_text(encoding="utf-8"))
        assert contract["allowed_levels"] == []
        assert contract["allowed_operators"] == []


def test_production_quota_arithmetic() -> None:
    config = yaml.safe_load((ROOT / "configs" / "production_10k.yaml").read_text(encoding="utf-8"))
    assert sum(config["level_targets"].values()) == config["target_pairs"] == 10_000
    by_level = {level: 0 for level in config["level_targets"]}
    for targets in config["dataset_level_targets"].values():
        for level, count in targets.items():
            by_level[level] += count
    assert by_level == config["level_targets"]
    assert sum(sum(row.values()) for row in config["dataset_level_targets"].values()) == 10_000


def test_all_commands_accept_shared_flags() -> None:
    parser = build_parser()
    for command in COMMANDS:
        argv = [command, "--dry-run", "--resume", "--seed", "1", "--workers", "1", "--limit", "1", "--world-id", "w", "--run-id", "r"]
        if command == "download":
            argv += ["--tier", "metadata"]
        if command in {"generate-claim-graphs", "generate-unknown", "sample-quota"}:
            argv += ["--config", "configs/golden_set.yaml"]
        if command == "evaluate":
            argv += ["--predictions", "predictions.jsonl"]
        args = parser.parse_args(argv)
        assert args.command == command
        assert args.dry_run and args.resume


def test_every_advertised_command_is_implemented() -> None:
    assert IMPLEMENTED == set(COMMANDS)


def test_raw_boundary_is_versioned() -> None:
    raw = ROOT / "data" / "raw"
    assert (raw / "README.md").exists()
    for dataset_dir in (path for path in raw.iterdir() if path.is_dir()):
        for revision_dir in dataset_dir.iterdir():
            assert revision_dir.is_dir()
            assert len(revision_dir.name) == 40


def test_license_and_access_states_are_explicit() -> None:
    datasets = load_registry()["datasets"]
    assert datasets["ca_vqa"]["status"] == "BLOCKED_LICENSE"
    assert datasets["hypo3d"]["status"] == "GRAPH_VALID"
    assert datasets["hypo3d"]["graph_validation_status"] == "GRAPH_MANIFEST_VALID"
    assert datasets["hypo3d"]["redistribution_mode"] == "blocked_until_access_and_media_terms_verified"
    assert datasets["omnispatial"]["status"] == "BLOCKED_LICENSE"


def test_validate_media_dry_run() -> None:
    from spaceconflict.media_validation import validate_media

    result = validate_media(
        "sti_bench",
        dry_run=True,
        resume=True,
        run_id="test_media",
        limit=3,
    )
    assert result["status"] == "PLANNED"
    assert result["world_limit"] == 3


def test_validate_hypo3d_media_dry_run() -> None:
    from spaceconflict.media_validation import validate_media

    result = validate_media(
        "hypo3d",
        dry_run=True,
        resume=True,
        run_id="test_hypo3d_media",
        limit=3,
    )
    assert result["status"] == "PLANNED"
    assert result["world_limit"] == 3
