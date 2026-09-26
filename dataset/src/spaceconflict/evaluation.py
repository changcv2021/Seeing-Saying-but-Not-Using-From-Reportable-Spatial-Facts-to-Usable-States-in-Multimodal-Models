from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from .hashing import sha256_file
from .registry import ROOT


LABELS = ("SUPPORTED", "CONTRADICTORY", "UNKNOWN")
EVALUATOR_VERSION = "evaluation_v1"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"INVALID_JSON:{path}:{line_number}:{exc.msg}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSONL_ROW_NOT_OBJECT:{path}:{line_number}")
            rows.append(value)
    return rows


def _safe_project_path(relative: str, root: Path) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"PATH_ESCAPES_PROJECT_ROOT:{relative}") from exc
    return path


def _ratio(numerator: int | float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _mean(values: Iterable[float]) -> float | None:
    materialized = list(values)
    return sum(materialized) / len(materialized) if materialized else None


def _classification(gold: list[str], predicted: list[str]) -> dict[str, Any]:
    per_class: dict[str, dict[str, Any]] = {}
    for label in LABELS:
        tp = sum(g == label and p == label for g, p in zip(gold, predicted))
        fp = sum(g != label and p == label for g, p in zip(gold, predicted))
        fn = sum(g == label and p != label for g, p in zip(gold, predicted))
        support = sum(g == label for g in gold)
        precision = _ratio(tp, tp + fp)
        recall = _ratio(tp, tp + fn)
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall
            else 0.0 if support else None
        )
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }
    present = [row for row in per_class.values() if row["support"]]
    return {
        "claim_accuracy": _ratio(sum(g == p for g, p in zip(gold, predicted)), len(gold)),
        "balanced_accuracy": _mean(row["recall"] for row in present),
        "macro_f1": _mean(row["f1"] for row in present),
        "per_class": per_class,
        "sample_count": len(gold),
    }


def _set_f1(gold: Iterable[str], predicted: Iterable[str]) -> dict[str, float]:
    gold_set, predicted_set = set(gold), set(predicted)
    if not gold_set and not predicted_set:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "exact": 1.0}
    intersection = len(gold_set & predicted_set)
    precision = intersection / len(predicted_set) if predicted_set else 0.0
    recall = intersection / len(gold_set) if gold_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "exact": float(gold_set == predicted_set),
    }


def _macro_set_metric(rows: list[dict[str, float]]) -> dict[str, Any]:
    return {
        "precision": _mean(row["precision"] for row in rows),
        "recall": _mean(row["recall"] for row in rows),
        "f1": _mean(row["f1"] for row in rows),
        "exact_match": _mean(row["exact"] for row in rows),
        "sample_count": len(rows),
    }


