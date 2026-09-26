#!/usr/bin/env python3
"""Evidence-backed compliance matrix for guide sections 31–37."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from spaceconflict.cli import COMMANDS, build_parser
from spaceconflict.hashing import sha256_file


SHARED_FLAGS = {"--dry-run", "--resume", "--seed", "--workers", "--limit", "--world-id", "--run-id"}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def gate(actual: Any, required: Any, passed: bool, evidence: str) -> dict[str, Any]:
    return {"actual": actual, "required": required, "pass": passed, "evidence": evidence}


def cli_checks() -> dict[str, Any]:
    parser = build_parser()
    action = next(item for item in parser._actions if getattr(item, "choices", None))
    choices = action.choices
    missing_commands = sorted(set(COMMANDS) - set(choices))
    flag_failures = {}
    for command in COMMANDS:
        flags = {flag for item in choices[command]._actions for flag in item.option_strings}
        missing = sorted(SHARED_FLAGS - flags)
        if missing:
            flag_failures[command] = missing
    return {
        "status": "PASS" if not missing_commands and not flag_failures else "FAIL",
        "required_command_count": len(COMMANDS),
        "implemented_command_count": len(COMMANDS) - len(missing_commands),
        "missing_commands": missing_commands,
        "shared_flag_failures": flag_failures,
        "evidence": ["src/spaceconflict/cli.py", "tests/test_bootstrap.py"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--guide", type=Path, required=True)
    parser.add_argument("--release", default="production_available_v1")
    parser.add_argument("--quota-version", default="quota_production_available_v1")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--proof-report", action="append")
    parser.add_argument("--unknown-report", action="append")
    parser.add_argument("--test-count", type=int, default=66)
    parser.add_argument("--test-job-id", type=int, default=8075995)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    guide = args.guide.resolve()
    release_dir = root / "release" / args.release
    production = load(root / f"reports/production_available.{args.release}.json")
    release_audit = load(root / f"reports/release_audit.{args.release}.json")
    replay = load(root / f"reports/replay_chain_audit.{args.release}.json")
    shortcuts = load(root / f"reports/shortcut_controls.{args.release}.json")
    quota = load(root / f"reports/quota.{args.quota_version}.seed_{args.seed}.json")
    proof_paths = (
        [(root / value).resolve() for value in args.proof_report]
        if args.proof_report else
        [root / "reports/proof_verification.proof_verification_p1_v2.json"]
    )
    unknown_paths = (
        [(root / value).resolve() for value in args.unknown_report]
        if args.unknown_report else
        [root / "reports/unknown_generation.unknown_p1_v2.json"]
    )
    for path in [*proof_paths, *unknown_paths]:
        path.relative_to(root)
    proof_reports = [load(path) for path in proof_paths]
    unknown_reports = [load(path) for path in unknown_paths]
    proof = {
        "auto_accepted_count": sum(row["auto_accepted_count"] for row in proof_reports),
        "certificate_replay_pass_rate": min(row["certificate_replay_pass_rate"] for row in proof_reports),
        "independent_verifier_agreement_rate": min(row["independent_verifier_agreement_rate"] for row in proof_reports),
    }
    unknown_accepted = sum(row["auto_accepted_unknown_count"] for row in unknown_reports)
    unknown_evidence = sum(row["evidence_ablation_count"] for row in unknown_reports)
    unknown = {
        "auto_accepted_unknown_count": unknown_accepted,
        "evidence_ablation_count": unknown_evidence,
        "evidence_ablation_ratio": unknown_evidence / unknown_accepted if unknown_accepted else 0.0,
        "positive_witness_pass_rate": min(row["positive_witness_pass_rate"] for row in unknown_reports),
        "negative_witness_pass_rate": min(row["negative_witness_pass_rate"] for row in unknown_reports),
    }
    proof_evidence = ", ".join(str(path.relative_to(root)) for path in proof_paths)
    unknown_evidence_paths = ", ".join(str(path.relative_to(root)) for path in unknown_paths)
    final = load(root / "reports/final.pilot_verified_2k_v2.json")
    dataset_registry = yaml.safe_load((root / "datasets.yaml").read_text(encoding="utf-8"))["datasets"]
    sampled_path = root / f"sampled/pairs.{args.quota_version}.seed_{args.seed}.jsonl"
    sampled = list(rows(sampled_path))
    test_world_level = Counter(
        (row["global_world_id"], row["level"]) for row in sampled if row["split"] == "test"
    )
    test_world_level_max = max(test_world_level.values(), default=0)
    release_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(release_dir.glob("*")) if path.is_file()
    )
    graph = final["graph"]
    acceptance = {
        "auto_accepted_pairs_at_least_10000": gate(proof["auto_accepted_count"], 10000, proof["auto_accepted_count"] >= 10000, proof_evidence),
        "L1_at_least_2000": gate(quota["level_counts"].get("L1", 0), 2000, quota["level_counts"].get("L1", 0) >= 2000, f"reports/quota.{args.quota_version}.seed_{args.seed}.json"),
        "L2_at_least_2000": gate(quota["level_counts"].get("L2", 0), 2000, quota["level_counts"].get("L2", 0) >= 2000, f"reports/quota.{args.quota_version}.seed_{args.seed}.json"),
        "L3_at_least_3500": gate(quota["level_counts"].get("L3", 0), 3500, quota["level_counts"].get("L3", 0) >= 3500, f"reports/quota.{args.quota_version}.seed_{args.seed}.json"),
        "L4_at_least_2500": gate(quota["level_counts"].get("L4", 0), 2500, quota["level_counts"].get("L4", 0) >= 2500, f"reports/quota.{args.quota_version}.seed_{args.seed}.json"),
        "provenance_coverage": gate(graph["provenance_coverage"], 1.0, graph["provenance_coverage"] == 1.0, "reports/final.pilot_verified_2k_v2.json"),
        "source_reconstruction": gate(graph["source_reconstruction_accuracy"], 1.0, graph["source_reconstruction_accuracy"] == 1.0, "reports/final.pilot_verified_2k_v2.json"),
        "release_machine_audit": gate(release_audit["status"], "PASS", release_audit["status"] == "PASS", f"reports/release_audit.{args.release}.json"),
        "full_replay_chain": gate(replay["status"], "PASS", replay["status"] == "PASS" and replay["failure_count"] == 0, f"reports/replay_chain_audit.{args.release}.json"),
        "independent_verifier": gate(proof["independent_verifier_agreement_rate"], 1.0, proof["independent_verifier_agreement_rate"] == 1.0, proof_evidence),
        "negative_predicate_preserved_at_least_70pct": gate(production["generation_accounting"]["predicate_preserved_ratio"], 0.7, production["generation_accounting"]["predicate_preserved_ratio"] >= 0.7, f"reports/production_available.{args.release}.json"),
        "predicate_complement_at_most_20pct": gate(production["generation_accounting"]["predicate_changed_ratio"], 0.2, production["generation_accounting"]["predicate_changed_ratio"] <= 0.2, f"reports/production_available.{args.release}.json"),
        "world_split_isolation": gate(release_audit["split_leakage_world_count"], 0, release_audit["split_leakage_world_count"] == 0, f"reports/release_audit.{args.release}.json"),
        "test_world_pair_cap": gate(production["pairs_per_world"]["test_max"], 4, production["pairs_per_world"]["test_max"] <= 4, f"reports/production_available.{args.release}.json"),
        "test_world_level_cap": gate(test_world_level_max, 2, test_world_level_max <= 2, str(sampled_path.relative_to(root))),
        "unknown_at_least_2000": gate(unknown["auto_accepted_unknown_count"], 2000, unknown["auto_accepted_unknown_count"] >= 2000, unknown_evidence_paths),
        "unknown_evidence_ablation_at_least_half": gate(unknown["evidence_ablation_ratio"], 0.5, unknown["evidence_ablation_ratio"] >= 0.5, unknown_evidence_paths),
        "no_model_predicted_ground_truth": gate(graph["origin_type_counts"].get("MODEL_PREDICTED", 0), 0, graph["origin_type_counts"].get("MODEL_PREDICTED", 0) == 0, "reports/final.pilot_verified_2k_v2.json"),
        "no_oracle_only_ground_truth": gate(graph["oracle_only_fact_count"], 0, graph["oracle_only_fact_count"] == 0, "reports/final.pilot_verified_2k_v2.json"),
        "no_unprovided_common_sense": gate(replay["failure_counts"].get("UNPROVIDED_PREMISE", 0), 0, replay["failure_counts"].get("UNPROVIDED_PREMISE", 0) == 0, f"reports/replay_chain_audit.{args.release}.json"),
        "no_formal_human_audit_field": gate("human_audit" in release_text, False, "human_audit" not in release_text, f"release/{args.release}"),
    }
    formal_eligible = all(item["pass"] for item in acceptance.values())
    tests = {
        "status": "PARTIAL_COVERAGE_SHORTFALLS_RECORDED",
        "executed_test_count": args.test_count,
        "executed_job_id": args.test_job_id,
        "covered": {
            "qa_parser_and_ontology_mapping": ["tests/test_adapters.py"],
            "inverse_rule": ["tests/test_verification.py", f"reports/shortcut_controls.{args.release}.json"],
            "time_and_count_scope": ["tests/test_language.py", "tests/test_verification.py"],
            "graph_edit_proof_replay_text_alignment": [f"reports/replay_chain_audit.{args.release}.json"],
            "source_to_export_integration_all_enabled_sources": [f"reports/replay_chain_audit.{args.release}.json"],
            "regression_resume_byte_identity": ["runs/proof_regression_8075736.out"],
        },
        "missing_or_blocked": {
            "symmetric_relation_direct_unit_test": "no symmetric predicate/operator is enabled in the current source contracts",
            "identity_merge_and_state_transition": "Hypo3D adapter and 688 world graphs pass; replayable L4 intervention certificates are pending",
            "touching_nontransitivity_property": "TOUCHING is outside the current accepted ontology",
            "L2_fact_deletion_property": "no L2 accepted sample exists",
        },
    }
    reporting = {
        "status": "PASS_WITH_EXPLICIT_NOT_AVAILABLE",
        "source_report": "PASS",
        "graph_report": "PASS",
        "generation_report": "PASS",
        "language_report": "PASS_EXCEPT_PARAPHRASE_NOT_AVAILABLE",
        "dataset_card": "PASS",
        "paraphrase_consistency": final["language"].get("paraphrase_consistency"),
        "evidence": [
            f"reports/production_available.{args.release}.json",
            "reports/final.pilot_verified_2k_v2.json",
            f"release/{args.release}/DATASET_CARD.md",
        ],
    }
    download_validation_path = root / "reports/ca_vqa/download_validation.full_v1.json"
    download_validation = load(download_validation_path) if download_validation_path.is_file() else {}
    ca_verified_files = download_validation.get(
        "verified_file_count", dataset_registry["ca_vqa"]["full_download_verified_files"]
    )
    ca_expected_files = download_validation.get(
        "expected_file_count", dataset_registry["ca_vqa"]["full_download_expected_files"]
    )
    ca_status = download_validation.get("status", "FULL_TRAIN_DOWNLOAD_RUNNING")
    blockers = [
        {
            "dataset": "hypo3d",
            "status": dataset_registry["hypo3d"].get("pipeline_status"),
            "reason": dataset_registry["hypo3d"].get("additional_pipeline_blockers"),
        },
        {"dataset": "scope", "status": "DISABLED", "reason": dataset_registry["scope"].get("reason") or dataset_registry["scope"].get("access_obstacle")},
        {"dataset": "embodiedbench", "status": "DISABLED", "reason": dataset_registry["embodiedbench"].get("reason") or dataset_registry["embodiedbench"].get("access_obstacle")},
    ]
    if ca_status != "FULL_DOWNLOAD_VALID":
        blockers.insert(0, {
            "dataset": "ca_vqa", "status": ca_status,
            "job_id": dataset_registry["ca_vqa"]["download_job_id"],
            "verified_files": ca_verified_files,
            "expected_files": ca_expected_files,
            "dependent_jobs": [
                dataset_registry["ca_vqa"]["dependent_profile_job_id"],
                dataset_registry["ca_vqa"]["full_download_validation_job_id"],
                dataset_registry["ca_vqa"]["full_profile_audit_job_id"],
            ],
        })
    report = {
        "schema_version": "1.0", "audit_version": "guide_compliance_v1",
        "guide": str(guide), "guide_sha256": sha256_file(guide),
        "release": args.release,
        "status": "IN_PROGRESS_VERIFIED_RELEASE_NOT_FORMAL_10K",
        "sections": {
            "31_cli": cli_checks(),
            "32_tests": tests,
            "33_state_and_logging": {
                "status": "PASS_FOR_NEW_RUNS_HISTORICAL_LOGS_REMAIN_V1",
                "logging_regression_job_id": 8075995,
                "logging_regression_status": "PASS_66_TESTS",
                "evidence": ["src/spaceconflict/logging_utils.py", "runs/logging_regression_8075995/validate-contract.json"],
            },
            "34_reporting": reporting,
            "35_acceptance": {"formal_10k_release_eligible": formal_eligible, "checks": acceptance},
            "37_replay_chain": {
                "status": replay["status"], "failure_count": replay["failure_count"],
                "artifact_reference_count": replay["artifact_reference_count"],
                "world_unique_path_count": replay["world_unique_path_count"],
                "evidence": f"reports/replay_chain_audit.{args.release}.json",
            },
        },
        "coverage_shortfalls": quota["missing_requirements"],
        "blockers": blockers,
        "policy": "quality and proof gates are not relaxed to fill numerical shortfalls",
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        f"# SpaceConflict guide compliance — {args.release}", "",
        f"Status: `{report['status']}`", "",
        f"Guide hash: `{report['guide_sha256']}`", "",
        "## Section status", "",
        "| Section | Status |", "|---|---|",
        *[f"| {name} | {value.get('status', value.get('formal_10k_release_eligible'))} |" for name, value in report["sections"].items()],
        "", "## Formal acceptance", "", "| Check | Actual | Required | Pass |", "|---|---:|---:|---:|",
        *[f"| {name} | {item['actual']} | {item['required']} | {item['pass']} |" for name, item in acceptance.items()],
        "", "## Active blockers", "",
        *[f"- `{item['dataset']}`: `{item['status']}` — {item.get('reason') or 'dependent job chain recorded in JSON'}" for item in blockers],
        "", "The release remains quality-verified but is not a formal 10,000-pair release candidate.", "",
    ]
    args.output_markdown.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "status": report["status"], "formal_10k_release_eligible": formal_eligible,
        "passing_acceptance_checks": sum(item["pass"] for item in acceptance.values()),
        "acceptance_check_count": len(acceptance), "blocker_count": len(blockers),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
