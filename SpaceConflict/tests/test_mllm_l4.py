from __future__ import annotations

from spaceconflict.mllm_l4 import classification_metrics, parse_model_response, user_prompt


def test_strict_json_response() -> None:
    result = parse_model_response('{"label":"UNKNOWN","confidence":0.8,"reason":"missing view"}')
    assert result["strict_json_valid"] is True
    assert result["schema_valid"] is True
    assert result["label"] == "UNKNOWN"


def test_markdown_response_is_not_strict_json() -> None:
    result = parse_model_response('```json\n{"label":"SUPPORTED"}\n```')
    assert result["strict_json_valid"] is False
    assert result["label"] is None
    assert result["recovered_label_diagnostic_only"] == "SUPPORTED"


def test_missing_media_prompt_does_not_treat_absence_as_negative() -> None:
    prompt = user_prompt({"claim_text": "A is left of B.", "intervention_text": "Move A.", "media": []})
    assert "missing, not as negative evidence" in prompt


def test_classification_metrics() -> None:
    report = classification_metrics(
        ["SUPPORTED", "CONTRADICTORY", "UNKNOWN"],
        ["SUPPORTED", "UNKNOWN", "UNKNOWN"],
    )
    assert report["accuracy"] == 2 / 3
    assert report["per_label"]["UNKNOWN"]["recall"] == 1.0

