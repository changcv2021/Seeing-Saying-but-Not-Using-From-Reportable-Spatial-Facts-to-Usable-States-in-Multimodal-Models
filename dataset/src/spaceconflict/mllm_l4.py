"""Shared blind-input, parsing, and metric helpers for L4 MLLM evaluation."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable


LABELS = ("SUPPORTED", "CONTRADICTORY", "UNKNOWN")
SYSTEM_PROMPT = """You are evaluating a spatial claim using only the supplied visual evidence and, when present, the stated hypothetical intervention. Classify the claim as exactly one of SUPPORTED, CONTRADICTORY, or UNKNOWN. SUPPORTED means the accessible evidence entails the claim. CONTRADICTORY means it explicitly refutes the claim. UNKNOWN means both the claim and its negation remain possible from the accessible evidence. Missing information is not negative evidence. Return JSON only."""


def user_prompt(sample: dict[str, Any]) -> str:
    intervention = str(sample.get("intervention_text") or "No intervention was supplied.")
    claim = str(sample.get("claim_text") or "")
    evidence_note = (
        f"Accessible visual evidence: {len(sample.get('media') or [])} image(s) supplied above."
        if sample.get("media") else
        "Accessible visual evidence: no image was supplied. Treat missing evidence as missing, not as negative evidence."
    )
    return (
        f"Hypothetical intervention:\n{intervention}\n\n"
        f"Spatial claim:\n{claim}\n\n"
        f"{evidence_note}\n\n"
        "Return exactly one JSON object with this schema:\n"
        '{"label":"SUPPORTED|CONTRADICTORY|UNKNOWN","confidence":0.0,"reason":"brief explanation"}'
    )


def parse_model_response(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    parsed: Any = None
    strict_json_valid = False
    if stripped:
        try:
            parsed = json.loads(stripped)
            strict_json_valid = isinstance(parsed, dict)
        except json.JSONDecodeError:
            parsed = None

    label = None
    confidence = None
    reason = None
    if isinstance(parsed, dict):
        raw_label = parsed.get("label")
        if isinstance(raw_label, str) and raw_label.strip().upper() in LABELS:
            label = raw_label.strip().upper()
        raw_confidence = parsed.get("confidence")
        if isinstance(raw_confidence, (int, float)) and not isinstance(raw_confidence, bool):
            if 0.0 <= float(raw_confidence) <= 1.0:
                confidence = float(raw_confidence)
        if isinstance(parsed.get("reason"), str):
            reason = parsed["reason"].strip()

    recovered = None
    matches = set(re.findall(r"\b(?:SUPPORTED|CONTRADICTORY|UNKNOWN)\b", stripped.upper()))
    if len(matches) == 1:
        recovered = next(iter(matches))
    return {
        "strict_json_valid": strict_json_valid,
        "schema_valid": strict_json_valid and label is not None,
        "label": label,
        "confidence": confidence,
        "reason": reason,
        "recovered_label_diagnostic_only": recovered,
    }


def classification_metrics(
    gold: list[str], predictions: list[str | None], labels: Iterable[str] = LABELS,
) -> dict[str, Any]:
    label_list = list(labels)
    if len(gold) != len(predictions):
        raise ValueError("gold and predictions have different lengths")
    per_label: dict[str, dict[str, float | int]] = {}
    recalls: list[float] = []
    f1s: list[float] = []
    correct = 0
    for expected, predicted in zip(gold, predictions, strict=True):
        correct += int(expected == predicted)
    for label in label_list:
        tp = sum(expected == label and predicted == label for expected, predicted in zip(gold, predictions, strict=True))
        fp = sum(expected != label and predicted == label for expected, predicted in zip(gold, predictions, strict=True))
        fn = sum(expected == label and predicted != label for expected, predicted in zip(gold, predictions, strict=True))
        support = sum(expected == label for expected in gold)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {
            "support": support, "tp": tp, "fp": fp, "fn": fn,
            "precision": precision, "recall": recall, "f1": f1,
        }
        if support:
            recalls.append(recall)
            f1s.append(f1)
    return {
        "n": len(gold),
        "accuracy": correct / len(gold) if gold else None,
        "balanced_accuracy": sum(recalls) / len(recalls) if recalls else None,
        "macro_f1": sum(f1s) / len(f1s) if f1s else None,
        "per_label": per_label,
    }