def _group_report(
    sample_ids: list[str],
    gold: dict[str, dict[str, Any]],
    predicted: dict[str, dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    buckets: dict[str, list[str]] = defaultdict(list)
    for sample_id in sample_ids:
        value = gold[sample_id].get(field)
        if value is not None:
            buckets[str(value)].append(sample_id)
    groups: dict[str, Any] = {}
    for value, ids in sorted(buckets.items()):
        correct = sum(predicted[item]["label"] == gold[item]["label"] for item in ids)
        groups[value] = {"accuracy": correct / len(ids), "sample_count": len(ids)}
    return {
        "macro_accuracy": _mean(row["accuracy"] for row in groups.values()),
        "groups": groups,
        "group_count": len(groups),
        "basis": "claim_label_accuracy; UNKNOWN excluded where grouping metadata is undefined",
    }


def _calibration(gold: list[str], predictions: list[dict[str, Any]], bins: int = 10) -> dict[str, Any]:
    confidences = [float(row["confidence"]) for row in predictions]
    correct = [int(g == row["label"]) for g, row in zip(gold, predictions)]
    brier = _mean((confidence - outcome) ** 2 for confidence, outcome in zip(confidences, correct))
    ece = 0.0
    bin_rows = []
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        selected = [
            position for position, confidence in enumerate(confidences)
            if lower <= confidence < upper or (index == bins - 1 and confidence == 1.0)
        ]
        if not selected:
            continue
        accuracy = sum(correct[position] for position in selected) / len(selected)
        confidence = sum(confidences[position] for position in selected) / len(selected)
        ece += len(selected) / len(gold) * abs(accuracy - confidence)
        bin_rows.append({
            "lower": lower,
            "upper": upper,
            "count": len(selected),
            "accuracy": accuracy,
            "mean_confidence": confidence,
        })
    return {
        "ece": ece,
        "brier": brier,
        "bins": bin_rows,
        "definition": "top-label calibration: confidence is the probability assigned to the predicted label",
    }


def _unknown_reason(gold: dict[str, dict[str, Any]], predicted: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ids = [sample_id for sample_id, row in gold.items() if row["label"] == "UNKNOWN"]
    reasons = sorted({str(gold[sample_id]["unknown_reason"]) for sample_id in ids})
    per_reason: dict[str, Any] = {}
    predicted_reasons = {
        sample_id: (
            predicted[sample_id].get("unknown_reason")
            if predicted[sample_id]["label"] == "UNKNOWN"
            else "__NOT_PREDICTED_UNKNOWN__"
        )
        for sample_id in ids
    }
    for reason in reasons:
        tp = sum(gold[item]["unknown_reason"] == reason and predicted_reasons[item] == reason for item in ids)
        fp = sum(gold[item]["unknown_reason"] != reason and predicted_reasons[item] == reason for item in ids)
        fn = sum(gold[item]["unknown_reason"] == reason and predicted_reasons[item] != reason for item in ids)
        precision = _ratio(tp, tp + fp)
        recall = _ratio(tp, tp + fn)
        f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else 0.0
        per_reason[reason] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    return {
        "macro_f1": _mean(row["f1"] for row in per_reason.values()),
        "per_reason": per_reason,
        "sample_count": len(ids),
    }


def _load_supporting_artifacts(
    manifest: dict[str, Any], root: Path
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    sampled: dict[str, dict[str, Any]] = {}
    unknown: dict[str, dict[str, Any]] = {}
    for relative in manifest.get("input_hashes", {}):
        path = _safe_project_path(relative, root)
        if not path.exists() or path.suffix != ".jsonl":
            continue
        if relative.startswith("sampled/pairs."):
            sampled = {row["pair_id"]: row for row in _read_jsonl(path)}
        elif relative.startswith("candidates/unknown/claims."):
            for row in _read_jsonl(path):
                unknown_id = row["unknown_id"]
                if unknown_id in unknown:
                    raise ValueError(f"DUPLICATE_UNKNOWN_SOURCE_ID:{unknown_id}")
                unknown[unknown_id] = row
    return sampled, unknown


def _build_gold(release_dir: Path, root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    required = ["manifest.json", "claims.jsonl", "pairs.jsonl", "unknown_challenge.jsonl"]
    missing = [name for name in required if not (release_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"RELEASE_FILES_MISSING:{','.join(missing)}")
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    claims = _read_jsonl(release_dir / "claims.jsonl")
    pairs = _read_jsonl(release_dir / "pairs.jsonl")
    unknown_claims = _read_jsonl(release_dir / "unknown_challenge.jsonl")
    sampled, unknown_source = _load_supporting_artifacts(manifest, root)
    pair_by_id = {row["pair_id"]: row for row in pairs}
    gold: dict[str, dict[str, Any]] = {}
    pair_aux: dict[str, Any] = {}

    for pair_id, pair in pair_by_id.items():
        sampled_row = sampled.get(pair_id, {})
        certificate: dict[str, Any] = {}
        evidence_graph: dict[str, Any] = {}
        certificate_path = sampled_row.get("certificate_path")
        evidence_path = sampled_row.get("evidence_subgraph_path")
        if certificate_path:
            path = _safe_project_path(certificate_path, root)
            if path.is_file():
                certificate = json.loads(path.read_text(encoding="utf-8"))
        if evidence_path:
            path = _safe_project_path(evidence_path, root)
            if path.is_file():
                evidence_graph = json.loads(path.read_text(encoding="utf-8"))
        pair_aux[pair_id] = {
            "certificate": certificate,
            "evidence_graph": evidence_graph,
            "sampled": sampled_row,
        }

    for claim in claims:
        sample_id, pair_id = claim["sample_id"], claim["pair_id"]
        if sample_id in gold:
            raise ValueError(f"DUPLICATE_GOLD_SAMPLE_ID:{sample_id}")
        pair = pair_by_id.get(pair_id)
        if pair is None:
            raise ValueError(f"CLAIM_REFERENCES_UNKNOWN_PAIR:{sample_id}:{pair_id}")
        aux = pair_aux[pair_id]
        sampled_row = aux["sampled"]
        label = claim["label"]
        if label == "SUPPORTED":
            evidence_ids = set(
                sampled_row.get("independent_verifier", {}).get("supported", {}).get("evidence_fact_ids", [])
                or aux["evidence_graph"].get("supported_fact_ids", [])
            )
            conflict_slots: set[str] = set()
            correction = None
        else:
            evidence_ids = set(aux["certificate"].get("evidence_fact_ids", []))
            conflict_slots = set(aux["certificate"].get("conflict_slots", []))
            correction = pair["supported_claim"]
        all_fact_ids = {fact.get("fact_id") for fact in aux["evidence_graph"].get("facts", []) if fact.get("fact_id")}
        allowed_rules = {
            node["id"] for node in aux["certificate"].get("proof_nodes", [])
            if node.get("type") == "RULE"
        }
        task = pair.get("task", {})
        source = pair.get("source", {})
        gold[sample_id] = {
            "sample_id": sample_id,
            "pair_id": pair_id,
            "label": label,
            "level": task.get("level") or sampled_row.get("level"),
            "track": task.get("primary_diagnostic_tag") or sampled_row.get("primary_track"),
            "source": source.get("source_dataset") or sampled_row.get("source_dataset"),
            "modality": pair.get("media", {}).get("media_type"),
            "operator": task.get("operator_id") or sampled_row.get("operator_id"),
            "conflict_slots": conflict_slots,
            "evidence_ids": evidence_ids,
            "allowed_fact_ids": all_fact_ids,
            "required_rules": allowed_rules if label == "CONTRADICTORY" else set(),
            "correction": correction,
            "unknown_reason": None,
        }

    for claim in unknown_claims:
        sample_id = claim["sample_id"]
        if sample_id in gold:
            raise ValueError(f"DUPLICATE_GOLD_SAMPLE_ID:{sample_id}")
        source = unknown_source.get(sample_id)
        if source is None:
            raise ValueError(f"UNKNOWN_SOURCE_ROW_MISSING:{sample_id}")
        certificate: dict[str, Any] = {}
        certificate_path = source.get("certificate_path")
        if certificate_path:
            path = _safe_project_path(certificate_path, root)
            if path.is_file():
                certificate = json.loads(path.read_text(encoding="utf-8"))
        evidence_ids = set(certificate.get("available_evidence_ids", []))
        if not evidence_ids:
            evidence_ids = {
                str(item["role"]) for item in claim.get("media", {}).get("source_references", [])
                if item.get("role")
            }
        unknown_reason = source.get("unknown_reason") or certificate.get("unknown_reason")
        if not isinstance(unknown_reason, str) or not unknown_reason:
            raise ValueError(f"UNKNOWN_REASON_MISSING:{sample_id}")
        gold[sample_id] = {
            "sample_id": sample_id,
            "pair_id": claim.get("pair_id"),
            "label": "UNKNOWN",
            "level": None,
            "track": None,
            "source": source.get("source_dataset"),
            "modality": claim.get("media", {}).get("media_type"),
            "operator": None,
            "conflict_slots": set(),
            "evidence_ids": evidence_ids,
            "allowed_fact_ids": set(),
            "required_rules": set(),
            "correction": None,
            "unknown_reason": unknown_reason,
        }
    expected = manifest.get("claim_count", len(claims)) + manifest.get("unknown_claim_count", len(unknown_claims))
    if len(gold) != expected:
        raise ValueError(f"RELEASE_COUNT_MISMATCH:expected={expected}:loaded={len(gold)}")
    return gold, {"manifest": manifest, "pairs": pairs, "pair_aux": pair_aux}


def _validate_predictions(path: Path, gold_ids: set[str], root: Path) -> dict[str, dict[str, Any]]:
    schema = json.loads((root / "schemas/prediction.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    predictions: dict[str, dict[str, Any]] = {}
    for line_number, row in enumerate(_read_jsonl(path), 1):
        errors = sorted(validator.iter_errors(row), key=lambda error: list(error.absolute_path))
        if errors:
            location = ".".join(str(part) for part in errors[0].absolute_path) or "$"
            raise ValueError(f"PREDICTION_SCHEMA_INVALID:{line_number}:{location}:{errors[0].message}")
        sample_id = row["sample_id"]
        if sample_id in predictions:
            raise ValueError(f"DUPLICATE_PREDICTION_SAMPLE_ID:{sample_id}")
        predictions[sample_id] = row
    missing, extra = sorted(gold_ids - predictions.keys()), sorted(predictions.keys() - gold_ids)
    if missing:
        raise ValueError(f"MISSING_PREDICTIONS:{len(missing)}:{','.join(missing[:5])}")
    if extra:
        raise ValueError(f"UNKNOWN_PREDICTION_IDS:{len(extra)}:{','.join(extra[:5])}")
    return predictions


def _prediction_evidence(row: dict[str, Any]) -> set[str]:
    return {
        str(item.get("fact_id") or item["media_ref"])
        for item in row["evidence"]
    }


def _premises(row: dict[str, Any]) -> tuple[set[str], set[str]]:
    facts: set[str] = set()
    rules: set[str] = set()
    for step in row["justification_steps"]:
        facts.update(step.get("premise_fact_ids", []))
        if step.get("rule_id"):
            rules.add(step["rule_id"])
    return facts, rules


def evaluate_predictions(
    predictions_path: Path,
    release_dir: Path,
    *,
    output_path: Path | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    predictions_path = predictions_path.resolve()
    release_dir = release_dir.resolve()
    if not predictions_path.is_file():
        raise FileNotFoundError(f"PREDICTIONS_NOT_FOUND:{predictions_path}")
    gold, release = _build_gold(release_dir, root)
    predictions = _validate_predictions(predictions_path, set(gold), root)
    sample_ids = sorted(gold)
    gold_labels = [gold[item]["label"] for item in sample_ids]
    prediction_rows = [predictions[item] for item in sample_ids]
    predicted_labels = [row["label"] for row in prediction_rows]
    classification = _classification(gold_labels, predicted_labels)

    pair_members: dict[str, dict[str, str]] = defaultdict(dict)
    for sample_id in sample_ids:
        if gold[sample_id]["label"] in {"SUPPORTED", "CONTRADICTORY"}:
            pair_members[gold[sample_id]["pair_id"]][gold[sample_id]["label"]] = sample_id
    pair_correct: dict[str, bool] = {}
    for pair_id, members in pair_members.items():
        if set(members) != {"SUPPORTED", "CONTRADICTORY"}:
            raise ValueError(f"INCOMPLETE_GOLD_PAIR:{pair_id}")
        pair_correct[pair_id] = all(predictions[item]["label"] == gold[item]["label"] for item in members.values())

    grouped = {
        field: _group_report(sample_ids, gold, predictions, field)
        for field in ("level", "track", "source", "modality", "operator")
    }
    worst_candidates = [
        {"dimension": field, "group": name, **values}
        for field, report in grouped.items()
        for name, values in report["groups"].items()
    ]
    worst_group = min(worst_candidates, key=lambda row: (row["accuracy"], row["dimension"], row["group"])) if worst_candidates else None

    contradictory_ids = [item for item in sample_ids if gold[item]["label"] == "CONTRADICTORY"]
    conflict_rows = [
        _set_f1(gold[item]["conflict_slots"], predictions[item]["conflict_location"]["slots"])
        for item in contradictory_ids
    ]
    evidence_rows = [
        _set_f1(gold[item]["evidence_ids"], _prediction_evidence(predictions[item]))
        for item in sample_ids
    ]
    correction_rows = [
        _set_f1(
            gold[item]["conflict_slots"],
            predictions[item]["correction"]["changed_slots"] if predictions[item]["correction"] else [],
        )
        for item in contradictory_ids
    ]

    correction_valid: dict[str, bool] = {}
    proof_executable: dict[str, bool] = {}
    evidence_sufficient: dict[str, bool] = {}
    no_unsupported: dict[str, bool] = {}
    total_declared_premises = unsupported_premises = 0
    total_declared_rules = unsupported_rules = 0
    contradiction_with_structured_premises = 0
    for sample_id in sample_ids:
        prediction, target = predictions[sample_id], gold[sample_id]
        predicted_evidence = _prediction_evidence(prediction)
        evidence_sufficient[sample_id] = target["evidence_ids"].issubset(predicted_evidence)
        premise_facts, premise_rules = _premises(prediction)
        bad_facts = premise_facts - target["allowed_fact_ids"]
        bad_rules = premise_rules - target["required_rules"] if target["label"] == "CONTRADICTORY" else premise_rules
        total_declared_premises += len(premise_facts)
        unsupported_premises += len(bad_facts)
        total_declared_rules += len(premise_rules)
        unsupported_rules += len(bad_rules)
        no_unsupported[sample_id] = not bad_facts and not bad_rules
        if target["label"] == "CONTRADICTORY":
            if premise_facts:
                contradiction_with_structured_premises += 1
            proof_executable[sample_id] = (
                target["evidence_ids"].issubset(premise_facts)
                and target["required_rules"].issubset(premise_rules)
                and no_unsupported[sample_id]
            )
            correction = prediction["correction"]
            expected = target["correction"]
            correction_valid[sample_id] = bool(
                correction
                and correction["changed_slots"]
                and set(correction["changed_slots"]) == target["conflict_slots"]
                and correction["normalized"] == expected["normalized"]
                and correction["text"] == expected["natural_text"]
            )

    proof_pair_correct: dict[str, bool] = {}
    proof_components = defaultdict(int)
    for pair_id, members in pair_members.items():
        positive, negative = members["SUPPORTED"], members["CONTRADICTORY"]
        components = {
            "labels_correct": pair_correct[pair_id],
            "conflict_slots_correct": set(predictions[negative]["conflict_location"]["slots"]) == gold[negative]["conflict_slots"],
            "evidence_sufficient": evidence_sufficient[positive] and evidence_sufficient[negative],
            "proof_executable": proof_executable[negative],
            "no_unsupported_premise": no_unsupported[positive] and no_unsupported[negative],
            "correction_valid": correction_valid[negative],
        }
        for name, passed in components.items():
            proof_components[name] += int(passed)
        proof_pair_correct[pair_id] = all(components.values())

    conditional_pairs = []
    conditional_inconsistent = 0
    for pair_id, members in pair_members.items():
        values = [predictions[item].get("source_qa_correct") for item in members.values()]
        if all(isinstance(value, bool) for value in values):
            if len(set(values)) != 1:
                conditional_inconsistent += 1
            elif values[0]:
                conditional_pairs.append(pair_id)
    conditional = (
        {
            "status": "AVAILABLE",
            "value": _mean(float(pair_correct[item]) for item in conditional_pairs),
            "eligible_pair_count": len(conditional_pairs),
            "inconsistent_pair_count": conditional_inconsistent,
        }
        if conditional_pairs
        else {
            "status": "NOT_AVAILABLE",
            "value": None,
            "eligible_pair_count": 0,
            "inconsistent_pair_count": conditional_inconsistent,
            "reason": "source_qa_correct was not supplied consistently for any source-QA-correct pair",
        }
    )

    paraphrase_groups: dict[str, list[str]] = defaultdict(list)
    for sample_id, prediction in predictions.items():
        if prediction.get("paraphrase_group_id"):
            paraphrase_groups[prediction["paraphrase_group_id"]].append(sample_id)
    usable_paraphrase_groups = {key: value for key, value in paraphrase_groups.items() if len(value) > 1}
    paraphrase = (
        {
            "status": "AVAILABLE",
            "value": _mean(float(len({predictions[item]["label"] for item in ids}) == 1) for ids in usable_paraphrase_groups.values()),
            "group_count": len(usable_paraphrase_groups),
            "basis": "externally supplied paraphrase_group_id",
        }
        if usable_paraphrase_groups
        else {
            "status": "NOT_AVAILABLE",
            "value": None,
            "group_count": 0,
            "reason": "release contains one selected realization per claim and no multi-item paraphrase groups were supplied",
        }
    )

    unknown_metrics = classification["per_class"]["UNKNOWN"]
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "evaluator_version": EVALUATOR_VERSION,
        "status": "PASS",
        "release": {
            "path": str(release_dir),
            "export_version": release["manifest"].get("export_version"),
            "pair_count": len(pair_members),
            "sample_count": len(sample_ids),
        },
        "inputs": {
            "predictions": str(predictions_path),
            "predictions_sha256": sha256_file(predictions_path),
            "release_manifest_sha256": sha256_file(release_dir / "manifest.json"),
        },
        "metrics": {
            **classification,
            "pair_accuracy": _mean(float(value) for value in pair_correct.values()),
            "pair_count": len(pair_correct),
            "level_macro": grouped["level"],
            "track_macro": grouped["track"],
            "source_macro": grouped["source"],
            "modality_macro": grouped["modality"],
            "operator_macro": grouped["operator"],
            "worst_group_accuracy": worst_group,
            "conflict_slot": _macro_set_metric(conflict_rows),
            "evidence_grounding": _macro_set_metric(evidence_rows),
            "structured_correction_slot": _macro_set_metric(correction_rows),
            "unknown": {
                "precision": unknown_metrics["precision"],
                "recall": unknown_metrics["recall"],
                "f1": unknown_metrics["f1"],
                "support": unknown_metrics["support"],
            },
            "unknown_reason": _unknown_reason(gold, predictions),
            "conditional_contradiction_detection": conditional,
            "calibration": _calibration(gold_labels, prediction_rows),
            "paraphrase_consistency": paraphrase,
            "unsupported_premise": {
                "rate": _ratio(unsupported_premises, total_declared_premises),
                "unsupported_count": unsupported_premises,
                "declared_count": total_declared_premises,
                "structured_premise_coverage": _ratio(contradiction_with_structured_premises, len(contradictory_ids)),
                "unsupported_rule_rate": _ratio(unsupported_rules, total_declared_rules),
                "unsupported_rule_count": unsupported_rules,
                "declared_rule_count": total_declared_rules,
                "note": "rate is null when no structured premise/rule IDs were declared",
            },
            "proof_carrying_pair_accuracy": _mean(float(value) for value in proof_pair_correct.values()),
            "proof_carrying_pair_count": sum(proof_pair_correct.values()),
            "proof_carrying_components": {
                name: count / len(pair_members) for name, count in sorted(proof_components.items())
            },
        },
        "metric_policy": {
            "set_metrics": "per-sample set precision/recall/F1, then macro-average",
            "empty_set": "gold and prediction both empty scores 1",
            "pair_accuracy": "both binary members must have the correct label",
            "worst_group": "minimum claim accuracy across observed Level/Track/Source/Modality/Operator groups",
            "proof_carrying_pair": "labels + exact slots + sufficient evidence + executable structured proof + no unsupported IDs + exact structured correction",
        },
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
