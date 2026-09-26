from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from ..graphs.pipeline import WORLD_GRAPH_VERSION
from ..hashing import sha256_bytes, sha256_file
from ..registry import ROOT
from .claims import CLAIM_BUILD_VERSION
from .language import TEXT_VERIFICATION_VERSION, _parse


PROOF_VERIFICATION_VERSION = "proof_verification_p1_v2"

ASYMMETRIC_PREDICATES = {
    "LEFT_OF", "RIGHT_OF", "FRONT_OF", "BEHIND", "ABOVE", "BELOW", "BEFORE", "AFTER",
}
INVERSE_PREDICATES = {
    "LEFT_OF": "RIGHT_OF", "RIGHT_OF": "LEFT_OF",
    "FRONT_OF": "BEHIND", "BEHIND": "FRONT_OF",
    "ABOVE": "BELOW", "BELOW": "ABOVE",
    "BEFORE": "AFTER", "AFTER": "BEFORE",
}
TRANSITIVE_RULES = {
    "LEFT_OF": "AUTHORIZED_DIRECTION_TRANSITIVITY",
    "RIGHT_OF": "AUTHORIZED_DIRECTION_TRANSITIVITY",
    "ABOVE": "AUTHORIZED_DIRECTION_TRANSITIVITY",
    "BELOW": "AUTHORIZED_DIRECTION_TRANSITIVITY",
    "BEFORE": "STRICT_ORDER_TRANSITIVITY",
    "AFTER": "STRICT_ORDER_TRANSITIVITY",
}


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


def _same_context(fact: dict[str, Any], parsed: dict[str, Any]) -> bool:
    return all(fact["context"].get(key) == value for key, value in parsed["context"].items())


def _two_hop_evidence(
    *, parsed: dict[str, Any], world_facts: list[dict[str, Any]],
    authorized_rule_ids: set[str], reverse: bool = False,
) -> list[dict[str, Any]]:
    predicate = parsed["predicate"]
    rule = TRANSITIVE_RULES.get(predicate)
    if rule not in authorized_rule_ids or parsed["polarity"] != "positive":
        return []
    subject = parsed["object"] if reverse else parsed["subject"]
    object_ = parsed["subject"] if reverse else parsed["object"]
    normalized_edges: list[tuple[str, str, dict[str, Any]]] = []
    inverse = INVERSE_PREDICATES.get(predicate)
    for fact in world_facts:
        if (
            fact.get("polarity") != "positive"
            or not isinstance(fact.get("subject"), str)
            or not isinstance(fact.get("object"), str)
            or not _same_context(fact, parsed)
        ):
            continue
        if fact.get("predicate") == predicate:
            normalized_edges.append((fact["subject"], fact["object"], fact))
        elif fact.get("predicate") == inverse:
            normalized_edges.append((fact["object"], fact["subject"], fact))
    second_by_subject: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for edge in normalized_edges:
        second_by_subject.setdefault(edge[0], []).append(edge)
    paths = [
        (first[2], second[2])
        for first in normalized_edges if first[0] == subject
        for second in second_by_subject.get(first[1], [])
        if second[1] == object_ and subject != object_
    ]
    if len(paths) != 1:
        return []
    return list(paths[0])


