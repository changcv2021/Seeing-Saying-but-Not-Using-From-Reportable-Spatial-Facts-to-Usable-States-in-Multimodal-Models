from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .generation.claims import CLAIM_BUILD_VERSION
from .generation.language import REALIZATION_VERSION, TEXT_VERIFICATION_VERSION
from .generation.verification import PROOF_VERIFICATION_VERSION
from .graphs.pipeline import WORLD_GRAPH_VERSION
from .registry import ROOT, load_registry
from .release import EXPORT_VERSION, QUOTA_VERSION
from .unknown.pipeline import UNKNOWN_VERSION


REPORT_VERSION = "final_report_v2"


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def _pick(value: dict[str, Any] | None, *keys: str) -> dict[str, Any] | None:
    if value is None:
        return None
    return {key: value.get(key) for key in keys}


def _source_section(root: Path) -> dict[str, Any]:
    registry = load_registry(root)["datasets"]
    rows: dict[str, Any] = {}
    for dataset, config in sorted(registry.items()):
        discovery = _load(root / "reports" / dataset / "source_discovery.json") or {}
        profile = _load(root / "reports" / dataset / "profile.json") or {}
        reconstruction = _load(root / "reports" / dataset / "source_reconstruction.json") or {}
        media_reports = sorted((root / "reports" / dataset).glob("media_validation.*.json"))
        media = _load(media_reports[-1]) if media_reports else None
        rows[dataset] = {
            "enabled": config.get("enabled"),
            "registry_status": config.get("status"),
            "pipeline_status": config.get("pipeline_status"),
            "source_revision": discovery.get("source_revision"),
            "data_revision": discovery.get("data_revision"),
            "license_id": discovery.get("license_id"),
            "redistribution_allowed": discovery.get("redistribution_allowed"),
            "known_files": discovery.get("known_files", []),
            "known_total_bytes": discovery.get("known_total_bytes"),
            "access_obstacles": discovery.get("access_obstacles", []),
            "counts": {
                "records": profile.get("record_count"),
                "worlds": profile.get("world_count"),
                "media_images": profile.get("image_count"),
                "media_videos": profile.get("video_count"),
                "frames": profile.get("frame_count"),
                "qa": profile.get("qa_count"),
                "adapter_candidates": profile.get("adapter_candidate_count"),
            },
            "profile_scope": profile.get("profile_scope"),
            "included_task_distribution": profile.get("question_type_distribution") or profile.get("question_type_distribution_sample"),
            "excluded_task_families": profile.get("excluded_task_families", []),
            "source_reconstruction": _pick(
                reconstruction,
                "status", "benchmark_acceptance_status", "candidate_count",
                "reconstruction_pass_count", "reconstruction_failure_count",
            ),
            "media_validation": _pick(
                media,
                "status", "validator_version", "mapping_count", "media_count",
                "missing_count", "hash_failure_count", "validation_scope",
            ),
        }
    return rows


