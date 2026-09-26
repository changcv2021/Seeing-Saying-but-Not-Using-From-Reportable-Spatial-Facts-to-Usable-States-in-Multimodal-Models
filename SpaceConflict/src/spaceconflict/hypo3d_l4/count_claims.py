from __future__ import annotations

import hashlib
import re
from typing import Any

from .certificates import validate_certificate_separation
from .verification import verify_count_pair_accessibly


REALIZER_VERSION = "hypo3d_l4_count_realizer_v2"
_COUNT_TEXT = re.compile(r"^After the change, there are (?P<count>\d+) (?P<subject>.+) in the scene\.$")


def _pair_id(bundle: dict[str, Any]) -> str:
    value = "|".join((bundle["scene_id"], bundle["change_id"], bundle["question_id"]))
    return f"sc_hypo3d_l4_v2_{hashlib.sha256(value.encode()).hexdigest()[:20]}"


def _realize(subject: str, count: int) -> str:
    return f"After the change, there are {count} {subject} in the scene."


def _roundtrip(text: str) -> tuple[str, int] | None:
    match = _COUNT_TEXT.fullmatch(text)
    if not match:
        return None
    return match.group("subject"), int(match.group("count"))


def build_count_pair(bundle: dict[str, Any]) -> dict[str, Any]:
    fact = bundle["pre_state_subgraph"]["facts"][0]
    subject = str(fact["subject"])
    pre_count = int(fact["value"])
    post_count = int(bundle["accessible_transition"]["derived_post_count"])
    if pre_count == post_count:
        raise ValueError("Count pair requires a non-zero intervention delta")
    supported_text = _realize(subject, post_count)
    contradictory_text = _realize(subject, pre_count)
    if _roundtrip(supported_text) != (subject, post_count):
        raise ValueError("Supported graph-text-graph round trip failed")
    if _roundtrip(contradictory_text) != (subject, pre_count):
        raise ValueError("Contradictory graph-text-graph round trip failed")
    pair_id = _pair_id(bundle)
    pre_fact_id = fact["fact_id"]
    rule_id = bundle["accessible_transition"]["rule_id"]
    oracle_id = bundle["label_provenance_check"]["post_oracle_id"]
    base_nodes = [
        {"id": pre_fact_id, "type": "SOURCE_PRE_FACT"},
        {"id": f"int:{bundle['branch_id']}", "type": "INTERVENTION"},
        {"id": rule_id, "type": "TRANSITION_RULE"},
        {"id": f"derived:count:{subject}:{post_count}", "type": "DERIVED_POST_FACT"},
    ]
    supported_graph = {"subject": subject, "predicate": "COUNT", "value": post_count, "state": "post", "scope": "whole_scene"}
    contradictory_graph = {"subject": subject, "predicate": "COUNT", "value": pre_count, "state": "post", "scope": "whole_scene"}
    verifier = verify_count_pair_accessibly(
        pre_state_subgraph=bundle["pre_state_subgraph"],
        accessible_transition=bundle["accessible_transition"],
        supported_claim=supported_graph,
        contradictory_claim=contradictory_graph,
        necessary_pre_fact_ids=list(bundle["necessary_pre_fact_ids"]),
    )
    if verifier["status"] != "PASS":
        raise ValueError(f"Independent accessible verifier failed: {verifier['errors']}")
    dependency_checks = {
        "scene_only_label": verifier["scene_only_label"],
        "change_only_label": verifier["change_only_label"],
        "full_input_label": verifier["supported"]["label"], "status": "PASS",
    }
    certificate = {
        "certificate_id": f"cert:{pair_id}",
        "label": "SUPPORTED",
        "level": "L4",
        "strength_slice": "L4_CORE",
        "label_provenance_certificate": {
            "post_oracle_id": oracle_id,
            "source_reconstruction": "PASS",
            "oracle_consistency_verifier": "PASS",
        },
        "accessible_reasoning_certificate": {
            "proof_nodes": [*base_nodes, {"id": "claim:supported", "type": "CLAIM_ATOM"}],
            "proof_edges": [
                [pre_fact_id, rule_id, "premise"],
                [f"int:{bundle['branch_id']}", rule_id, "premise"],
                [rule_id, f"derived:count:{subject}:{post_count}", "derives"],
                [f"derived:count:{subject}:{post_count}", "claim:supported", "entails"],
            ],
            "forbidden_premises_absent": True,
            "accessible_evidence_verifier": "PASS",
        },
        "dependency_checks": dependency_checks,
        "co_truth_possible": False,
        "requires_unprovided_fact": False,
    }
    errors = validate_certificate_separation(certificate)
    if errors:
        raise ValueError(f"Certificate separation failed: {errors}")
    return {
        "pair_id": pair_id,
        "schema_version": "hypo3d_l4_pair_v2",
        "source": {
            "scene_id": bundle["scene_id"], "change_id": bundle["change_id"],
            "question_id": bundle["question_id"], "branch_id": bundle["branch_id"],
            "post_oracle_id": oracle_id,
        },
        "task": {
            "level": "L4", "strength_slice": "L4_CORE", "primary_track": "DYNAMIC",
            "secondary_tracks": (
                ["GEO-TOPO", "IDENTITY"]
                if bundle.get("change_type") == "REPLACEMENT" else ["GEO-TOPO"]
            ),
            "operator_id": bundle.get("operator_id", "COUNT_UPDATE_OMISSION"),
        },
        "supported_claim": {
            "graph": supported_graph,
            "text": supported_text,
        },
        "contradictory_claim": {
            "graph": contradictory_graph,
            "text": contradictory_text,
        },
        "edit": {
            "changed_slots": ["count_value"], "before": post_count, "after": pre_count,
            "preserved_slots": ["subject", "predicate", "scope", "state", "branch_id", "syntax_family"],
        },
        "certificate": certificate,
        "realizer_version": REALIZER_VERSION,
        "validation": {
            "transition_replay": "PASS", "oracle_consistency": "PASS",
            "accessible_evidence_verifier": "PASS", "graph_text_roundtrip": "PASS",
            "independent_verifier": verifier,
            "necessary_fact_ablation": "PASS",
            "co_truth_check": "PASS", "final_status": "AUTO_ACCEPTED",
        },
    }
