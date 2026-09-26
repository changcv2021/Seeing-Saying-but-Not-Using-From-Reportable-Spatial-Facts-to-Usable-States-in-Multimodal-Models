from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AdapterResult:
    source_dataset: str
    source_item_id: str
    source_record_hash: str
    source_task: str
    global_world_id: str | None
    adapter_version: str
    status: str
    facts: list[dict[str, Any]] = field(default_factory=list)
    answer_semantics: Any = None
    source_answer: Any = None
    reconstructed_answer: Any = None
    reconstruction_pass: bool = False
    reject_codes: list[str] = field(default_factory=list)
    blocking_reject_codes: list[str] = field(default_factory=list)
    media_locator: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def record_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return normalized.strip("_") or "unnamed"


def option_map(options: list[str] | dict[str, str] | None) -> dict[str, str]:
    if isinstance(options, dict):
        return {str(key).upper(): str(value).strip() for key, value in options.items() if value is not None}
    result: dict[str, str] = {}
    for value in options or []:
        match = re.fullmatch(r"\s*([A-Z])\.\s*(.*?)\s*", str(value), flags=re.DOTALL)
        if not match:
            raise ValueError(f"Malformed option: {value!r}")
        result[match.group(1)] = match.group(2)
    return result


def fact(
    *, subject: str, predicate: str, object_: str | None, value: Any, world_id: str,
    reference_frame: str, scope: str, source_item_id: str, source_record_hash: str,
    source_dataset: str, source_field_paths: list[str], context_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = {
        "world_id": world_id, "reference_frame": reference_frame, "state_id": "observed",
        "branch_id": "actual", "scope": scope,
    }
    context.update(context_extra or {})
    return {
        "subject": subject, "predicate": predicate, "object": object_, "value": value,
        "polarity": "positive", "context": context,
        "provenance": {
            "origin_type": "QA_DIRECT", "source_dataset": source_dataset,
            "source_item_ids": [source_item_id], "source_field_paths": source_field_paths,
            "source_record_hash": source_record_hash,
        },
    }

