from __future__ import annotations

import json
import hashlib
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from .generation.verification import PROOF_VERIFICATION_VERSION
from .graphs.pipeline import WORLD_GRAPH_VERSION
from .hashing import sha256_bytes, sha256_file
from .registry import ROOT
from .unknown.pipeline import UNKNOWN_VERSION


QUOTA_VERSION = "quota_pilot_2k_v2"
EXPORT_VERSION = "pilot_verified_2k_v2"


def _versions(config: Path | None) -> tuple[str, str, dict[str, Any]]:
    policy = yaml.safe_load(config.read_text(encoding="utf-8")) if config is not None else {}
    policy = policy or {}
    quota_version = str(policy.get("quota_version", QUOTA_VERSION))
    export_version = str(policy.get("export_version", EXPORT_VERSION))
    for value in (quota_version, export_version):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
            raise ValueError(f"UNSAFE_RELEASE_VERSION:{value}")
    return quota_version, export_version, policy


def _configured_paths(
    *, root: Path, policy: dict[str, Any], key: str, default: Path,
) -> list[Path]:
    configured = policy.get(key)
    values = [str(default.relative_to(root))] if configured is None else configured
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list) or not values or not all(isinstance(value, str) for value in values):
        raise ValueError(f"INVALID_CONFIGURED_PATHS:{key}")
    paths = []
    for value in values:
        relative = Path(value)
        if relative.is_absolute():
            raise ValueError(f"ABSOLUTE_CONFIGURED_PATH:{key}:{value}")
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"CONFIGURED_PATH_ESCAPES_ROOT:{key}:{value}") from exc
        paths.append(path)
    return paths


