from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ..hashing import sha256_file
from .certificates import validate_certificate_separation
from .common import jsonl_bytes, write_versioned
from .normalize_qa import normalize_post_qa
from .verification import verify_count_pair_accessibly, verify_existence_pair_accessibly


MEDIA_ROLES = (
    "camera_view", "top_view_label", "top_view_no_label",
    "top_view_no_label_rotated", "top_view_with_label_rotated",
)
FORBIDDEN_MODEL_INPUT_KEYS = {
    "source_answer", "source_answer_raw", "post_oracle", "post_oracle_id",
    "gold_label", "label", "operator", "operator_id", "proof", "certificate",
    "changed_slot", "changed_slots",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row["scene_id"]), str(row["change_id"]),
        str(row.get("question_id") or row.get("source_question_id")),
    )


def _forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_MODEL_INPUT_KEYS:
                found.add(key)
            found.update(_forbidden_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_forbidden_keys(child))
    return found


def verification_status(
    *, accepted_count: int, calibration_ratio_pass: bool, p0_minimum: int,
) -> str:
    if not calibration_ratio_pass:
        return "REJECT_CALIBRATION_RATIO_EXCEEDED"
    if accepted_count == 0:
        return "VERIFIED_CANDIDATE_SET_EMPTY"
    if accepted_count >= p0_minimum:
        return "VERIFIED_CANDIDATE_SET_VALID_P0_MET"
    return "VERIFIED_CANDIDATE_SET_VALID_P0_SHORTFALL"


