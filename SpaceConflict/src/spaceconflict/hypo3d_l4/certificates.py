from __future__ import annotations

from typing import Any


ACCESSIBLE_NODE_TYPES = {
    "SOURCE_PRE_FACT", "TARGET_RESOLUTION", "INTERVENTION", "TRANSITION_RULE",
    "DERIVED_POST_FACT", "CLAIM_ATOM", "CONTRADICTION", "CORRECTION",
}
FORBIDDEN_ACCESSIBLE_NODE_TYPES = {"SOURCE_POST_ORACLE", "SOURCE_ANSWER"}


def classify_strength(
    *, full_label: str, scene_only_label: str, change_only_label: str,
    necessary_pre_fact_ids: list[str],
) -> tuple[str | None, str | None]:
    if full_label not in {"SUPPORTED", "CONTRADICTORY"}:
        return None, "REJECT_TRANSITION_PRECONDITION_FAIL"
    if scene_only_label != "UNKNOWN":
        return None, "REJECT_SCENE_ONLY_SUFFICIENT"
    if change_only_label == "UNKNOWN" and necessary_pre_fact_ids:
        return "L4_CORE", None
    if change_only_label in {"SUPPORTED", "CONTRADICTORY"}:
        return "L4_CALIBRATION", None
    return None, "REJECT_PRESTATE_MISSING"


def validate_certificate_separation(certificate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    provenance = certificate.get("label_provenance_certificate")
    reasoning = certificate.get("accessible_reasoning_certificate")
    if not isinstance(provenance, dict) or not provenance.get("post_oracle_id"):
        errors.append("MISSING_LABEL_PROVENANCE_ORACLE")
    if not isinstance(reasoning, dict):
        return errors + ["MISSING_ACCESSIBLE_REASONING_CERTIFICATE"]
    node_types = {
        str(node.get("type")) for node in reasoning.get("proof_nodes", []) if isinstance(node, dict)
    }
    forbidden = sorted(node_types & FORBIDDEN_ACCESSIBLE_NODE_TYPES)
    if forbidden:
        errors.append(f"ORACLE_LEAK_IN_ACCESSIBLE_REASONING:{','.join(forbidden)}")
    unknown = sorted(node_types - ACCESSIBLE_NODE_TYPES)
    if unknown:
        errors.append(f"UNKNOWN_ACCESSIBLE_NODE_TYPE:{','.join(unknown)}")
    dependencies = certificate.get("dependency_checks", {})
    strength = certificate.get("strength_slice")
    if strength == "L4_CORE" and (
        dependencies.get("scene_only_label") != "UNKNOWN"
        or dependencies.get("change_only_label") != "UNKNOWN"
    ):
        errors.append("L4_CORE_DEPENDENCY_FAIL")
    return errors