def _unique_rows(paths: list[Path], id_key: str) -> list[dict[str, Any]]:
    rows = [row for path in paths for row in _load_jsonl(path)]
    ids = [row[id_key] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"DUPLICATE_CONFIGURED_INPUT_ID:{id_key}")
    return rows


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write(path: Path, payload: bytes, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume:
            raise FileExistsError(f"Output exists: {path}; use --resume")
        if path.read_bytes() != payload:
            raise ValueError(f"Non-deterministic output: {path}")
    else:
        path.write_bytes(payload)


def sample_quota(
    *, config: Path, dry_run: bool, resume: bool, seed: int, limit: int | None, root: Path = ROOT,
) -> dict[str, Any]:
    quota_version, export_version, policy = _versions(config)
    proof_version = str(policy.get("proof_verification_version", PROOF_VERIFICATION_VERSION))
    source_paths = _configured_paths(
        root=root, policy=policy, key="proof_candidate_paths",
        default=root / "candidates/auto_accepted" / f"pairs.{proof_version}.jsonl",
    )
    output_path = root / "sampled" / f"pairs.{quota_version}.seed_{seed}.jsonl"
    report_path = root / "reports" / f"quota.{quota_version}.seed_{seed}.json"
    if dry_run:
        return {
            "status": "PLANNED", "inputs": [str(path.relative_to(root)) for path in source_paths],
            "output": str(output_path.relative_to(root)), "config": str(config),
        }
    missing_sources = [str(path.relative_to(root)) for path in source_paths if not path.exists()]
    if missing_sources:
        return {"status": "BLOCKED_SOURCE", "reason": "AUTO_ACCEPTED_CANDIDATES_MISSING", "missing": missing_sources}
    rows = _unique_rows(source_paths, "pair_id")
    target_max = int(policy.get("target_pairs_max", policy.get("target_pairs", len(rows))))
    if limit is not None:
        target_max = min(target_max, limit)
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[(row["source_dataset"], row["level"])].append(row)
    for values in buckets.values():
        values.sort(key=lambda row: hashlib.sha256(f"{seed}\0{row['pair_id']}".encode()).hexdigest())
    ordered_rows = []
    bucket_keys = sorted(buckets)
    for index in range(max((len(values) for values in buckets.values()), default=0)):
        for key in bucket_keys:
            if index < len(buckets[key]):
                ordered_rows.append(buckets[key][index])
    selected = []
    world_counts: Counter[str] = Counter()
    test_world_level_counts: Counter[tuple[str, str]] = Counter()
    bucket_counts: Counter[tuple[str, str]] = Counter()
    cap_rejects: Counter[str] = Counter()
    raw_bucket_caps = policy.get("bucket_pair_caps", {})
    bucket_caps: dict[tuple[str, str], int] = {}
    for dataset, level_caps in raw_bucket_caps.items():
        if not isinstance(level_caps, dict):
            raise ValueError(f"INVALID_BUCKET_PAIR_CAPS:{dataset}")
        for level, cap in level_caps.items():
            if int(cap) < 1:
                raise ValueError(f"INVALID_BUCKET_PAIR_CAP:{dataset}:{level}:{cap}")
            bucket_caps[(str(dataset), str(level))] = int(cap)
    test_world_pair_cap = int(policy.get("test_world_pair_cap", 4))
    non_test_world_pair_cap = int(policy.get("non_test_world_pair_cap", test_world_pair_cap))
    if test_world_pair_cap < 1 or non_test_world_pair_cap < 1:
        raise ValueError("world pair caps must be >= 1")
    for row in ordered_rows:
        world = row["global_world_id"]
        bucket = (row["source_dataset"], row["level"])
        if bucket in bucket_caps and bucket_counts[bucket] >= bucket_caps[bucket]:
            cap_rejects["BUCKET_PAIR_CAP"] += 1
            continue
        world_pair_cap = test_world_pair_cap if row["split"] == "test" else non_test_world_pair_cap
        if world_counts[world] >= world_pair_cap:
            cap_rejects["WORLD_PAIR_CAP"] += 1
            continue
        if row["split"] == "test" and test_world_level_counts[(world, row["level"])] >= 2:
            cap_rejects["TEST_WORLD_LEVEL_CAP"] += 1
            continue
        selected.append(row)
        bucket_counts[bucket] += 1
        world_counts[world] += 1
        if row["split"] == "test":
            test_world_level_counts[(world, row["level"])] += 1
        if len(selected) >= target_max:
            break
    dataset_counts = Counter(row["source_dataset"] for row in selected)
    level_counts = Counter(row["level"] for row in selected)
    track_counts = Counter(row["primary_track"] for row in selected)
    operator_counts = Counter(row["operator_id"] for row in selected)
    split_counts = Counter(row["split"] for row in selected)
    modality_counts: Counter[str] = Counter()
    media_type_map = {"image": "single_image", "video": "continuous_video"}
    for row in selected:
        graph = json.loads((root / row["world_graph_path"]).read_text())
        evidence = json.loads((root / row["evidence_subgraph_path"]).read_text())
        evidence_media_ids = set(evidence["media_ids"])
        modality_counts.update(
            media_type_map.get(item["media_type"], item["media_type"])
            for item in graph["media"] if item["media_id"] in evidence_media_ids
        )
    missing_requirements = []
    target_min = int(policy.get("target_pairs_min", 0))
    if len(selected) < target_min:
        missing_requirements.append({"requirement": "target_pairs_min", "target": target_min, "actual": len(selected)})
    if policy.get("require_all_primary_tracks"):
        missing = sorted({"GEO-TOPO", "XFORM-PROJ", "IDENTITY", "DYNAMIC", "EMBODIED-OBS"} - set(track_counts))
        if missing:
            missing_requirements.append({"requirement": "all_primary_tracks", "missing": missing})
    if policy.get("require_all_modalities"):
        expected_modalities = {"single_image", "multi_view_images", "ordered_multi_frame", "continuous_video", "interactive_episode"}
        missing = sorted(expected_modalities - set(modality_counts))
        if missing:
            missing_requirements.append({"requirement": "all_modalities", "actual": sorted(modality_counts), "missing": missing})
    unknown_version = str(policy.get("unknown_version", UNKNOWN_VERSION))
    unknown_paths = _configured_paths(
        root=root, policy=policy, key="unknown_claim_paths",
        default=root / "candidates/unknown" / f"claims.{unknown_version}.jsonl",
    )
    existing_unknown_paths = [path for path in unknown_paths if path.exists()]
    unknown_count = len(_unique_rows(existing_unknown_paths, "unknown_id")) if existing_unknown_paths else 0
    unknown_target = int(policy.get("unknown_claims", 1 if policy.get("require_unknown_examples") else 0))
    if unknown_target and unknown_count < unknown_target:
        missing_requirements.append({
            "requirement": "unknown_examples", "target": unknown_target, "actual": unknown_count,
            "reason": "SAFE_EVIDENCE_ABLATION_SHORTFALL",
        })
    expected_datasets = {"spar", "ca_vqa", "vsi_bench", "sti_bench", "hypo3d", "omnispatial"}
    missing_datasets = sorted(expected_datasets - set(dataset_counts))
    if missing_datasets:
        missing_requirements.append({"requirement": "dataset_coverage", "missing": missing_datasets})
    missing_levels = sorted({"L1", "L2", "L3", "L4"} - set(level_counts))
    if missing_levels:
        missing_requirements.append({"requirement": "level_coverage", "missing": missing_levels})
    payload = b"".join(_json_bytes(row) + b"\n" for row in selected)
    _write(output_path, payload, resume)
    report = {
        "schema_version": "1.0", "quota_version": quota_version,
        "export_version": export_version,
        "status": "QUOTA_VALID" if not missing_requirements else "QUOTA_SHORTFALL",
        "release_candidate_eligible": not missing_requirements,
        "quality_policy": "SHORTFALLS_REPORTED_NEVER_FILLED_WITH_UNPROVED_SAMPLES",
        "input_auto_accepted_count": len(rows), "selected_pair_count": len(selected),
        "dataset_counts": dict(sorted(dataset_counts.items())), "level_counts": dict(sorted(level_counts.items())),
        "primary_track_counts": dict(sorted(track_counts.items())), "operator_counts": dict(sorted(operator_counts.items())),
        "modality_counts": dict(sorted(modality_counts.items())),
        "split_counts": dict(sorted(split_counts.items())), "cap_reject_counts": dict(sorted(cap_rejects.items())),
        "test_world_pair_cap": test_world_pair_cap,
        "non_test_world_pair_cap": non_test_world_pair_cap,
        "bucket_pair_caps": {
            dataset: {
                level: cap for (candidate_dataset, level), cap in sorted(bucket_caps.items())
                if candidate_dataset == dataset
            }
            for dataset in sorted({dataset for dataset, _ in bucket_caps})
        },
        "unknown_claim_count": unknown_count,
        "missing_requirements": missing_requirements,
        "input_hashes": {
            **{str(path.relative_to(root)): sha256_file(path) for path in source_paths},
            str(config): sha256_file(config),
            **{str(path.relative_to(root)): sha256_file(path) for path in existing_unknown_paths},
        },
        "output_hashes": {str(output_path.relative_to(root)): sha256_bytes(payload)},
        "next_gate": "VERIFIED_SLICE_EXPORT_ALLOWED_FULL_P0_BLOCKED" if missing_requirements else "EXPORT_PENDING",
    }
    report_payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    _write(report_path, report_payload, resume)
    return report


def _claim_payload(claim: dict[str, Any]) -> dict[str, Any]:
    return {
        "normalized": claim["normalized"], "canonical_text": claim["canonical_text"],
        "natural_text": claim["natural_text"], "text_graph_alignment": claim["text_graph_alignment"],
    }


def export_benchmark(
    *, dry_run: bool, resume: bool, seed: int, limit: int | None,
    config: Path | None = None, root: Path = ROOT,
) -> dict[str, Any]:
    quota_version, export_version, policy = _versions(config)
    source_path = root / "sampled" / f"pairs.{quota_version}.seed_{seed}.jsonl"
    quota_report_path = root / "reports" / f"quota.{quota_version}.seed_{seed}.json"
    release_dir = root / "release" / export_version
    master_path = release_dir / "pairs.jsonl"
    claims_path = release_dir / "claims.jsonl"
    unknown_path = release_dir / "unknown_challenge.jsonl"
    manifest_path = release_dir / "manifest.json"
    card_path = release_dir / "DATASET_CARD.md"
    if dry_run:
        return {"status": "PLANNED", "input": str(source_path.relative_to(root)), "release_dir": str(release_dir.relative_to(root))}
    if not source_path.exists() or not quota_report_path.exists():
        return {"status": "BLOCKED_SOURCE", "reason": "QUOTA_OUTPUT_MISSING"}
    rows = _load_jsonl(source_path)
    if limit is not None:
        rows = rows[:limit]
    pair_validator = Draft202012Validator(json.loads((root / "schemas/benchmark_pair.schema.json").read_text()))
    claim_validator = Draft202012Validator(json.loads((root / "schemas/benchmark_claim.schema.json").read_text()))
    enrichment_paths = (
        _configured_paths(
            root=root, policy=policy, key="media_reference_enrichment_paths",
            default=root / "data/media_index/unused.jsonl",
        )
        if policy.get("media_reference_enrichment_paths") else []
    )
    enrichment_rows = [row for path in enrichment_paths for row in _load_jsonl(path)]
    media_enrichment_by_source_item = {
        row["source_item_id"]: row for row in enrichment_rows
    }
    if len(media_enrichment_by_source_item) != len(enrichment_rows):
        raise ValueError("DUPLICATE_MEDIA_ENRICHMENT_SOURCE_ITEM_ID")
    pairs, claims = [], []
    split_counts: Counter[str] = Counter()
    for row in rows:
        graph = json.loads((root / row["world_graph_path"]).read_text())
        evidence = json.loads((root / row["evidence_subgraph_path"]).read_text())
        evidence_media_ids = set(evidence["media_ids"])
        selected_media = [item for item in graph["media"] if item["media_id"] in evidence_media_ids]
        if not selected_media:
            raise ValueError(f"EVIDENCE_MEDIA_MISSING:{row['pair_id']}")
        trace_path = root / next(path for path in row["artifacts"] if path.startswith("construction_traces/") and path.endswith(".json"))
        trace = json.loads(trace_path.read_text())
        certificate = json.loads((root / row["certificate_path"]).read_text())
        source_revision = selected_media[0]["source_revision"]
        raw_types = {item["media_type"] for item in selected_media}
        normalized_types = {"image": "single_image", "video": "continuous_video"}
        media_type = normalized_types.get(next(iter(raw_types)), next(iter(raw_types))) if len(raw_types) == 1 else "mixed"
        reference_keys = (
            "media_id", "relative_path", "archive_member", "source_revision", "reference_frame",
            "support_frames", "frame_roles", "validation_scope", "ordered_frame_manifest",
            "ordered_frame_manifest_key", "ordered_frame_count", "source_reference_only",
            "local_media_byte_validation", "media_manifest", "media_manifest_key", "frame_count",
            "bbox_annotation_identity_scope",
        )
        enrichment_keys = (
            "required_bbox_frame_indices", "required_support_frame_indices", "selection_reason",
        )
        pair_enrichments = [
            media_enrichment_by_source_item[source_item_id]
            for source_item_id in row["source_item_ids"]
            if source_item_id in media_enrichment_by_source_item
        ]
        source_references = []
        for item in selected_media:
            reference = {key: item[key] for key in reference_keys if key in item}
            media_facts = sorted(
                (
                    fact for fact in evidence["facts"]
                    if item["media_id"] in fact.get("grounding", {}).get("media_ids", [])
                ),
                key=lambda fact: fact["fact_id"],
            )
            bbox_annotations = [
                {
                    "fact_id": fact["fact_id"],
                    "source_item_ids": fact["provenance"]["source_item_ids"],
                    "bbox_annotation_keys": fact["grounding"]["bbox_annotation_keys"],
                }
                for fact in media_facts if "bbox_annotation_keys" in fact.get("grounding", {})
            ]
            if bbox_annotations:
                reference["evidence_bbox_annotations"] = bbox_annotations
                reference["entity_identity_policies"] = sorted({
                    fact["grounding"]["entity_identity_policy"]
                    for fact in media_facts if "entity_identity_policy" in fact.get("grounding", {})
                })
            matching = [value for value in pair_enrichments if value.get("media_id") == item["media_id"]]
            if len(matching) > 1:
                raise ValueError(f"AMBIGUOUS_MEDIA_ENRICHMENT:{row['pair_id']}:{item['media_id']}")
            if matching:
                reference.update({key: matching[0][key] for key in enrichment_keys if key in matching[0]})
            source_references.append(reference)
        media = {
            "media_type": media_type,
            "media_ids": [item["media_id"] for item in selected_media],
            "source_references": source_references,
        }
        pair = {
            "pair_id": row["pair_id"], "schema_version": "2.0",
            "source": {"source_dataset": row["source_dataset"], "source_item_ids": row["source_item_ids"], "global_world_id": row["global_world_id"], "source_revision": source_revision, "source_hashes": trace["source_hashes"]},
            "media": media,
            "task": {"level": row["level"], "primary_diagnostic_tag": row["primary_track"], "secondary_diagnostic_tags": row["secondary_tracks"], "operator_id": row["operator_id"]},
            "graph_reference": {
                "world_graph_id": graph["world_graph_id"],
                "world_graph_version": row.get("world_graph_version") or Path(row["world_graph_path"]).parent.name or WORLD_GRAPH_VERSION,
                "world_graph_hash": row["world_graph_hash"],
            },
            "supported_claim": _claim_payload(row["supported_claim"]), "contradictory_claim": _claim_payload(row["contradictory_claim"]),
            "construction_trace_id": trace["trace_id"], "certificate_id": certificate["certificate_id"],
            "validation": {"source_reconstruction": "pass", "graph_consistency": "pass", "claim_entailment": "pass", "contradiction_proof": "pass", "graph_text_roundtrip": "pass", "pair_balance": "pass", "level_validation": "pass", "track_validation": "pass", "independent_verifier": "pass", "final_status": "AUTO_ACCEPTED"},
        }
        errors = list(pair_validator.iter_errors(pair))
        if errors:
            raise ValueError(f"PAIR_SCHEMA_INVALID:{row['pair_id']}:{errors[0].message}")
        pairs.append(pair)
        split_counts[row["split"]] += 1
        for suffix, side, label in (("pos", "supported_claim", "SUPPORTED"), ("neg", "contradictory_claim", "CONTRADICTORY")):
            claim = {"sample_id": f"{row['pair_id']}_{suffix}", "pair_id": row["pair_id"], "media": media, "claim": pair[side]["natural_text"], "label": label}
            errors = list(claim_validator.iter_errors(claim))
            if errors:
                raise ValueError(f"CLAIM_SCHEMA_INVALID:{row['pair_id']}:{errors[0].message}")
            claims.append(claim)
    pairs_payload = b"".join(_json_bytes(row) + b"\n" for row in pairs)
    claims_payload = b"".join(_json_bytes(row) + b"\n" for row in claims)
    unknown_version = str(policy.get("unknown_version", UNKNOWN_VERSION))
    unknown_source_paths = _configured_paths(
        root=root, policy=policy, key="unknown_claim_paths",
        default=root / "candidates/unknown" / f"claims.{unknown_version}.jsonl",
    )
    existing_unknown_paths = [path for path in unknown_source_paths if path.exists()]
    unknown_rows = _unique_rows(existing_unknown_paths, "unknown_id") if existing_unknown_paths else []
    unknown_claims = [
        {
            "sample_id": row["unknown_id"], "pair_id": row["parent_pair_id"],
            "media": row["media"], "claim": row["claim"]["natural_text"], "label": "UNKNOWN",
        }
        for row in unknown_rows
    ]
    for claim in unknown_claims:
        errors = list(claim_validator.iter_errors(claim))
        if errors:
            raise ValueError(f"UNKNOWN_CLAIM_SCHEMA_INVALID:{claim['sample_id']}:{errors[0].message}")
    unknown_payload = b"".join(_json_bytes(row) + b"\n" for row in unknown_claims)
    _write(master_path, pairs_payload, resume)
    _write(claims_path, claims_payload, resume)
    _write(unknown_path, unknown_payload, resume)
    quota = json.loads(quota_report_path.read_text())
    manifest = {
        "schema_version": "1.0", "export_version": export_version,
        "status": "VERIFIED_SLICE_EXPORTED" if not quota["release_candidate_eligible"] else "RELEASE_CANDIDATE_EXPORTED",
        "release_candidate_eligible": quota["release_candidate_eligible"], "pair_count": len(pairs), "claim_count": len(claims),
        "unknown_claim_count": len(unknown_claims),
        "split_counts": dict(sorted(split_counts.items())), "media_redistributed": False,
        "upstream_acquisition_required": True, "quota_shortfalls": quota["missing_requirements"],
        "input_hashes": {
            str(source_path.relative_to(root)): sha256_file(source_path),
            str(quota_report_path.relative_to(root)): sha256_file(quota_report_path),
            **{str(path.relative_to(root)): sha256_file(path) for path in existing_unknown_paths},
            **{str(path.relative_to(root)): sha256_file(path) for path in enrichment_paths},
        },
        "output_hashes": {
            str(master_path.relative_to(root)): sha256_bytes(pairs_payload),
            str(claims_path.relative_to(root)): sha256_bytes(claims_payload),
            str(unknown_path.relative_to(root)): sha256_bytes(unknown_payload),
        },
    }
    covered_datasets = ", ".join(sorted({pair["source"]["source_dataset"] for pair in pairs}))
    covered_levels = ", ".join(sorted({pair["task"]["level"] for pair in pairs}))
    covered_tracks = ", ".join(sorted({pair["task"]["primary_diagnostic_tag"] for pair in pairs}))
    card = f"""# SpaceConflict — {export_version}\n\nThis is an automatically verified golden slice, not a full release candidate. It contains {len(pairs)} minimal pairs ({len(claims)} binary claim-level examples) and {len(unknown_claims)} independently exported Unknown claims from {covered_datasets}.\n\n## Task and truth boundary\n\nThe task tests consistency with a partial spatiotemporal world graph. SUPPORTED means entailed by supplied source-grounded facts; CONTRADICTORY means explicitly refuted under the same context; UNKNOWN means both the claim and its negation remain satisfiable. Missing graph edges are never treated as negative facts.\n\n## Data and media\n\nNo source media is redistributed. Records contain frozen upstream source IDs, revisions, hashes, and media locators. Users must acquire upstream data and accept its terms independently. World splits were assigned by `global_world_id` before language realization.\n\n## Validation\n\nEvery included pair passed source reconstruction, graph consistency, proof replay, graph–text–graph round trip, pair balance, decisive-fact ablation, and an independent verifier. Source references explicitly report whether local media bytes were decoded; a source-reference-only marker is not a pixel-validation claim. Unknown examples additionally passed positive and negative witness replay after decisive-view ablation. There was no formal human audit.\n\n## Coverage and known limitations\n\nThis slice currently covers levels {covered_levels} and primary tracks {covered_tracks}. It does not yet provide complete L1–L4, five-track, modality, planned-dataset, or 2,000-example Unknown coverage. It must not be used to claim general spatial reasoning coverage or full SpaceConflict P0 completion. See `manifest.json` for machine-readable shortfalls.\n""".encode()
    _write(card_path, card, resume)
    manifest["output_hashes"][str(card_path.relative_to(root))] = sha256_bytes(card)
    manifest_payload = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    _write(manifest_path, manifest_payload, resume)
    return manifest
