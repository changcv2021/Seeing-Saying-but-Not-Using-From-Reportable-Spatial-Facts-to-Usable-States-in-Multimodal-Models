from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .adapters.pipeline import build_adapter_outputs, reconstruct_source_qa
from .canonical import promote_candidates
from .download.metadata import acquire_metadata
from .evaluation import evaluate_predictions
from .graphs.pipeline import build_graphs, validate_graphs
from .hypo3d_l4.pipeline import run_action as run_hypo3d_l4_action
from .generation.claims import generate_claim_graphs
from .generation.language import realize_texts, verify_texts
from .generation.verification import verify_proofs
from .logging_utils import run_envelope, write_run_log
from .media_validation import DEFAULT_STORAGE_ROOT, validate_media
from .profiling.profile import profile_dataset
from .release import EXPORT_VERSION, export_benchmark, sample_quota
from .reporting import build_final_report
from .unknown.pipeline import generate_unknown
from .registry import ROOT, iter_source_reports, load_json, load_registry, select_datasets, validate_contract
from .world_index.pipeline import build_world_index, split_worlds


COMMANDS = [
    "discover", "download", "profile", "validate-contract", "build-canonical",
    "reconstruct-source-qa", "validate-media", "build-world-index", "split-worlds", "build-graphs",
    "validate-graphs", "generate-claim-graphs", "realize-text", "verify-text",
    "verify-proofs", "generate-unknown", "sample-quota", "export-benchmark",
    "evaluate", "report", "hypo3d-l4",
]
IMPLEMENTED = set(COMMANDS)


def add_shared_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--world-id")
    parser.add_argument("--run-id", default="manual")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spaceconflict")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        sub = subparsers.add_parser(name)
        add_shared_flags(sub)
        if name == "hypo3d-l4":
            sub.add_argument("action", nargs="?", default="audit-source", choices=[
                "audit-source", "audit-grounding", "build-branch-index", "build-object-catalog", "parse-changes", "normalize-post-qa",
                "resolve-targets", "build-prestates", "audit-provisional-coverage", "build-transitions",
                "run-dependency-ablation", "generate-claim-graphs", "realize-text",
                "verify", "sample", "report",
            ])
            sub.add_argument("--raw-root", type=Path, default=ROOT / "data/raw/hypo3d")
            sub.add_argument("--media-root", type=Path)
            sub.add_argument("--branch-index", type=Path)
            sub.add_argument("--parsed-changes", type=Path)
            sub.add_argument("--object-catalog", type=Path)
            sub.add_argument("--post-oracles", type=Path)
            sub.add_argument("--target-resolutions", type=Path)
            sub.add_argument("--grounding-metadata", type=Path)
            sub.add_argument("--embodiedscan-info", dest="embodiedscan_infos", type=Path, action="append", default=[])
            sub.add_argument(
                "--catalog-source-type",
                choices=["EMBODIEDSCAN_OFFICIAL_ANNOTATION", "UNVERIFIED_THIRD_PARTY_MIRROR"],
                default="EMBODIEDSCAN_OFFICIAL_ANNOTATION",
            )
            sub.add_argument("--prestates", type=Path)
            sub.add_argument("--pairs", type=Path)
            sub.add_argument("--calibration-limit", type=int, default=0)
            sub.add_argument("--output", type=Path)
            sub.add_argument("--scene-id")
            sub.add_argument("--change-id")
            sub.add_argument("--question-id")
        if name in {"discover", "download", "profile", "validate-contract", "build-canonical", "reconstruct-source-qa", "validate-media", "build-world-index", "build-graphs", "validate-graphs"}:
            sub.add_argument("--dataset", default="all")
        if name in {"build-world-index", "split-worlds", "build-graphs"}:
            sub.add_argument("--world-index-version")
        if name in {"split-worlds", "build-graphs"}:
            sub.add_argument("--split-version")
        if name in {"build-graphs", "validate-graphs"}:
            sub.add_argument("--world-graph-version")
        if name == "validate-media":
            sub.add_argument("--storage-root", type=Path, default=DEFAULT_STORAGE_ROOT)
        if name == "build-canonical":
            sub.add_argument("--media-run-id")
        if name == "download":
            sub.add_argument("--tier", required=True, choices=["metadata", "pilot", "production"])
        if name in {"generate-claim-graphs", "generate-unknown", "sample-quota"}:
            sub.add_argument("--config", type=Path, required=True)
        if name == "export-benchmark":
            sub.add_argument("--config", type=Path)
        if name == "realize-text":
            sub.add_argument("--candidates", type=int, default=3)
            sub.add_argument("--claim-build-version")
            sub.add_argument("--realization-version")
        if name == "verify-text":
            sub.add_argument("--realization-version")
            sub.add_argument("--text-verification-version")
        if name == "verify-proofs":
            sub.add_argument("--text-verification-version")
            sub.add_argument("--world-graph-manifest")
            sub.add_argument("--proof-verification-version")
        if name == "evaluate":
            sub.add_argument("--predictions", type=Path, required=True)
            sub.add_argument("--release-dir", type=Path, default=ROOT / "release" / EXPORT_VERSION)
            sub.add_argument("--output", type=Path)
        if name == "report":
            sub.add_argument("--release-dir", type=Path, default=ROOT / "release" / EXPORT_VERSION)
            sub.add_argument("--output-json", type=Path, default=ROOT / "reports" / f"final.{EXPORT_VERSION}.json")
            sub.add_argument("--output-markdown", type=Path, default=ROOT / "reports" / f"final.{EXPORT_VERSION}.md")
    return parser


