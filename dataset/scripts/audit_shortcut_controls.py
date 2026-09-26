#!/usr/bin/env python3
"""Build and audit the guide's construction-time shortcut controls.

Controls that require a submitted multimodal model are emitted as deterministic
manifests and explicitly marked NOT_MODEL_SCORED. Static benchmark invariants
and the equivalent-inversion verifier are executed here.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

from spaceconflict.generation.language import TEMPLATES, _candidate
from spaceconflict.generation.verification import INVERSE_PREDICATES, independent_label


CONTROL_VERSION = "shortcut_controls_v1"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def payload_sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def write_deterministic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise ValueError(f"NONDETERMINISTIC_CONTROL_OUTPUT:{path}")
    if not path.exists():
        path.write_bytes(payload)


def jsonl_payload(rows: list[dict[str, Any]]) -> bytes:
    return b"".join((compact(row) + "\n").encode("utf-8") for row in rows)


def entropy(counts: Counter[str]) -> dict[str, float]:
    total = sum(counts.values())
    if not total:
        return {"bits": 0.0, "normalized": 0.0}
    probabilities = [count / total for count in counts.values()]
    bits = -sum(value * math.log2(value) for value in probabilities)
    maximum = math.log2(len(counts)) if len(counts) > 1 else 0.0
    return {"bits": bits, "normalized": bits / maximum if maximum else 0.0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--release", default="pilot_verified_2k_v2")
    parser.add_argument("--quota-version", default="quota_pilot_2k_v2")
    parser.add_argument("--analysis-report", type=Path)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--control-version", default=CONTROL_VERSION)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.control_version):
        parser.error("--control-version must be a safe version identifier")
    root = args.root.resolve()
    release_dir = root / "release" / args.release
    controls_dir = root / "controls" / args.release / args.control_version

    pairs = read_jsonl(release_dir / "pairs.jsonl")
    claims = read_jsonl(release_dir / "claims.jsonl")
    sampled_path = root / "sampled" / f"pairs.{args.quota_version}.seed_{args.seed}.jsonl"
    sampled = read_jsonl(sampled_path)
    sampled_by_id = {row["pair_id"]: row for row in sampled}
    pair_by_id = {row["pair_id"]: row for row in pairs}
    claims_by_pair: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        claims_by_pair[claim["pair_id"]].append(claim)
    analysis_path = (
        args.analysis_report.resolve()
        if args.analysis_report is not None
        else root / "reports" / f"pilot_2k.{args.release}.json"
    )
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))

    # Media-only: each minimal pair presents byte-identical media to both labels,
    # so even an oracle over the exact media signature has a 50/50 label tie.
    signature_labels: dict[str, Counter[str]] = defaultdict(Counter)
    pair_media_identity_failures = 0
    for pair in pairs:
        pair_claims = claims_by_pair[pair["pair_id"]]
        signatures = {compact(row["media"]) for row in pair_claims}
        pair_media_identity_failures += int(len(signatures) != 1)
        for row in pair_claims:
            signature_labels[hashlib.sha256(compact(row["media"]).encode()).hexdigest()].update([row["label"]])
    media_oracle_correct = sum(max(counts.values()) for counts in signature_labels.values())
    media_only_upper_bound = media_oracle_correct / len(claims)

    # A deterministic world-disjoint cyclic donor provides a reproducible media
    # shuffle. Context mismatch makes the original claim ungrounded (UNKNOWN).
    ordered = sorted(pairs, key=lambda row: (hashlib.sha256(f"{args.seed}\0{row['pair_id']}".encode()).hexdigest(), row["pair_id"]))
    media_shuffle_rows: list[dict[str, Any]] = []
    for index, pair in enumerate(ordered):
        donor = None
        for offset in range(1, len(ordered)):
            candidate = ordered[(index + offset) % len(ordered)]
            if (
                candidate["supported_claim"]["normalized"]["context"].get("world_id")
                != pair["supported_claim"]["normalized"]["context"].get("world_id")
                and compact(candidate["media"]) != compact(pair["media"])
            ):
                donor = candidate
                break
        if donor is None:
            raise ValueError(f"NO_WORLD_DISJOINT_MEDIA_DONOR:{pair['pair_id']}")
        media_shuffle_rows.append({
            "pair_id": pair["pair_id"],
            "donor_pair_id": donor["pair_id"],
            "original_world_id": pair["supported_claim"]["normalized"]["context"].get("world_id"),
            "donor_world_id": donor["supported_claim"]["normalized"]["context"].get("world_id"),
            "original_media_ids": pair["media"].get("media_ids", []),
            "donor_media": donor["media"],
            "expected_label_after_shuffle": "UNKNOWN",
            "reason": "donor evidence has a disjoint world context",
        })

    # Frame/view controls are manifests rather than copied media, preserving the
    # upstream redistribution policy.
    frame_rows: list[dict[str, Any]] = []
    frame_counts: Counter[str] = Counter()
    degenerate_video_intervals = 0
    multiview_missing_explicit_roles = 0
    for pair in pairs:
        media_type = pair["media"]["media_type"]
        source_reference = pair["media"].get("source_references", [{}])[0]
        context = pair["supported_claim"]["normalized"]["context"]
        if media_type == "multi_view_images" and source_reference.get("frame_roles"):
            role_map = source_reference["frame_roles"]
            support_roles = sorted(
                (role for role in role_map if re.fullmatch(r"support_frame_[1-9][0-9]*", role)),
                key=lambda role: int(role.removeprefix("support_frame_")),
            )
            expected_support_roles = [f"support_frame_{index}" for index in range(1, len(support_roles) + 1)]
            if "reference_frame" not in role_map or not support_roles or support_roles != expected_support_roles:
                multiview_missing_explicit_roles += 1
                continue
            roles = ["reference_frame", *support_roles]
            members = [role_map[role] for role in roles]
            rotated = members[1:] + members[:1]
            frame_rows.append({
                "pair_id": pair["pair_id"], "media_type": media_type,
                "frame_shuffle": {role: member for role, member in zip(roles, rotated)},
                "first_frame_only": {"role": roles[0], "archive_member": members[0], "expected_label_policy": "ORIGINAL_LABEL_REQUIRES_MODEL_SCORING"},
                "last_frame_only": {"role": roles[-1], "archive_member": members[-1], "expected_label_policy": "UNKNOWN_WITHOUT_CERTIFIED_REFERENCE_FRAME"},
                "wrong_view": {"replacement_role": "support_frame_1", "archive_member": members[1], "expected_label_policy": "UNKNOWN_WITHOUT_CERTIFIED_REFERENCE_FRAME"},
            })
            frame_counts.update(["frame_shuffle", "first_frame_only", "last_frame_only", "wrong_view"])
        elif media_type == "multi_view_images":
            multiview_missing_explicit_roles += 1
        elif media_type == "continuous_video":
            interval = context.get("time_scope")
            start = interval.get("start") if isinstance(interval, dict) else None
            end = interval.get("end") if isinstance(interval, dict) else None
            degenerate_video_intervals += int(start is not None and start == end)
            frame_rows.append({
                "pair_id": pair["pair_id"], "media_type": media_type,
                "media_locator": source_reference.get("relative_path"),
                "frame_shuffle": {"operation": "reverse_temporal_order", "scope": interval},
                "first_frame_only": {"timestamp": start, "expected_label_policy": "MODEL_SCORING_REQUIRED"},
                "last_frame_only": {"timestamp": end, "expected_label_policy": "MODEL_SCORING_REQUIRED"},
                "wrong_view": {"status": "NOT_APPLICABLE_NO_ALTERNATE_VIEW"},
            })
            frame_counts.update(["frame_shuffle", "first_frame_only", "last_frame_only"])

    # Equivalent inversion is executable: regenerate the inverse surface form
    # and run the independent verifier against the same world graph.
    family_index = {family: index for index, (family, _) in enumerate(TEMPLATES)}
    world_cache: dict[str, dict[str, Any]] = {}
    inversion_rows: list[dict[str, Any]] = []
    inversion_failures: list[dict[str, Any]] = []
    for row in sampled:
        pair_id = row["pair_id"]
        if row["world_graph_path"] not in world_cache:
            world_cache[row["world_graph_path"]] = json.loads(
                (root / row["world_graph_path"]).read_text(encoding="utf-8")
            )
        world_graph = world_cache[row["world_graph_path"]]
        world_facts = world_graph["facts"]
        for side in ("supported_claim", "contradictory_claim"):
            original = row[side]
            graph = original["normalized"]
            atom = graph["atoms"][0]
            inverse = INVERSE_PREDICATES.get(atom["predicate"])
            if inverse is None or atom.get("object") is None:
                continue
            inverse_graph = copy.deepcopy(graph)
            inverse_atom = inverse_graph["atoms"][0]
            inverse_atom["subject"], inverse_atom["object"] = atom["object"], atom["subject"]
            inverse_atom["predicate"] = inverse
            inverse_atom["atom_id"] = f"{atom.get('atom_id', pair_id)}:equivalent_inverse"
            inverse_graph["claim_graph_id"] = f"{graph['claim_graph_id']}:equivalent_inverse"
            candidate = _candidate(
                f"{pair_id}:equivalent_inverse",
                inverse_graph,
                family_index[row["selected_style_family"]],
                0,
                original.get("entity_aliases", {}),
            )
            candidate["normalized"] = inverse_graph
            result = independent_label(
                candidate=candidate, entity_graph=inverse_graph, world_facts=world_facts,
                authorized_rule_ids=set(world_graph.get("authorized_rule_ids", [])),
            )
            record = {
                "pair_id": pair_id,
                "side": side,
                "original_predicate": atom["predicate"],
                "inverse_predicate": inverse,
                "expected_label": graph["label"],
                "verifier_label": result["label"],
                "original_text": original["natural_text"],
                "equivalent_inverse_text": candidate["natural_text"],
                "equivalent_inverse_normalized": inverse_graph,
                "verifier_evidence_fact_ids": result["evidence_fact_ids"],
            }
            inversion_rows.append(record)
            if result["label"] != graph["label"]:
                inversion_failures.append({
                    "pair_id": pair_id, "side": side,
                    "expected": graph["label"], "actual": result["label"],
                })

    # Generator fingerprint and fixed/diverse realization checks.
    style_label_counts: dict[str, Counter[str]] = defaultdict(Counter)
    candidate_family_counts: list[int] = []
    candidate_surface_counts: list[int] = []
    source_item_strata: Counter[str] = Counter()
    evidence_fact_strata: Counter[str] = Counter()
    for row in sampled:
        labels = ("SUPPORTED", "CONTRADICTORY")
        for label in labels:
            style_label_counts[row["selected_style_family"]].update([label])
        candidates = row["supported_candidates"] + row["contradictory_candidates"]
        candidate_family_counts.append(len({item["style_family"] for item in candidates}))
        candidate_surface_counts.append(len({item["natural_text"] for item in candidates}))
        source_count = len(set(row["source_item_ids"]))
        source_item_strata.update(["single_qa" if source_count == 1 else "fact_bundle"])
        evidence = json.loads((root / row["evidence_subgraph_path"]).read_text(encoding="utf-8"))
        evidence_fact_strata.update(["single_fact" if len(evidence["facts"]) == 1 else "fact_bundle"])
    style_conditional_upper = (
        sum(max(counts.values()) for counts in style_label_counts.values()) / (2 * len(sampled))
        if sampled else None
    )

    media_payload = jsonl_payload(media_shuffle_rows)
    frame_payload = jsonl_payload(frame_rows)
    inversion_payload = jsonl_payload(inversion_rows)
    output_paths = {
        "media_shuffle": controls_dir / "media_shuffle.jsonl",
        "frame_controls": controls_dir / "frame_controls.jsonl",
        "equivalent_inversion": controls_dir / "equivalent_inversion.jsonl",
    }
    for key, payload in (
        ("media_shuffle", media_payload),
        ("frame_controls", frame_payload),
        ("equivalent_inversion", inversion_payload),
    ):
        write_deterministic(output_paths[key], payload)

    label_classifier = analysis["text_only_classifiers"]["label"]
    report = {
        "schema_version": "1.0",
        "control_version": args.control_version,
        "release": args.release,
        "status": "PASS" if not inversion_failures and pair_media_identity_failures == 0 and media_only_upper_bound == 0.5 else "FAIL",
        "control_scope": "construction-time static controls plus executable text/inversion checks; no MLLM scores are fabricated",
        "controls": {
            "text_only": {
                "status": "EXECUTED",
                "accuracy": label_classifier["accuracy"],
                "balanced_accuracy": label_classifier["balanced_accuracy"],
                "roc_auc": label_classifier.get("roc_auc"),
                "leakage_assessment": label_classifier["leakage_assessment"],
            },
            "media_only": {
                "status": "STATIC_EXACT_INPUT_AUDIT_PASS" if pair_media_identity_failures == 0 and media_only_upper_bound == 0.5 else "FAIL",
                "exact_media_signature_count": len(signature_labels),
                "pair_media_identity_failure_count": pair_media_identity_failures,
                "conditional_majority_accuracy_upper_bound": media_only_upper_bound,
                "reason": "both labels in every pair receive identical media",
            },
            "media_shuffle": {
                "status": "MANIFEST_READY_NOT_MODEL_SCORED",
                "case_count": len(media_shuffle_rows),
                "world_disjoint_rate": fmean(row["original_world_id"] != row["donor_world_id"] for row in media_shuffle_rows),
                "manifest": str(output_paths["media_shuffle"].relative_to(root)),
            },
            "frame_shuffle": {
                "status": "MANIFEST_READY_NOT_MODEL_SCORED",
                "case_count": frame_counts["frame_shuffle"],
                "multiview_missing_explicit_role_count": multiview_missing_explicit_roles,
                "manifest": str(output_paths["frame_controls"].relative_to(root)),
            },
            "first_frame_only": {
                "status": "MANIFEST_READY_NOT_MODEL_SCORED",
                "case_count": frame_counts["first_frame_only"],
                "degenerate_video_interval_count": degenerate_video_intervals,
                "manifest": str(output_paths["frame_controls"].relative_to(root)),
            },
            "last_frame_only": {
                "status": "MANIFEST_READY_NOT_MODEL_SCORED",
                "case_count": frame_counts["last_frame_only"],
                "manifest": str(output_paths["frame_controls"].relative_to(root)),
            },
            "wrong_view": {
                "status": "MANIFEST_READY_NOT_MODEL_SCORED",
                "case_count": frame_counts["wrong_view"],
                "applicability": "multi_view_images_with_explicit_frame_roles",
                "multiview_missing_explicit_role_count": multiview_missing_explicit_roles,
                "manifest": str(output_paths["frame_controls"].relative_to(root)),
            },
            "equivalent_inversion": {
                "status": "EXECUTED_PASS" if not inversion_failures and inversion_rows else "FAIL",
                "case_count": len(inversion_rows),
                "pass_count": len(inversion_rows) - len(inversion_failures),
                "failure_count": len(inversion_failures),
                "failure_examples": inversion_failures[:20],
                "manifest": str(output_paths["equivalent_inversion"].relative_to(root)),
            },
            "generator_fingerprint": {
                "status": "EXECUTED",
                "label_leakage_assessment": label_classifier["leakage_assessment"],
                "text_predictability_by_target": analysis["text_only_classifiers"],
                "interpretation": "dataset/level/operator/style fingerprints are reported; only label prediction is a shortcut gate",
            },
            "fixed_template_vs_diverse_realization": {
                "status": "EXECUTED",
                "selected_style_conditional_label_upper_bound": style_conditional_upper,
                "candidate_family_count": {
                    "min": min(candidate_family_counts), "mean": fmean(candidate_family_counts), "max": max(candidate_family_counts),
                },
                "candidate_surface_count": {
                    "min": min(candidate_surface_counts), "mean": fmean(candidate_surface_counts), "max": max(candidate_surface_counts),
                },
                "selected_style_entropy": entropy(Counter(row["selected_style_family"] for row in sampled)),
            },
            "single_qa_vs_fact_bundle": {
                "status": "EXECUTED_WITH_STRATUM_SHORTFALL" if len(source_item_strata) < 2 else "EXECUTED",
                "source_item_count_strata": dict(sorted(source_item_strata.items())),
                "evidence_fact_count_strata": dict(sorted(evidence_fact_strata.items())),
                "shortfall": "single-QA and bundle comparison requires both strata" if len(source_item_strata) < 2 else None,
            },
        },
        "corpus_checks": {
            **analysis["corpus_checks"],
            "realization_family_entropy": entropy(Counter(row["selected_style_family"] for row in sampled)),
            "negation_distribution": {
                "explicit_negation": analysis["corpus_checks"]["explicit_negation_claim_count"],
                "without_explicit_negation": len(claims) - analysis["corpus_checks"]["explicit_negation_claim_count"],
            },
        },
        "input_hashes": {
            str((release_dir / "pairs.jsonl").relative_to(root)): sha256(release_dir / "pairs.jsonl"),
            str((release_dir / "claims.jsonl").relative_to(root)): sha256(release_dir / "claims.jsonl"),
            str(sampled_path.relative_to(root)): sha256(sampled_path),
            str(analysis_path.relative_to(root)): sha256(analysis_path),
        },
        "output_hashes": {
            str(output_paths["media_shuffle"].relative_to(root)): payload_sha256(media_payload),
            str(output_paths["frame_controls"].relative_to(root)): payload_sha256(frame_payload),
            str(output_paths["equivalent_inversion"].relative_to(root)): payload_sha256(inversion_payload),
        },
        "remaining_model_work": [
            "score a declared MLLM on media_shuffle",
            "score the same MLLM on frame_shuffle/first/last/wrong-view manifests",
            "report deltas against its unperturbed predictions",
        ],
    }
    report_path = root / "reports" / f"shortcut_controls.{args.release}.json"
    report_payload = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    report_path.write_bytes(report_payload)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
