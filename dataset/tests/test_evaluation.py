from __future__ import annotations

import json

from jsonschema import Draft202012Validator

from spaceconflict.evaluation import _classification, _load_supporting_artifacts, _set_f1
from spaceconflict.registry import ROOT


def test_classification_metrics_are_three_way_and_macro_averaged() -> None:
    report = _classification(
        ["SUPPORTED", "CONTRADICTORY", "UNKNOWN"],
        ["SUPPORTED", "UNKNOWN", "UNKNOWN"],
    )
    assert report["claim_accuracy"] == 2 / 3
    assert report["balanced_accuracy"] == 2 / 3
    assert report["macro_f1"] == (1.0 + 0.0 + 2 / 3) / 3
    assert report["per_class"]["UNKNOWN"]["precision"] == 0.5


def test_set_f1_handles_empty_and_nonempty_sets() -> None:
    assert _set_f1([], []) == {"precision": 1.0, "recall": 1.0, "f1": 1.0, "exact": 1.0}
    assert _set_f1(["a", "b"], ["b", "c"]) == {
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
        "exact": 0.0,
    }


def test_prediction_schema_requires_executable_structure() -> None:
    schema = json.loads((ROOT / "schemas/prediction.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    prediction = {
        "sample_id": "example",
        "label": "CONTRADICTORY",
        "conflict_location": {"slots": ["subject"], "claim_fragments": ["left object"]},
        "evidence": [{
            "media_ref": "view_02",
            "entity_ref": "object_1",
            "observation": "object_1 is right of object_2",
            "fact_id": "fact:1",
        }],
        "justification_steps": [{
            "type": "proof",
            "statement": "The grounded fact conflicts with the claim.",
            "premise_fact_ids": ["fact:1"],
            "rule_id": "rule:INVERSE",
            "conclusion": "contradiction",
        }],
        "correction": {"normalized": {}, "text": "corrected", "changed_slots": ["subject"]},
        "unknown_reason": None,
        "confidence": 0.9,
        "source_qa_correct": True,
    }
    assert list(validator.iter_errors(prediction)) == []
    del prediction["evidence"][0]["media_ref"]
    assert list(validator.iter_errors(prediction))


def test_supporting_artifacts_merge_multiple_unknown_files(tmp_path) -> None:
    first = tmp_path / "candidates/unknown/claims.first.jsonl"
    second = tmp_path / "candidates/unknown/claims.second.jsonl"
    first.parent.mkdir(parents=True)
    first.write_text('{"unknown_id":"u1","unknown_reason":"MISSING_VIEW"}\n', encoding="utf-8")
    second.write_text('{"unknown_id":"u2","unknown_reason":"COUNT_SCOPE_INCOMPLETE"}\n', encoding="utf-8")
    manifest = {"input_hashes": {
        "candidates/unknown/claims.first.jsonl": "sha256:not-used",
        "candidates/unknown/claims.second.jsonl": "sha256:not-used",
    }}
    _, unknown = _load_supporting_artifacts(manifest, tmp_path)
    assert set(unknown) == {"u1", "u2"}
    assert unknown["u1"]["unknown_reason"] == "MISSING_VIEW"
    assert unknown["u2"]["unknown_reason"] == "COUNT_SCOPE_INCOMPLETE"