def _graph_detail(root: Path, summary: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    """Compile the guide-required graph accounting from validated graph artifacts."""
    manifest_path = root / "world_graphs" / f"manifest.{WORLD_GRAPH_VERSION}.jsonl"
    origin_types: Counter[str] = Counter()
    observability: Counter[str] = Counter()
    fact_count = provenance_complete = derived_count = oracle_count = 0
    if manifest_path.is_file():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("validation_status") != "GRAPH_VALID":
                continue
            graph = _load(root / row["graph_path"]) or {}
            for fact in graph.get("facts", []):
                fact_count += 1
                origin_types[str(fact.get("provenance", {}).get("origin_type", "MISSING"))] += 1
                observability[str(fact.get("observability", "MISSING"))] += 1
                derived_count += int(fact.get("derivation") is not None)
                oracle_count += int(fact.get("observability") == "oracle_only")
                provenance = fact.get("provenance", {})
                provenance_complete += int(all(provenance.get(key) for key in (
                    "source_dataset", "source_item_ids", "source_record_hash", "adapter_version",
                )))
    reconstruction_pass = sum(
        int((row.get("source_reconstruction") or {}).get("reconstruction_pass_count") or 0)
        for row in sources.values()
    )
    reconstruction_failure = sum(
        int((row.get("source_reconstruction") or {}).get("reconstruction_failure_count") or 0)
        for row in sources.values()
    )
    return {
        **summary,
        "valid_graph_fact_count": fact_count,
        "native_fact_count": sum(count for origin, count in origin_types.items() if origin.startswith("NATIVE")),
        "qa_derived_fact_count": sum(count for origin, count in origin_types.items() if origin.startswith("QA")),
        "rule_derived_fact_count": derived_count,
        "oracle_only_fact_count": oracle_count,
        "origin_type_counts": dict(sorted(origin_types.items())),
        "observability_distribution": dict(sorted(observability.items())),
        "provenance_complete_count": provenance_complete,
        "provenance_coverage": provenance_complete / fact_count if fact_count else None,
        "source_reconstruction_pass_count": reconstruction_pass,
        "source_reconstruction_failure_count": reconstruction_failure,
        "source_reconstruction_accuracy": (
            reconstruction_pass / (reconstruction_pass + reconstruction_failure)
            if reconstruction_pass + reconstruction_failure else None
        ),
        "identity_merge_count": summary.get("semantic_duplicate_fact_merge_count"),
        "graph_inconsistency_count": summary.get("graph_rejected_count"),
    }


def _acceptance(
    analysis: dict[str, Any], audit: dict[str, Any], replay_audit: dict[str, Any],
    shortcut_audit: dict[str, Any], proof: dict[str, Any], unknown: dict[str, Any],
) -> dict[str, Any]:
    coverage = analysis.get("coverage", {})
    levels = coverage.get("level_counts", {})
    checks = {
        "auto_accepted_pairs_at_least_10000": {
            "actual": analysis.get("text_verified_count"), "required": 10_000,
            "pass": (analysis.get("text_verified_count") or 0) >= 10_000,
        },
        "L1_at_least_2000": {"actual": levels.get("L1", 0), "required": 2_000, "pass": levels.get("L1", 0) >= 2_000},
        "L2_at_least_2000": {"actual": levels.get("L2", 0), "required": 2_000, "pass": levels.get("L2", 0) >= 2_000},
        "L3_at_least_3500": {"actual": levels.get("L3", 0), "required": 3_500, "pass": levels.get("L3", 0) >= 3_500},
        "L4_at_least_2500": {"actual": levels.get("L4", 0), "required": 2_500, "pass": levels.get("L4", 0) >= 2_500},
        "unknown_at_least_2000": {
            "actual": unknown.get("auto_accepted_unknown_count", 0), "required": 2_000,
            "pass": unknown.get("auto_accepted_unknown_count", 0) >= 2_000,
        },
        "unknown_ablation_at_least_half": {
            "actual": unknown.get("evidence_ablation_ratio"), "required": 0.5,
            "pass": (unknown.get("evidence_ablation_ratio") or 0) >= 0.5,
        },
        "proof_replay": {"actual": proof.get("certificate_replay_pass_rate"), "required": 1.0, "pass": proof.get("certificate_replay_pass_rate") == 1.0},
        "independent_verifier": {"actual": proof.get("independent_verifier_agreement_rate"), "required": 1.0, "pass": proof.get("independent_verifier_agreement_rate") == 1.0},
        "release_machine_audit": {"actual": audit.get("status"), "required": "PASS", "pass": audit.get("status") == "PASS"},
        "private_replay_chain_audit": {"actual": replay_audit.get("status"), "required": "PASS", "pass": replay_audit.get("status") == "PASS"},
        "static_shortcut_control_audit": {"actual": shortcut_audit.get("status"), "required": "PASS", "pass": shortcut_audit.get("status") == "PASS"},
        "world_split_isolation": {"actual": audit.get("split_leakage_world_count"), "required": 0, "pass": audit.get("split_leakage_world_count") == 0},
        "test_world_pair_cap": {
            "actual": analysis.get("pairs_per_world", {}).get("test_max"), "required_max": 4,
            "pass": (analysis.get("pairs_per_world", {}).get("test_max") or 10**9) <= 4,
        },
    }
    return {
        "formal_10k_release_eligible": all(row["pass"] for row in checks.values()),
        "checks": checks,
        "policy": "quality gates are never relaxed to fill quota shortfalls",
    }


def _render_markdown(report: dict[str, Any]) -> str:
    release = report["release"]
    acceptance = report["acceptance"]
    lines = [
        f"# SpaceConflict final report — {release['export_version']}",
        "",
        f"Status: `{report['status']}`. This is a verified pilot slice, not the formal 10,000-pair release.",
        "",
        "## Release",
        "",
        f"- Minimal pairs: {release['pair_count']}",
        f"- Binary claims: {release['claim_count']}",
        f"- Unknown claims: {release['unknown_claim_count']}",
        f"- Machine release audit: `{release['audit_status']}`",
        f"- Private replay-chain audit: `{release['replay_chain_audit_status']}`",
        f"- Static shortcut-control audit: `{release['shortcut_control_audit_status']}`",
        "",
        "## Sources",
        "",
        "| Dataset | Enabled | Source revision | License | Records | Worlds | QA | Pipeline status |",
        "|---|---:|---|---|---:|---:|---:|---|",
    ]
    for name, row in report["sources"].items():
        counts = row["counts"]
        lines.append(
            f"| {name} | {row['enabled']} | {row['source_revision'] or 'N/A'} | "
            f"{row['license_id'] or 'N/A'} | {counts['records'] if counts['records'] is not None else 'N/A'} | "
            f"{counts['worlds'] if counts['worlds'] is not None else 'N/A'} | "
            f"{counts['qa'] if counts['qa'] is not None else 'N/A'} | {row['pipeline_status'] or 'N/A'} |"
        )
    lines += [
        "",
        "## Graph, generation, and language",
        "",
        f"- Valid world graphs: {report['graph'].get('graph_valid_count')}; rejected graphs: {report['graph'].get('graph_rejected_count')}.",
        f"- Structurally accepted pairs: {report['generation'].get('structural_accepted_count')}; proof-verified pairs: {report['generation'].get('proof_verified_count')}.",
        f"- Predicate-preserved ratio: {report['generation'].get('predicate_preserved_ratio')}.",
        f"- Text-only label accuracy: {report['language'].get('text_only_label_accuracy')} (AUC {report['language'].get('text_only_label_auc')}).",
        f"- Exact sample duplicate rate before release sampling: {report['language'].get('exact_sample_duplicate_rate')}.",
        f"- Valid-graph facts: {report['graph'].get('valid_graph_fact_count')}; provenance coverage: {report['graph'].get('provenance_coverage')}.",
        f"- Source reconstruction accuracy: {report['graph'].get('source_reconstruction_accuracy')}; oracle-only facts: {report['graph'].get('oracle_only_fact_count')}.",
        "",
        "## Evaluation",
        "",
        f"Evaluator integration status: `{report['evaluation'].get('status', 'NOT_RUN')}`. "
        "Oracle smoke results only validate evaluator mechanics and are not a model baseline.",
        f"Shortcut-control audit: `{report['shortcut_controls'].get('status', 'NOT_RUN')}`. "
        "Static invariants and equivalent inversions were executed; media/frame perturbation manifests "
        "are ready but require predictions from each evaluated model.",
        "",
        "## Formal 10k acceptance",
        "",
        f"Eligible: `{acceptance['formal_10k_release_eligible']}`.",
        "",
        "| Check | Actual | Required | Pass |",
        "|---|---:|---:|---:|",
    ]
    for name, row in acceptance["checks"].items():
        required = row.get("required", row.get("required_max"))
        lines.append(f"| {name} | {row.get('actual')} | {required} | {row['pass']} |")
    lines += [
        "",
        "## Known limitations",
        "",
        "- Current sampled coverage has no L2 or L4; Hypo3D annotations and world graphs are valid, but replayable L4 intervention certificates are pending.",
        "- Unknown has a verified evidence-ablation construction but is below the 2,000 target.",
        "- No upstream media is redistributed; users must acquire it under upstream terms.",
        "- The world graph is partial: missing facts imply Unknown, never false.",
        "- Validation is automatic; no formal human audit was performed.",
        "- Do not use this pilot to claim general spatial reasoning or formal SpaceConflict completion.",
        "",
    ]
    return "\n".join(lines)


def build_final_report(
    *,
    release_dir: Path,
    output_json: Path | None = None,
    output_markdown: Path | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    manifest = _load(release_dir / "manifest.json")
    if manifest is None:
        raise FileNotFoundError(f"RELEASE_MANIFEST_MISSING:{release_dir / 'manifest.json'}")
    graph = _load(root / "reports" / f"graph_build.{WORLD_GRAPH_VERSION}.json") or {}
    claims = _load(root / "reports" / f"claim_generation.{CLAIM_BUILD_VERSION}.json") or {}
    language = _load(root / "reports" / f"language_realization.{REALIZATION_VERSION}.json") or {}
    text = _load(root / "reports" / f"text_verification.{TEXT_VERIFICATION_VERSION}.json") or {}
    proof = _load(root / "reports" / f"proof_verification.{PROOF_VERIFICATION_VERSION}.json") or {}
    unknown = _load(root / "reports" / f"unknown_generation.{UNKNOWN_VERSION}.json") or {}
    quota = _load(root / "reports" / f"quota.{QUOTA_VERSION}.seed_20260826.json") or {}
    analysis = _load(root / "reports" / f"pilot_2k.{EXPORT_VERSION}.json") or {}
    audit = _load(root / "reports" / f"release_audit.{EXPORT_VERSION}.json") or {}
    replay_audit = _load(root / "reports" / f"replay_chain_audit.{EXPORT_VERSION}.json") or {}
    shortcut_audit = _load(root / "reports" / f"shortcut_controls.{EXPORT_VERSION}.json") or {
        "status": "NOT_RUN",
        "reason": "shortcut-control audit report is not present",
    }
    evaluation = _load(root / "reports" / f"evaluation.{EXPORT_VERSION}.oracle_smoke.json") or {
        "status": "NOT_RUN",
        "reason": "evaluator integration report is not present",
    }
    sources = _source_section(root)
    graph_summary = _pick(
        graph, "status", "world_count", "graph_valid_count", "graph_rejected_count",
        "reject_code_counts", "semantic_duplicate_fact_merge_count", "split_leakage_check",
    ) or {}
    report = {
        "schema_version": "1.0",
        "report_version": REPORT_VERSION,
        "status": "PILOT_COMPLETE_WITH_COVERAGE_SHORTFALLS",
        "release": {
            "export_version": manifest.get("export_version"),
            "pair_count": manifest.get("pair_count"),
            "claim_count": manifest.get("claim_count"),
            "unknown_claim_count": manifest.get("unknown_claim_count"),
            "release_candidate_eligible": manifest.get("release_candidate_eligible"),
            "shortfalls": manifest.get("quota_shortfalls", []),
            "audit_status": audit.get("status"),
            "replay_chain_audit_status": replay_audit.get("status"),
            "replay_chain_audit_report": f"reports/replay_chain_audit.{EXPORT_VERSION}.json",
            "shortcut_control_audit_status": shortcut_audit.get("status"),
            "shortcut_control_audit_report": f"reports/shortcut_controls.{EXPORT_VERSION}.json",
            "dataset_card": str(release_dir / "DATASET_CARD.md"),
        },
        "sources": sources,
        "graph": _graph_detail(root, graph_summary, sources),
        "generation": {
            "structural_accepted_count": claims.get("structural_accepted_count"),
            "proof_verified_count": proof.get("auto_accepted_count"),
            "dataset_counts": quota.get("dataset_counts"),
            "level_counts": quota.get("level_counts"),
            "track_counts": quota.get("primary_track_counts"),
            "operator_counts": quota.get("operator_counts"),
            "modality_counts": quota.get("modality_counts"),
            "predicate_preserved_ratio": claims.get("predicate_preserved_ratio"),
            "verification_rejects": proof.get("reject_code_counts"),
            "pairs_per_world": analysis.get("pairs_per_world"),
        },
        "language": {
            "realization_family_counts": language.get("selected_style_family_counts"),
            "lexicalization_counts": language.get("selected_relation_lexicalization_counts"),
            "exact_sample_duplicate_rate": text.get("exact_sample_duplicate_rate"),
            "surface_text_reuse_rate": text.get("surface_text_reuse_rate"),
            "text_only_label_accuracy": analysis.get("text_only_classifiers", {}).get("label", {}).get("accuracy"),
            "text_only_label_auc": analysis.get("text_only_classifiers", {}).get("label", {}).get("roc_auc"),
            "text_only_label_assessment": analysis.get("text_only_classifiers", {}).get("label", {}).get("leakage_assessment"),
            "paraphrase_consistency": evaluation.get("metrics", {}).get("paraphrase_consistency"),
        },
        "unknown": _pick(
            unknown, "status", "target_claim_count", "auto_accepted_unknown_count",
            "evidence_ablation_count", "evidence_ablation_ratio", "positive_witness_pass_rate",
            "negative_witness_pass_rate",
        ),
        "evaluation": {
            "status": evaluation.get("status"),
            "evaluator_version": evaluation.get("evaluator_version"),
            "report": f"reports/evaluation.{EXPORT_VERSION}.oracle_smoke.json" if evaluation.get("status") == "PASS" else None,
            "oracle_smoke_only": True,
            "metrics": evaluation.get("metrics"),
        },
        "replay_chain": replay_audit,
        "shortcut_controls": shortcut_audit,
        "acceptance": _acceptance(analysis, audit, replay_audit, shortcut_audit, proof, unknown),
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_markdown is not None:
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        output_markdown.write_text(_render_markdown(report), encoding="utf-8")
    return report
