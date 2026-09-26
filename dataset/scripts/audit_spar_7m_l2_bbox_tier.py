#!/usr/bin/env python3
"""Independent closure audit for accepted SPAR bbox-identity L2 pairs."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from spaceconflict.hashing import sha256_file


IDENTITY_POLICY = "EXACT_SAME_IMAGE_PATH_AND_INTEGER_BBOX_ANNOTATION_KEY"
TRANSITIVE = {"LEFT_OF", "RIGHT_OF", "ABOVE", "BELOW"}


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.open() if line.strip()]


def context_key(fact: dict[str, Any]) -> str:
    return json.dumps(fact["context"], sort_keys=True, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-version", default="spar_7m_l2_bbox_tier_audit_v1")
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root, proof_path, output_path = args.root.resolve(), args.proof.resolve(), args.output.resolve()
    failures: list[dict[str, Any]] = []
    predicate_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    paths_checked = ablations_checked = 0
    rows = load(proof_path)
    for row in rows:
        pair_failures: list[str] = []
        if row.get("status") != "AUTO_ACCEPTED" or row.get("level") != "L2":
            pair_failures.append("NOT_AUTO_ACCEPTED_L2")
        if row.get("operator_id") != "RELATION_GRAPH_UNSAT" or row.get("primary_track") != "GEO-TOPO":
            pair_failures.append("WRONG_OPERATOR_OR_TRACK")
        verifier = row.get("independent_verifier", {})
        if (
            verifier.get("certificate_replay") != "PASS"
            or verifier.get("supported", {}).get("label") != "SUPPORTED"
            or verifier.get("contradictory", {}).get("label") != "CONTRADICTORY"
            or verifier.get("supported", {}).get("suggested_level") != "L2"
            or verifier.get("contradictory", {}).get("suggested_level") != "L2"
        ):
            pair_failures.append("INDEPENDENT_VERIFIER_NOT_STRICT_L2")
        evidence = json.loads((root / row["evidence_subgraph_path"]).read_text())
        certificate = json.loads((root / row["certificate_path"]).read_text())
        graph = json.loads((root / row["world_graph_path"]).read_text())
        facts = evidence.get("facts", [])
        if len(facts) != 2:
            pair_failures.append("EVIDENCE_FACT_COUNT_NOT_TWO")
        else:
            first, second = facts
            predicate_counts[first.get("predicate", "MISSING")] += 1
            if (
                first.get("predicate") not in TRANSITIVE
                or first.get("predicate") != second.get("predicate")
                or context_key(first) != context_key(second)
            ):
                pair_failures.append("PREMISE_PREDICATE_OR_CONTEXT_MISMATCH")
            if not all(
                fact.get("grounding", {}).get("entity_identity_policy") == IDENTITY_POLICY
                and "bbox_annotation_keys" in fact.get("grounding", {})
                and fact.get("provenance", {}).get("origin_type") == "QA_DIRECT"
                for fact in facts
            ):
                pair_failures.append("BBOX_IDENTITY_OR_DIRECT_PROVENANCE_MISSING")
            orderings = [
                (a, b) for a, b in ((first, second), (second, first))
                if a.get("object") == b.get("subject")
            ]
            supported_atom = row["supported_claim"]["normalized"]["atoms"][0]
            matching = [
                (a, b) for a, b in orderings
                if supported_atom.get("predicate") == a.get("predicate")
                and supported_atom.get("subject") == a.get("subject")
                and supported_atom.get("object") == b.get("object")
            ]
            if len(matching) != 1:
                pair_failures.append("PREMISES_DO_NOT_FORM_CLAIMED_UNIQUE_CHAIN")
            else:
                a, b = matching[0]
                graph_facts = [
                    fact for fact in graph["facts"]
                    if fact.get("predicate") == a["predicate"] and context_key(fact) == context_key(a)
                ]
                direct = {(fact["subject"], fact.get("object")) for fact in graph_facts}
                conclusion = (a["subject"], b["object"])
                if conclusion in direct:
                    pair_failures.append("DIRECT_CONCLUSION_PRESENT")
                outgoing: dict[str, list[str]] = defaultdict(list)
                for subject, object_ in direct:
                    if isinstance(object_, str):
                        outgoing[subject].append(object_)
                proof_middles = [middle for middle in outgoing[conclusion[0]] if conclusion[1] in outgoing[middle]]
                paths_checked += 1
                if len(set(proof_middles)) != 1:
                    pair_failures.append("TWO_HOP_PATH_NOT_UNIQUE")
        required = set(evidence.get("minimality", {}).get("required_fact_ids", []))
        ablations = certificate.get("minimality", {}).get("ablation_results", [])
        ablations_checked += len(ablations)
        if (
            len(required) != 2 or required != set(certificate.get("evidence_fact_ids", []))
            or {item.get("removed_fact_id") for item in ablations} != required
            or any(item.get("result") != "UNKNOWN" for item in ablations)
        ):
            pair_failures.append("MINIMALITY_CERTIFICATE_INVALID")
        evidence_media = set(evidence.get("media_ids", []))
        selected_media = [media for media in graph["media"] if media.get("media_id") in evidence_media]
        if (
            len(selected_media) != 1 or selected_media[0].get("media_type") != "single_image"
            or selected_media[0].get("source_reference_only") is not True
            or selected_media[0].get("local_media_byte_validation") != "NOT_PERFORMED_UNDERLYING_MEDIA_NOT_PRESENT"
        ):
            pair_failures.append("MEDIA_SCOPE_DISCLOSURE_INVALID")
        if pair_failures:
            failures.append({"pair_id": row.get("pair_id"), "failure_codes": sorted(set(pair_failures))})
        split_counts[row.get("split", "MISSING")] += 1
    report = {
        "schema_version": "1.0", "audit_version": args.audit_version,
        "status": "PASS" if rows and not failures else "FAIL", "run_id": args.run_id,
        "accepted_pairs_checked": len(rows), "failure_count": len(failures), "failures": failures,
        "two_hop_paths_checked": paths_checked, "fact_ablations_checked": ablations_checked,
        "predicate_counts": dict(sorted(predicate_counts.items())), "split_counts": dict(sorted(split_counts.items())),
        "identity_policy": IDENTITY_POLICY,
        "media_validation_scope": "OFFICIAL_ANNOTATION_PATH_AND_BBOX_REFERENCES_ONLY_NO_LOCAL_PIXEL_BYTES",
        "input_hashes": {str(proof_path.relative_to(root)): sha256_file(proof_path)},
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        if not args.resume:
            raise FileExistsError(output_path)
        if output_path.read_bytes() != payload:
            raise ValueError("NON_DETERMINISTIC_OUTPUT")
    else:
        output_path.write_bytes(payload)
    print(payload.decode(), end="")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