def verify_official_count_pairs(
    *, branch_index: Path, post_oracles: Path, prestates: Path, pairs: Path,
    media_root: Path, output_dir: Path, dry_run: bool, resume: bool,
) -> dict[str, Any]:
    outputs = {
        "pairs": output_dir / "pairs.count_l4_core_v2.jsonl",
        "model_inputs": output_dir / "model_inputs.count_l4_core_v2.jsonl",
        "gold": output_dir / "gold.count_l4_core_v2.jsonl",
        "rejects": output_dir / "rejects.count_l4_core_v2.jsonl",
        "report": output_dir / "verification_report.count_l4_core_v2.json",
    }
    inputs = [branch_index, post_oracles, prestates, pairs]
    if dry_run:
        return {
            "status": "PLANNED", "action": "verify",
            "inputs": [str(path) for path in inputs], "media_root": str(media_root),
            "outputs": {key: str(path) for key, path in outputs.items()},
        }
    missing = [str(path) for path in inputs if not path.is_file()]
    if not media_root.is_dir():
        missing.append(str(media_root))
    if missing:
        return {"status": "BLOCKED_SOURCE", "action": "verify", "missing_inputs": missing}

    branches = {_key(row): row for row in _read_jsonl(branch_index)}
    oracles = {_key(row): row for row in _read_jsonl(post_oracles)}
    prestate_rows = {_key(row): row for row in _read_jsonl(prestates)}
    pair_rows = _read_jsonl(pairs)
    accepted: list[dict[str, Any]] = []
    model_inputs: list[dict[str, Any]] = []
    gold: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    media_hashes: dict[str, str] = {}

    for pair in pair_rows:
        source = pair.get("source") or {}
        current_key = (
            str(source.get("scene_id")), str(source.get("change_id")),
            str(source.get("question_id")),
        )
        errors: list[str] = []
        branch = branches.get(current_key)
        oracle = oracles.get(current_key)
        prestate = prestate_rows.get(current_key)
        if branch is None:
            errors.append("SOURCE_BRANCH_MISSING")
        if oracle is None:
            errors.append("POST_ORACLE_MISSING")
        if prestate is None:
            errors.append("PRESTATE_MISSING")
        if branch is not None and oracle is not None:
            reconstructed, reject_code = normalize_post_qa(branch)
            if reject_code is not None or reconstructed != oracle:
                errors.append("SOURCE_QA_RECONSTRUCTION_FAIL")
            if source.get("post_oracle_id") != oracle.get("oracle_id"):
                errors.append("POST_ORACLE_ID_MISMATCH")
        if prestate is not None:
            predicate = pair.get("supported_claim", {}).get("graph", {}).get("predicate")
            if predicate == "COUNT":
                independent = verify_count_pair_accessibly(
                    pre_state_subgraph=prestate["pre_state_subgraph"],
                    accessible_transition=prestate["accessible_transition"],
                    supported_claim=pair["supported_claim"]["graph"],
                    contradictory_claim=pair["contradictory_claim"]["graph"],
                    necessary_pre_fact_ids=list(prestate["necessary_pre_fact_ids"]),
                )
            elif predicate == "EXISTS_IN_WORLD" and pair.get("task", {}).get("strength_slice") == "L4_CALIBRATION":
                independent = verify_existence_pair_accessibly(
                    accessible_transition=prestate.get("existence_transition") or {},
                    supported_claim=pair["supported_claim"]["graph"],
                    contradictory_claim=pair["contradictory_claim"]["graph"],
                )
            else:
                independent = {"status": "FAIL"}
            if independent["status"] != "PASS":
                errors.append("REJECT_VERIFIER_DISAGREEMENT")
        errors.extend(validate_certificate_separation(pair.get("certificate") or {}))
        if pair.get("validation", {}).get("final_status") != "AUTO_ACCEPTED":
            errors.append("PAIR_NOT_AUTO_ACCEPTED")

        scene_id = current_key[0]
        media: dict[str, Any] = {}
        for role in MEDIA_ROLES:
            relative = f"{role}/{scene_id}.png"
            path = media_root / relative
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"REJECT_MEDIA_NOT_MATERIALIZABLE:{role}")
                continue
            digest = media_hashes.setdefault(str(path), sha256_file(path))
            media[role] = {"path": relative, "sha256": digest}

        if errors:
            rejects.append({"pair_id": pair.get("pair_id"), "source_key": current_key, "errors": sorted(set(errors))})
            continue
        accepted.append(pair)
        variants = [
            (pair["supported_claim"]["text"], "SUPPORTED"),
            (pair["contradictory_claim"]["text"], "CONTRADICTORY"),
        ]
        if hashlib.sha256(str(pair["pair_id"]).encode("utf-8")).digest()[0] & 1:
            variants.reverse()
        for index, (claim_text, label) in enumerate(variants):
            example_id = f"{pair['pair_id']}:candidate_{index}"
            model_input = {
                "example_id": example_id,
                "pair_id": pair["pair_id"],
                "scene_id": scene_id,
                "branch_id": source["branch_id"],
                "level": "L4",
                "context_change": branch["context_change_raw"],
                "media": media,
                "claim": claim_text,
            }
            leaked = _forbidden_keys(model_input)
            if leaked:
                raise ValueError(f"Model-input leakage for {example_id}: {sorted(leaked)}")
            model_inputs.append(model_input)
            gold.append({"example_id": example_id, "pair_id": pair["pair_id"], "label": label})

    p0_minimum = 100
    core_count = sum(pair.get("task", {}).get("strength_slice") == "L4_CORE" for pair in accepted)
    calibration_count = sum(pair.get("task", {}).get("strength_slice") == "L4_CALIBRATION" for pair in accepted)
    calibration_ratio_pass = calibration_count * 100 <= len(accepted) * 15
    operator_counts = Counter(str(pair.get("task", {}).get("operator_id")) for pair in accepted)
    report = {
        "schema_version": "hypo3d_l4_final_verification_v2",
        "status": verification_status(
            accepted_count=len(accepted),
            calibration_ratio_pass=calibration_ratio_pass,
            p0_minimum=p0_minimum,
        ),
        "input_pair_count": len(pair_rows),
        "accepted_pair_count": len(accepted),
        "core_pair_count": core_count,
        "calibration_pair_count": calibration_count,
        "calibration_ratio": calibration_count / len(accepted) if accepted else 0.0,
        "calibration_ratio_limit": 0.15,
        "calibration_ratio_gate": "PASS" if calibration_ratio_pass else "FAIL",
        "operator_counts": dict(sorted(operator_counts.items())),
        "operator_family_count": len(operator_counts),
        "rejected_pair_count": len(rejects),
        "model_input_count": len(model_inputs),
        "gold_count": len(gold),
        "media_file_count": len(media_hashes),
        "p0_minimum_pairs": p0_minimum,
        "p0_shortfall_pairs": max(0, p0_minimum - len(accepted)),
        "model_input_truth_boundary": "NO_SOURCE_ANSWER_ORACLE_PROOF_OPERATOR_OR_GOLD_LABEL",
        "input_hashes": {str(path): sha256_file(path) for path in inputs},
    }
    write_versioned(outputs["pairs"], jsonl_bytes(accepted), resume=resume)
    write_versioned(outputs["model_inputs"], jsonl_bytes(model_inputs), resume=resume)
    write_versioned(outputs["gold"], jsonl_bytes(gold), resume=resume)
    write_versioned(outputs["rejects"], jsonl_bytes(rejects), resume=resume)
    write_versioned(
        outputs["report"],
        (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        resume=resume,
    )
    return {
        **report, "action": "verify",
        "outputs": {key: str(path) for key, path in outputs.items()},
        "output_hashes": {str(path): sha256_file(path) for path in outputs.values()},
    }
