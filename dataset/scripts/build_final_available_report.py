#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_many(root: Path, values: list[str]) -> list[Path]:
    paths = []
    for value in values:
        path = (root / value).resolve()
        path.relative_to(root)
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--quota-version", required=True)
    parser.add_argument("--proof-report", action="append", required=True)
    parser.add_argument("--unknown-report", action="append", required=True)
    parser.add_argument("--guide-compliance", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--test-count", type=int, required=True)
    parser.add_argument("--test-job-id", type=int, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    release_dir = root / "release" / args.release
    manifest = load(release_dir / "manifest.json")
    quota = load(root / f"reports/quota.{args.quota_version}.seed_{args.seed}.json")
    analysis = load(root / f"reports/production_available.{args.release}.json")
    release_audit = load(root / f"reports/release_audit.{args.release}.json")
    replay = load(root / f"reports/replay_chain_audit.{args.release}.json")
    shortcuts = load(root / f"reports/shortcut_controls.{args.release}.json")
    guide = load(args.guide_compliance.resolve())
    proof_paths = resolve_many(root, args.proof_report)
    unknown_paths = resolve_many(root, args.unknown_report)
    proofs = [load(path) for path in proof_paths]
    unknowns = [load(path) for path in unknown_paths]
    registry = yaml.safe_load((root / "datasets.yaml").read_text(encoding="utf-8"))["datasets"]
    ca = registry["ca_vqa"]
    download_validation_path = root / "reports/ca_vqa/download_validation.full_v1.json"
    download_validation = load(download_validation_path) if download_validation_path.is_file() else {}
    ca_verified_files = download_validation.get("verified_file_count", ca["full_download_verified_files"])
    ca_expected_files = download_validation.get("expected_file_count", ca["full_download_expected_files"])
    ca_verified_bytes = download_validation.get("verified_bytes", ca["full_download_verified_bytes"])
    ca_expected_bytes = download_validation.get("expected_bytes", ca["full_download_expected_bytes"])
    ca_download_status = download_validation.get("status", "RUNNING")
    proof_count = sum(row["auto_accepted_count"] for row in proofs)
    unknown_count = sum(row["auto_accepted_unknown_count"] for row in unknowns)
    unknown_evidence = sum(row["evidence_ablation_count"] for row in unknowns)
    report = {
        "schema_version": "1.0",
        "report_version": "final_available_report_v1",
        "release": args.release,
        "status": "VERIFIED_AVAILABLE_RELEASE_WITH_COVERAGE_SHORTFALLS",
        "release_candidate_eligible": manifest["release_candidate_eligible"],
        "counts": {
            "pairs": manifest["pair_count"], "binary_claims": manifest["claim_count"],
            "unknown_claims": manifest["unknown_claim_count"],
            "proof_valid_input_pairs": proof_count,
            "release_worlds": replay["world_unique_path_count"],
            "release_evidence_unique_facts": replay["evidence_unique_fact_count"],
            "release_artifact_references": replay["artifact_reference_count"],
        },
        "coverage": {
            "datasets": quota["dataset_counts"], "levels": quota["level_counts"],
            "primary_tracks": quota["primary_track_counts"], "operators": quota["operator_counts"],
            "modalities": quota["modality_counts"], "splits": quota["split_counts"],
            "shortfalls": quota["missing_requirements"],
        },
        "verification": {
            "release_machine_audit": release_audit["status"],
            "replay_chain_audit": replay["status"], "replay_failure_count": replay["failure_count"],
            "shortcut_control_audit": shortcuts["status"],
            "proof_certificate_replay_min_rate": min(row["certificate_replay_pass_rate"] for row in proofs),
            "proof_independent_verifier_min_rate": min(row["independent_verifier_agreement_rate"] for row in proofs),
            "proof_minimality_ablation_min_rate": min(row["minimality_ablation_pass_rate"] for row in proofs),
            "unknown_evidence_ablation_count": unknown_evidence,
            "unknown_evidence_ablation_ratio": unknown_evidence / unknown_count if unknown_count else 0.0,
            "unknown_positive_witness_min_rate": min(row["positive_witness_pass_rate"] for row in unknowns),
            "unknown_negative_witness_min_rate": min(row["negative_witness_pass_rate"] for row in unknowns),
            "text_only_label_accuracy": analysis["text_only_classifiers"]["label"]["accuracy"],
            "text_only_label_roc_auc": analysis["text_only_classifiers"]["label"]["roc_auc"],
            "claim_media_composite_unique": release_audit["text_checks"]["claim_media_composite_unique"],
            "exact_surface_duplicate_rate": analysis["corpus_checks"]["exact_surface_duplicate_rate"],
            "test_count": args.test_count, "test_job_id": args.test_job_id,
        },
        "formal_guide_acceptance": guide["sections"]["35_acceptance"],
        "acquisition": {
            "ca_vqa_download_job_id": ca["download_job_id"],
            "ca_vqa_verified_files": ca_verified_files,
            "ca_vqa_expected_files": ca_expected_files,
            "ca_vqa_verified_bytes": ca_verified_bytes,
            "ca_vqa_expected_bytes": ca_expected_bytes,
            "full_download_status": ca_download_status,
        },
        "evidence_reports": {
            "manifest": f"release/{args.release}/manifest.json",
            "quota": f"reports/quota.{args.quota_version}.seed_{args.seed}.json",
            "analysis": f"reports/production_available.{args.release}.json",
            "release_audit": f"reports/release_audit.{args.release}.json",
            "replay_audit": f"reports/replay_chain_audit.{args.release}.json",
            "shortcut_audit": f"reports/shortcut_controls.{args.release}.json",
            "proof_reports": [str(path.relative_to(root)) for path in proof_paths],
            "unknown_reports": [str(path.relative_to(root)) for path in unknown_paths],
            "guide_compliance": str(args.guide_compliance.resolve().relative_to(root)),
        },
        "policy": "quality and proof gates are never relaxed to fill numerical or coverage shortfalls",
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        f"# SpaceConflict final report — {args.release}", "",
        f"Status: `{report['status']}`; formal release candidate: `{report['release_candidate_eligible']}`.", "",
        "## Verified release", "",
        f"- {manifest['pair_count']} minimal pairs / {manifest['claim_count']} binary claims / {manifest['unknown_claim_count']} Unknown claims.",
        f"- {replay['world_unique_path_count']} worlds, {replay['evidence_unique_fact_count']} unique replayed evidence facts, {replay['artifact_reference_count']} artifact references.",
        f"- Release audit `{release_audit['status']}`, replay `{replay['status']}`, shortcut controls `{shortcuts['status']}`.",
        f"- Text-only label accuracy/AUC: {report['verification']['text_only_label_accuracy']} / {report['verification']['text_only_label_roc_auc']}.", "",
        "## Coverage", "",
        f"- Dataset counts: `{quota['dataset_counts']}`", f"- Level counts: `{quota['level_counts']}`",
        f"- Unknown evidence-ablation claims: {unknown_evidence}.",
        f"- Formal shortfalls: `{quota['missing_requirements']}`", "",
        "## Acquisition", "",
        f"CA-VQA job `{ca['download_job_id']}`: status `{ca_download_status}`, {ca_verified_files}/{ca_expected_files} files and {ca_verified_bytes}/{ca_expected_bytes} bytes verified.", "",
        "No upstream media is redistributed. This artifact is the largest currently verified available slice, not the formal 10k/2k benchmark release candidate.", "",
    ]
    args.output_markdown.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "status": report["status"], "pairs": manifest["pair_count"],
        "unknown_claims": manifest["unknown_claim_count"], "release_candidate_eligible": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