def independent_label(
    *, candidate: dict[str, Any], entity_graph: dict[str, Any], world_facts: list[dict[str, Any]],
    authorized_rule_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Classify text without generator label, operator, edit trace, or certificate."""
    parsed = _parse(candidate, entity_graph)
    if parsed is None:
        return {"label": "UNKNOWN", "normalized_claim": None, "evidence_fact_ids": [], "co_truth_possible": True, "requires_unprovided_fact": True, "unknown_reason": "TEXT_PARSE_FAILED", "suggested_level": None}
    authorized_rule_ids = authorized_rule_ids or set()
    direct_supporting = [
        fact for fact in world_facts
        if fact["predicate"] == parsed["predicate"]
        and fact["subject"] == parsed["subject"] and fact.get("object") == parsed["object"]
        and fact.get("value") == parsed.get("value")
        and fact["polarity"] == parsed["polarity"] and _same_context(fact, parsed)
    ]
    inverse_supporting = [
        fact for fact in world_facts
        if INVERSE_PREDICATES.get(parsed["predicate"]) == fact["predicate"]
        and fact["subject"] == parsed["object"] and fact.get("object") == parsed["subject"]
        and fact.get("value") == parsed.get("value")
        and fact["polarity"] == parsed["polarity"] and _same_context(fact, parsed)
    ]
    transitive_supporting = _two_hop_evidence(
        parsed=parsed, world_facts=world_facts, authorized_rule_ids=authorized_rule_ids,
    )
    supporting_by_id = {
        fact["fact_id"]: fact for fact in direct_supporting + inverse_supporting + transitive_supporting
    }
    supporting = [supporting_by_id[key] for key in sorted(supporting_by_id)]
    explicit_polarity_refuting = [
        fact for fact in world_facts
        if fact["predicate"] == parsed["predicate"]
        and fact["subject"] == parsed["subject"] and fact.get("object") == parsed["object"]
        and fact.get("value") == parsed.get("value")
        and fact["polarity"] != parsed["polarity"] and _same_context(fact, parsed)
    ]
    count_refuting = [
        fact for fact in world_facts
        if parsed["predicate"] == "COUNT" and fact["predicate"] == "COUNT"
        and fact["subject"] == parsed["subject"] and fact.get("object") == parsed["object"]
        and fact.get("value") != parsed.get("value")
        and fact["polarity"] == "positive" and parsed["polarity"] == "positive"
        and _same_context(fact, parsed)
    ]
    asymmetric_refuting = [
        fact for fact in world_facts
        if parsed["predicate"] in ASYMMETRIC_PREDICATES and fact["predicate"] == parsed["predicate"]
        and fact["subject"] == parsed["object"] and fact.get("object") == parsed["subject"]
        and fact["polarity"] == "positive" and _same_context(fact, parsed)
    ]
    inverse_exclusive_refuting = [
        fact for fact in world_facts
        if INVERSE_PREDICATES.get(parsed["predicate"]) == fact["predicate"]
        and fact["subject"] == parsed["subject"] and fact.get("object") == parsed["object"]
        and fact["polarity"] == "positive" and parsed["polarity"] == "positive"
        and _same_context(fact, parsed)
    ]
    transitive_refuting = _two_hop_evidence(
        parsed=parsed, world_facts=world_facts,
        authorized_rule_ids=authorized_rule_ids, reverse=True,
    )
    refuting_by_id = {
        fact["fact_id"]: fact
        for fact in explicit_polarity_refuting + count_refuting + asymmetric_refuting + inverse_exclusive_refuting + transitive_refuting
    }
    refuting = [refuting_by_id[key] for key in sorted(refuting_by_id)]
    if supporting and not refuting:
        label, evidence, co_truth = "SUPPORTED", supporting, False
    elif refuting and not supporting:
        label, evidence, co_truth = "CONTRADICTORY", refuting, False
    else:
        label, evidence, co_truth = "UNKNOWN", supporting + refuting, bool(supporting and refuting)
    return {
        "label": label, "normalized_claim": parsed,
        "evidence_fact_ids": sorted(fact["fact_id"] for fact in evidence),
        "co_truth_possible": co_truth, "requires_unprovided_fact": False,
        "unknown_reason": "NO_DECISIVE_FACT" if label == "UNKNOWN" else None,
        "suggested_level": (
            "L2" if (transitive_supporting or transitive_refuting)
            else "L3" if parsed["predicate"] == "BEFORE" else "L1"
        ) if label != "UNKNOWN" else None,
    }


def verify_proofs(
    *, dry_run: bool, resume: bool, limit: int | None,
    text_verification_version: str = TEXT_VERIFICATION_VERSION,
    world_graph_manifest: str | None = None,
    proof_verification_version: str = PROOF_VERIFICATION_VERSION,
    root: Path = ROOT,
) -> dict[str, Any]:
    source_path = root / "candidates/verified" / f"pairs.{text_verification_version}.jsonl"
    manifest_path = (
        root / world_graph_manifest if world_graph_manifest
        else root / "world_graphs" / f"manifest.{WORLD_GRAPH_VERSION}.jsonl"
    )
    output_path = root / "candidates/auto_accepted" / f"pairs.{proof_verification_version}.jsonl"
    verifier_path = root / "verifier_outputs" / f"results.{proof_verification_version}.jsonl"
    reject_path = root / "rejected/verification" / f"pairs.{proof_verification_version}.jsonl"
    report_path = root / "reports" / f"proof_verification.{proof_verification_version}.json"
    if dry_run:
        return {"status": "PLANNED", "input": str(source_path.relative_to(root)), "output": str(output_path.relative_to(root))}
    if not source_path.exists() or not manifest_path.exists():
        return {"status": "BLOCKED_SOURCE", "reason": "TEXT_OR_WORLD_GRAPH_MISSING"}
    rows = _load_jsonl(source_path)
    if limit is not None:
        rows = rows[:limit]
    manifest = {row["global_world_id"]: row for row in _load_jsonl(manifest_path)}
    certificate_validator = Draft202012Validator(json.loads((root / "schemas/proof_certificate.schema.json").read_text()))
    accepted, rejects, verifier_rows = [], [], []
    reject_counts: Counter[str] = Counter()
    for row in rows:
        pair_id = row["pair_id"]
        graph_row = manifest.get(row["global_world_id"])
        codes: list[str] = []
        if graph_row is None or graph_row["validation_status"] != "GRAPH_VALID":
            codes.append("GRAPH_UNSAT_BEFORE_CORRUPTION")
            graph = {"facts": [], "authorized_rule_ids": []}
        else:
            graph = json.loads((root / graph_row["graph_path"]).read_text())
            if sha256_file(root / graph_row["graph_path"]) != graph_row["graph_sha256"]:
                codes.append("GRAPH_HASH_MISMATCH")
        results = {}
        for side, expected in (("supported", "SUPPORTED"), ("contradictory", "CONTRADICTORY")):
            claim = row[f"{side}_claim"]
            result = independent_label(
                candidate=claim, entity_graph=claim["normalized"], world_facts=graph["facts"],
                authorized_rule_ids=set(graph.get("authorized_rule_ids", [])),
            )
            results[side] = result
            if result["label"] != expected:
                codes.append("VERIFIER_DISAGREEMENT")
            if result["co_truth_possible"]:
                codes.append("CO_TRUTH_POSSIBLE")
            if result["requires_unprovided_fact"]:
                codes.append("UNPROVIDED_PREMISE")
        certificate_path = root / next(path for path in row["artifacts"] if path.startswith("certificates/") and path.endswith(".json"))
        evidence_path = root / next(path for path in row["artifacts"] if path.startswith("evidence_subgraphs/") and path.endswith(".json"))
        if not certificate_path.exists() or not evidence_path.exists():
            codes.append("MISSING_PROOF_ARTIFACT")
            certificate, evidence = {}, {}
        else:
            certificate = json.loads(certificate_path.read_text())
            evidence = json.loads(evidence_path.read_text())
            if list(certificate_validator.iter_errors(certificate)):
                codes.append("PROOF_SCHEMA_INVALID")
            rule_ids = {
                node["id"].removeprefix("rule:") for node in certificate.get("proof_nodes", [])
                if node.get("type") == "RULE"
            }
            if not rule_ids <= set(graph.get("authorized_rule_ids", [])):
                codes.append("UNAUTHORIZED_RULE")
            world_fact_ids = {fact["fact_id"] for fact in graph.get("facts", [])}
            evidence_ids = set(certificate.get("evidence_fact_ids", []))
            if not evidence_ids or evidence_ids != set(evidence.get("minimality", {}).get("required_fact_ids", [])) or not evidence_ids <= world_fact_ids:
                codes.append("UNPROVIDED_PREMISE")
            for removed_id in sorted(evidence_ids):
                ablated_facts = [fact for fact in graph.get("facts", []) if fact["fact_id"] != removed_id]
                ablated_result = independent_label(
                    candidate=row["contradictory_claim"],
                    entity_graph=row["contradictory_claim"]["normalized"],
                    world_facts=ablated_facts,
                    authorized_rule_ids=set(graph.get("authorized_rule_ids", [])),
                )
                if ablated_result["label"] != "UNKNOWN":
                    codes.append("MINIMALITY_ABLATION_FAIL")
                    break
        verifier_record = {
            "pair_id": pair_id, "inputs_excluded": ["generator_label", "operator", "changed_slot", "proof", "construction_trace"],
            "supported": results["supported"], "contradictory": results["contradictory"],
            "certificate_replay": "PASS" if not codes else "FAIL",
        }
        verifier_rows.append(verifier_record)
        if codes:
            unique_codes = sorted(set(codes))
            reject_counts.update(unique_codes)
            rejects.append({"pair_id": pair_id, "reject_codes": unique_codes, "verifier": verifier_record})
        else:
            accepted.append({
                **row, "certificate_path": str(certificate_path.relative_to(root)),
                "evidence_subgraph_path": str(evidence_path.relative_to(root)),
                "world_graph_path": graph_row["graph_path"], "world_graph_hash": graph_row["graph_sha256"],
                "independent_verifier": verifier_record, "status": "AUTO_ACCEPTED",
            })
    accepted_payload = b"".join(_json_bytes(row) + b"\n" for row in accepted)
    verifier_payload = b"".join(_json_bytes(row) + b"\n" for row in verifier_rows)
    rejects_payload = b"".join(_json_bytes(row) + b"\n" for row in rejects)
    for path, payload in ((output_path, accepted_payload), (verifier_path, verifier_payload), (reject_path, rejects_payload)):
        _write(path, payload, resume)
    report = {
        "schema_version": "1.0", "proof_verification_version": proof_verification_version,
        "status": "VERIFIER_VALID" if accepted and not rejects else ("PARTIAL" if accepted else "REJECTED"),
        "input_pair_count": len(rows), "auto_accepted_count": len(accepted), "rejected_count": len(rejects),
        "reject_code_counts": dict(sorted(reject_counts.items())),
        "independent_verifier_agreement_rate": len(accepted) / len(rows) if rows else 0.0,
        "certificate_replay_pass_rate": len(accepted) / len(rows) if rows else 0.0,
        "minimality_ablation_pass_rate": len(accepted) / len(rows) if rows else 0.0,
        "input_hashes": {str(source_path.relative_to(root)): sha256_file(source_path), str(manifest_path.relative_to(root)): sha256_file(manifest_path)},
        "output_hashes": {str(output_path.relative_to(root)): sha256_bytes(accepted_payload), str(verifier_path.relative_to(root)): sha256_bytes(verifier_payload), str(reject_path.relative_to(root)): sha256_bytes(rejects_payload)},
        "next_gate": "QUOTA_AUDIT_AND_EXPORT_PENDING",
    }
    report_payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    _write(report_path, report_payload, resume)
    return report