def validate_registry(registry: dict[str, Any]) -> list[str]:
    schema = load_json(ROOT / "schemas" / "dataset_registry.schema.json")
    return [error.message for error in Draft202012Validator(schema).iter_errors(registry)]


def handle_discover(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    registry = load_registry()
    names = select_datasets(registry, args.dataset)
    rows = []
    for dataset, report in iter_source_reports(names):
        rows.append({
            "dataset": dataset,
            "status": report.get("status"),
            "source_revision": report.get("source_revision"),
            "data_revision": report.get("data_revision"),
            "license_id": report.get("license_id"),
            "recommended_tier": report.get("recommended_tier"),
            "access_obstacles": report.get("access_obstacles", []),
        })
    return 0, {"schema_version": "1.0", "dry_run": args.dry_run, "datasets": rows}


def handle_validate_contract(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    registry = load_registry()
    names = select_datasets(registry, args.dataset)
    results: dict[str, list[str]] = {"registry": validate_registry(registry)}
    for name in names:
        results[name] = validate_contract(name)
    failure_count = sum(bool(errors) for errors in results.values())
    return (1 if failure_count else 0), {
        "schema_version": "1.0", "status": "FAIL" if failure_count else "PASS", "results": results
    }


def handle_download(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    if args.tier != "metadata":
        return 2, {
            "status": "BLOCKED_SOURCE",
            "reason": "ONLY_METADATA_TIER_APPROVED_ON_LOGIN_NODE",
            "tier": args.tier,
        }
    registry = load_registry()
    names = select_datasets(registry, args.dataset)
    results = [acquire_metadata(name, dry_run=args.dry_run, resume=args.resume) for name in names]
    failures = sum(item["status"].startswith("BLOCKED") for item in results)
    return (2 if failures and failures == len(results) else 0), {"status": "PASS" if not failures else "PARTIAL", "results": results}


def handle_profile(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    registry = load_registry()
    names = select_datasets(registry, args.dataset)
    results = [profile_dataset(name, dry_run=args.dry_run) for name in names]
    failures = sum(item["status"].startswith("BLOCKED") for item in results)
    return (2 if failures and failures == len(results) else 0), {"status": "PASS" if not failures else "PARTIAL", "results": results}


def handle_build_canonical(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    registry = load_registry()
    names = select_datasets(registry, args.dataset)
    results = []
    for name in names:
        adapter = build_adapter_outputs(
            name, dry_run=args.dry_run, limit=args.limit, resume=args.resume,
        )
        promotion = promote_candidates(
            name, dry_run=args.dry_run, resume=args.resume, media_run_id=args.media_run_id,
        )
        results.append({"dataset": name, "adapter": adapter, "canonical": promotion})
    failures = sum(
        item["canonical"].get("status") not in {"CANONICAL_VALID", "PLANNED"}
        for item in results
    )
    return (2 if failures and failures == len(results) else 0), {
        "status": "PASS" if not failures else "PARTIAL", "results": results,
    }


def handle_reconstruct(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    registry = load_registry()
    names = select_datasets(registry, args.dataset)
    results = [reconstruct_source_qa(name, dry_run=args.dry_run) for name in names]
    failures = sum(item.get("status") != "PASS" and item.get("status") != "PLANNED" for item in results)
    return (2 if failures and failures == len(results) else 0), {"status": "PASS" if not failures else "PARTIAL", "results": results}


def handle_validate_media(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    registry = load_registry()
    names = select_datasets(registry, args.dataset)
    results = [validate_media(
        name,
        dry_run=args.dry_run,
        resume=args.resume,
        run_id=args.run_id,
        limit=args.limit,
        storage_root=args.storage_root,
    ) for name in names]
    failures = sum(item.get("status") not in {"PILOT_MEDIA_VALID", "PLANNED"} for item in results)
    return (1 if failures else 0), {"status": "PASS" if not failures else "PARTIAL", "results": results}


def handle_build_world_index(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    names = None if args.dataset == "all" else select_datasets(load_registry(), args.dataset)
    result = build_world_index(
        dry_run=args.dry_run, resume=args.resume, limit=args.limit,
        datasets=names,
        **({"world_index_version": args.world_index_version} if args.world_index_version else {}),
    )
    return (0 if result.get("status") in {"WORLD_INDEX_VALID", "PLANNED"} else 2), result


def handle_split_worlds(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = split_worlds(
        dry_run=args.dry_run, resume=args.resume, seed=args.seed, limit=args.limit,
        **({"world_index_version": args.world_index_version} if args.world_index_version else {}),
        **({"split_version": args.split_version} if args.split_version else {}),
    )
    return (0 if result.get("status") in {"WORLD_SPLIT_VALID", "PLANNED"} else 2), result


def handle_build_graphs(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    names = select_datasets(load_registry(), args.dataset)
    if args.dataset == "all":
        names = [
            name for name in names
            if any((ROOT / "data/canonical" / name).glob("*/*/records.jsonl"))
        ]
    result = build_graphs(
        names, dry_run=args.dry_run, resume=args.resume, limit=args.limit, seed=args.seed,
        **({"world_index_version": args.world_index_version} if args.world_index_version else {}),
        **({"split_version": args.split_version} if args.split_version else {}),
        **({"world_graph_version": args.world_graph_version} if args.world_graph_version else {}),
    )
    return (0 if result.get("status") in {"GRAPH_VALID", "PLANNED"} else 2), result


def handle_validate_graphs(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = validate_graphs(
        dry_run=args.dry_run, limit=args.limit,
        **({"world_graph_version": args.world_graph_version} if args.world_graph_version else {}),
    )
    return (0 if result.get("status") in {"GRAPH_MANIFEST_VALID", "PLANNED"} else 2), result


def handle_generate_claim_graphs(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = generate_claim_graphs(
        config=args.config, dry_run=args.dry_run, resume=args.resume, seed=args.seed, limit=args.limit,
    )
    return (0 if result.get("status") in {"STRUCTURAL_CLAIMS_VALID", "PLANNED"} else 2), result


def handle_realize_text(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = realize_texts(
        candidates=args.candidates, dry_run=args.dry_run, resume=args.resume,
        seed=args.seed, limit=args.limit,
        **({"claim_build_version": args.claim_build_version} if args.claim_build_version else {}),
        **({"realization_version": args.realization_version} if args.realization_version else {}),
    )
    return (0 if result.get("status") in {"TEXT_REALIZED", "PLANNED"} else 2), result


def handle_verify_text(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = verify_texts(
        dry_run=args.dry_run, resume=args.resume, limit=args.limit,
        **({"realization_version": args.realization_version} if args.realization_version else {}),
        **({"text_verification_version": args.text_verification_version} if args.text_verification_version else {}),
    )
    return (0 if result.get("status") in {"TEXT_VALID", "PLANNED"} else 2), result


def handle_verify_proofs(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = verify_proofs(
        dry_run=args.dry_run, resume=args.resume, limit=args.limit,
        **({"text_verification_version": args.text_verification_version} if args.text_verification_version else {}),
        **({"world_graph_manifest": args.world_graph_manifest} if args.world_graph_manifest else {}),
        **({"proof_verification_version": args.proof_verification_version} if args.proof_verification_version else {}),
    )
    return (0 if result.get("status") in {"VERIFIER_VALID", "PLANNED"} else 2), result


def handle_sample_quota(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = sample_quota(config=args.config, dry_run=args.dry_run, resume=args.resume, seed=args.seed, limit=args.limit)
    return (0 if result.get("status") in {"QUOTA_VALID", "QUOTA_SHORTFALL", "PLANNED"} else 2), result


def handle_generate_unknown(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = generate_unknown(
        config=args.config, dry_run=args.dry_run, resume=args.resume, seed=args.seed, limit=args.limit,
    )
    return (0 if result.get("status") in {"UNKNOWN_VALID", "UNKNOWN_SHORTFALL", "PLANNED"} else 2), result


def handle_export_benchmark(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = export_benchmark(
        dry_run=args.dry_run, resume=args.resume, seed=args.seed, limit=args.limit,
        config=args.config,
    )
    return (0 if result.get("status") in {"VERIFIED_SLICE_EXPORTED", "RELEASE_CANDIDATE_EXPORTED", "PLANNED"} else 2), result


def handle_evaluate(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    if args.dry_run:
        return 0, {
            "status": "PLANNED",
            "predictions": str(args.predictions),
            "release_dir": str(args.release_dir),
            "output": str(args.output) if args.output else None,
        }
    if args.output and args.output.exists() and not args.resume:
        raise FileExistsError(f"Output exists: {args.output}; use --resume")
    result = evaluate_predictions(
        args.predictions,
        args.release_dir,
        output_path=args.output,
    )
    return (0 if result.get("status") == "PASS" else 2), result


def handle_report(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    if args.dry_run:
        return 0, {
            "status": "PLANNED",
            "release_dir": str(args.release_dir),
            "output_json": str(args.output_json),
            "output_markdown": str(args.output_markdown),
        }
    existing = [path for path in (args.output_json, args.output_markdown) if path.exists()]
    if existing and not args.resume:
        raise FileExistsError(f"Output exists: {existing[0]}; use --resume")
    result = build_final_report(
        release_dir=args.release_dir,
        output_json=args.output_json,
        output_markdown=args.output_markdown,
    )
    return 0, result


def handle_hypo3d_l4(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    result = run_hypo3d_l4_action(
        args.action,
        raw_root=args.raw_root,
        output=args.output,
        media_root=args.media_root,
        branch_index=args.branch_index,
        parsed_changes=args.parsed_changes,
        object_catalog=args.object_catalog,
        post_oracles=args.post_oracles,
        target_resolutions=args.target_resolutions,
        grounding_metadata=args.grounding_metadata,
        catalog_source_type=args.catalog_source_type,
        embodiedscan_infos=args.embodiedscan_infos,
        prestates=args.prestates,
        pairs=args.pairs,
        calibration_limit=args.calibration_limit,
        dry_run=args.dry_run,
        resume=args.resume,
        limit=args.limit,
        scene_id=args.scene_id,
        change_id=args.change_id,
        question_id=args.question_id,
    )
    accepted = {
        "PLANNED", "SOURCE_AUDITED", "GROUNDING_AUDITED", "GROUNDING_COVERAGE_INCOMPLETE",
        "BRANCH_INDEX_VALID", "CHANGE_PARSE_VALID",
        "POST_ORACLE_VALID",
        "TARGET_RESOLUTION_VALID", "TARGET_RESOLUTION_PROVISIONAL",
        "FOUNDATION_VALID_PRESTATE_BLOCKED",
        "OBJECT_CATALOG_VALID", "OBJECT_CATALOG_PROVISIONAL",
        "PROVISIONAL_COVERAGE_AUDITED",
        "VERIFIED_CANDIDATE_SET_VALID_P0_MET",
        "VERIFIED_CANDIDATE_SET_VALID_P0_SHORTFALL", "VERIFIED_CANDIDATE_SET_EMPTY",
        "PRESTATE_VALID", "PRESTATE_SHORTFALL",
        "TRANSITION_INPUT_VALID", "CLAIM_GRAPH_VALID", "CLAIM_GRAPH_SHORTFALL",
    }
    return (0 if result.get("status") in accepted else 2), result


def handle_unimplemented(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    return 2, {
        "status": "BLOCKED_SOURCE",
        "command": args.command,
        "reason": "PHASE_NOT_IMPLEMENTED",
        "message": "This stage is intentionally gated until upstream acceptance conditions pass.",
    }


def _dispatch(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    if args.command == "discover":
        return handle_discover(args)
    elif args.command == "download":
        return handle_download(args)
    elif args.command == "profile":
        return handle_profile(args)
    elif args.command == "build-canonical":
        return handle_build_canonical(args)
    elif args.command == "reconstruct-source-qa":
        return handle_reconstruct(args)
    elif args.command == "validate-media":
        return handle_validate_media(args)
    elif args.command == "validate-contract":
        return handle_validate_contract(args)
    elif args.command == "build-world-index":
        return handle_build_world_index(args)
    elif args.command == "split-worlds":
        return handle_split_worlds(args)
    elif args.command == "build-graphs":
        return handle_build_graphs(args)
    elif args.command == "validate-graphs":
        return handle_validate_graphs(args)
    elif args.command == "generate-claim-graphs":
        return handle_generate_claim_graphs(args)
    elif args.command == "realize-text":
        return handle_realize_text(args)
    elif args.command == "verify-text":
        return handle_verify_text(args)
    elif args.command == "verify-proofs":
        return handle_verify_proofs(args)
    elif args.command == "generate-unknown":
        return handle_generate_unknown(args)
    elif args.command == "sample-quota":
        return handle_sample_quota(args)
    elif args.command == "export-benchmark":
        return handle_export_benchmark(args)
    elif args.command == "evaluate":
        return handle_evaluate(args)
    elif args.command == "report":
        return handle_report(args)
    elif args.command == "hypo3d-l4":
        return handle_hypo3d_l4(args)
    return handle_unimplemented(args)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be >= 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    if getattr(args, "calibration_limit", 0) < 0:
        parser.error("--calibration-limit must be >= 0")
    try:
        code, payload = _dispatch(args)
        exception = None
    except Exception as error:  # every operational failure must leave an auditable run record
        traceback.print_exc()
        code = 1
        exception = {"type": type(error).__name__, "message": str(error)}
        payload = {"status": "FAILED_EXCEPTION", "exception": exception}
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if not args.dry_run:
        counts = {"success": int(code == 0), "failure": int(code != 0)}
        log_path = write_run_log(run_envelope(
            args.command, args, counts, result=payload, exception=exception,
        ))
        print(json.dumps({"run_log": str(log_path)}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
