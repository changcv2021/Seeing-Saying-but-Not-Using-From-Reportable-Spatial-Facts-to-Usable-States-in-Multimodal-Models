from __future__ import annotations

from spaceconflict.adapters.hypo3d import adapt


def _row(question: str, answer: str, question_type: str = "Direction") -> dict:
    return {
        "base_scene_id": "scene0000_00",
        "branch_index": 3,
        "context_change": "The desk has been moved to the right of the refrigerator.",
        "change_type": "Object Movement Change",
        "question": question,
        "question_type": question_type,
        "question_id": "42",
        "answer": answer,
    }


def test_hypo3d_exact_count_is_branch_scoped_and_reconstructed() -> None:
    result = adapt(_row("How many tables remain in the room now?", "3", "Semantic"), 0)
    assert result.status == "WAITING_MEDIA"
    assert result.reconstruction_pass
    assert result.reconstructed_answer == "3"
    assert result.facts[0]["predicate"] == "COUNT"
    assert result.facts[0]["context"]["state_id"] == "post_intervention"
    assert result.facts[0]["context"]["branch_id"] == "branch:3"


def test_hypo3d_composite_direction_is_reconstructed() -> None:
    result = adapt(
        _row("What is the position of the kitchen counter relative to the desk?", "Back left"),
        0,
    )
    assert result.status == "WAITING_MEDIA"
    assert [fact["predicate"] for fact in result.facts] == ["BEHIND", "LEFT_OF"]
    assert result.reconstructed_answer == "Back left"


def test_hypo3d_metric_or_commonsense_question_is_rejected() -> None:
    result = adapt(
        _row("Which object is closest to the refrigerator?", "Chair", "Scale"),
        0,
    )
    assert result.status == "REJECTED"
    assert result.reject_codes == ["METRIC_OR_COMMONSENSE_DEPENDENCY"]


def test_hypo3d_missing_branch_data_is_rejected() -> None:
    row = _row("How many tables remain in the room now?", "3", "Semantic")
    row["context_change"] = None
    result = adapt(row, 0)
    assert result.status == "REJECTED"
    assert result.reject_codes == ["MALFORMED_SOURCE_RECORD"]
