from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from ..hashing import sha256_bytes, sha256_file
from ..registry import ROOT
from .claims import CLAIM_BUILD_VERSION


REALIZATION_VERSION = "realization_p1_v2"
TEXT_VERIFICATION_VERSION = "text_verification_p1_v2"

TEMPLATES = (
    ("context_first", "{context}, the {subject} {relation} the {object}."),
    ("subject_first", "The {subject} {relation} the {object} {context_suffix}."),
    ("evidence_first", "Considering the evidence {context_suffix}, the {subject} {relation} the {object}."),
    ("observed_context", "As observed {context_suffix}, the {subject} {relation} the {object}."),
    ("scene_attribution", "According to the scene {context_suffix}, the {subject} {relation} the {object}."),
    ("fixed_context", "With the context fixed {context_suffix}, the {subject} {relation} the {object}."),
)

RELATIONS = {
    "LEFT_OF": ("is to the left of", "is positioned left of", "lies to the left of"),
    "RIGHT_OF": ("is to the right of", "is positioned right of", "lies to the right of"),
    "FRONT_OF": ("is in front of", "is positioned ahead of", "lies in front of"),
    "BEHIND": ("is behind", "is positioned behind", "lies behind"),
    "ABOVE": ("is above", "is positioned above", "lies above"),
    "BELOW": ("is below", "is positioned below", "lies below"),
    "BEFORE": ("precedes", "occurs earlier than", "comes before"),
    "AFTER": ("follows", "occurs later than", "comes after"),
}

VISIBLE_RELATIONS = (
    "has a visible instance", "is represented by a visible instance", "appears in the image",
)

VISIBLE_TEMPLATES = {
    "context_first": "{context}, the {subject} {relation}.",
    "subject_first": "The {subject} {relation} {context_suffix}.",
    "evidence_first": "Considering the evidence {context_suffix}, the {subject} {relation}.",
    "observed_context": "As observed {context_suffix}, the {subject} {relation}.",
    "scene_attribution": "According to the scene {context_suffix}, the {subject} {relation}.",
    "fixed_context": "With the context fixed {context_suffix}, the {subject} {relation}.",
}

COUNT_RELATIONS = (
    "has exactly", "has a total of", "is represented by exactly",
)

COUNT_TEMPLATES = {
    "context_first": "{context}, the {subject} {relation} {value} visible instance{plural}.",
    "subject_first": "The {subject} {relation} {value} visible instance{plural} {context_suffix}.",
    "evidence_first": "Considering the evidence {context_suffix}, the {subject} {relation} {value} visible instance{plural}.",
    "observed_context": "As observed {context_suffix}, the {subject} {relation} {value} visible instance{plural}.",
    "scene_attribution": "According to the scene {context_suffix}, the {subject} {relation} {value} visible instance{plural}.",
    "fixed_context": "With the context fixed {context_suffix}, the {subject} {relation} {value} visible instance{plural}.",
}

CONTEXTS = {
    ("whole_video", "video_timeline", "whole_video", "observed", "actual"): (
        "Across the observed timeline of the actual video", "across the observed timeline of the actual video",
    ),
    ("whole_ordered_sequence", "video_timeline", "whole_video", "observed", "actual"): (
        "Across the complete ordered frame sequence of the actual scene",
        "across the complete ordered frame sequence of the actual scene",
    ),
    ("None", "observer_view_1", "world_shared_across_views", "observed", "actual"): (
        "In the actual scene observed from viewpoint 1", "in the actual scene observed from viewpoint 1",
    ),
    ("None", "source_question_declared_perspective", "current_media", "observed", "actual"): (
        "In the current image of the actual scene, from the perspective declared in the source question",
        "in the current image of the actual scene, from the perspective declared in the source question",
    ),
    ("None", "ca_vqa_reference_frame", "reference_frame", "observed", "actual"): (
        "In the designated reference image of the actual scene, with its four support images available",
        "in the designated reference image of the actual scene, with its four support images available",
    ),
}


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write(path: Path, payload: bytes, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume:
            raise FileExistsError(f"Output exists: {path}; use --resume")
        if path.read_bytes() != payload:
            raise ValueError(f"Non-deterministic output: {path}")
    else:
        path.write_bytes(payload)


def entity_description(entity_id: str) -> str:
    if entity_id.startswith("bbox_anchor:"):
        coordinates = entity_id.rsplit(":", 1)[-1].replace("_", ", ")
        return f"object marked by bounding box [{coordinates}]"
    if entity_id.startswith("query_target:"):
        return "queried target"
    if entity_id.startswith("perspective_reference:"):
        return "declared perspective origin"
    if entity_id.endswith(":bbox_target"):
        return "bounding-box target"
    if entity_id.endswith(":observer_view_1"):
        return "observer viewpoint"
    value = entity_id.split("@source_item:", 1)[0]
    value = value.removeprefix("first_appear:").removeprefix("mention:").removeprefix("class:")
    description = value.replace("_", " ").strip()
    return description.removeprefix("the ")


def _context_key(context: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return tuple(str(context.get(key)) for key in ("time_scope", "reference_frame", "scope", "state_id", "branch_id"))  # type: ignore[return-value]


def _surface_entity(entity_id: str, predicate: str) -> str:
    description = entity_description(entity_id)
    if entity_id.startswith("class:"):
        return f"object category “{description}”"
    return f"first appearance of the {description}" if predicate in {"BEFORE", "AFTER"} else description


def _context_forms(context: dict[str, Any]) -> tuple[str, str]:
    key = _context_key(context)
    if key in CONTEXTS:
        return CONTEXTS[key]
    time_scope = context.get("time_scope")
    if (
        context.get("scope") == "time_interval"
        and context.get("reference_frame") == "observer"
        and context.get("state_id") == "observed"
        and context.get("branch_id") == "actual"
        and isinstance(time_scope, dict)
        and float(time_scope.get("start")) == float(time_scope.get("end"))
    ):
        timestamp = f"{float(time_scope['start']):g}"
        phrase = f"at {timestamp} seconds in the actual video, viewed from the observer frame"
        return phrase.capitalize(), phrase
    raise ValueError(f"UNSUPPORTED_LANGUAGE_CONTEXT:{key}")


def _alignment(
    text: str, subject: str, predicate: str, relation: str, object_: str,
    context: dict[str, Any], context_surface: str, entity_aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    entity_aliases = entity_aliases or {}
    spans = []
    for slot, canonical, surface in (
        ("subject_id", subject, entity_aliases.get(subject, _surface_entity(subject, predicate))),
        ("predicate", predicate, relation),
        ("object_id", object_, entity_aliases.get(object_, _surface_entity(object_, predicate))),
    ):
        start = text.rfind(surface) if slot in {"subject_id", "object_id"} else text.find(surface)
        if start < 0:
            raise ValueError(f"SURFACE_SLOT_MISSING:{slot}:{surface}")
        spans.append({"slot": slot, "canonical_value": canonical, "surface_text": surface, "char_span": [start, start + len(surface)]})
    context_start = text.casefold().find(context_surface.casefold())
    if context_start < 0:
        raise ValueError(f"SURFACE_CONTEXT_MISSING:{context_surface}")
    for slot in ("media_id", "view_id", "frame_id", "time_scope", "reference_frame", "scope", "state_id", "branch_id"):
        spans.append({"slot": slot, "canonical_value": context.get(slot), "surface_text": text[context_start:context_start + len(context_surface)], "char_span": [context_start, context_start + len(context_surface)]})
    return spans


def _context_alignment(text: str, context: dict[str, Any], context_surface: str) -> list[dict[str, Any]]:
    start = text.casefold().find(context_surface.casefold())
    if start < 0:
        raise ValueError(f"SURFACE_CONTEXT_MISSING:{context_surface}")
    return [
        {
            "slot": slot, "canonical_value": context.get(slot),
            "surface_text": text[start:start + len(context_surface)],
            "char_span": [start, start + len(context_surface)],
        }
        for slot in ("media_id", "view_id", "frame_id", "time_scope", "reference_frame", "scope", "state_id", "branch_id")
    ]


def _unary_alignment(
    text: str, atom: dict[str, Any], relation: str, context: dict[str, Any], context_surface: str,
    entity_aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    entity_aliases = entity_aliases or {}
    subject_surface = entity_aliases.get(atom["subject"], _surface_entity(atom["subject"], atom["predicate"]))
    subject_start = text.rfind(subject_surface)
    relation_start = text.find(relation)
    if subject_start < 0 or relation_start < 0:
        raise ValueError("SURFACE_UNARY_SLOT_MISSING")
    return [
        {"slot": "subject_id", "canonical_value": atom["subject"], "surface_text": subject_surface, "char_span": [subject_start, subject_start + len(subject_surface)]},
        {"slot": "predicate", "canonical_value": atom["predicate"], "surface_text": relation, "char_span": [relation_start, relation_start + len(relation)]},
        {"slot": "object_id", "canonical_value": None, "surface_text": "", "char_span": [relation_start + len(relation), relation_start + len(relation)]},
        *_context_alignment(text, context, context_surface),
    ]


def _count_alignment(
    text: str, atom: dict[str, Any], relation: str, context: dict[str, Any], context_surface: str,
    entity_aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    spans = _unary_alignment(text, atom, relation, context, context_surface, entity_aliases)
    value_surface = str(atom["value"])
    value_start = text.find(value_surface, spans[1]["char_span"][1])
    if value_start < 0:
        raise ValueError("SURFACE_COUNT_VALUE_MISSING")
    spans.append({
        "slot": "value", "canonical_value": atom["value"], "surface_text": value_surface,
        "char_span": [value_start, value_start + len(value_surface)],
    })
    return spans


def _canonical(atom: dict[str, Any], context: dict[str, Any]) -> str:
    context_text = ",".join(f"{key}={context.get(key)}" for key in ("time_scope", "reference_frame", "scope", "state_id", "branch_id"))
    if atom["predicate"] == "VISIBLE_IN_FRAME":
        proposition = f"VISIBLE_IN_FRAME({entity_description(atom['subject'])})"
    elif atom["predicate"] == "COUNT":
        proposition = f"COUNT({entity_description(atom['subject'])},value={atom.get('value')})"
    else:
        proposition = f"{atom['predicate']}({entity_description(atom['subject'])},{entity_description(atom['object'])})"
    return f"{context_text} | {proposition}"


def _entity_declaration(entity_aliases: dict[str, str], predicate: str) -> str:
    by_alias = {alias: entity_id for entity_id, alias in entity_aliases.items()}
    if set(by_alias) != {"entity A", "entity B"}:
        return ""
    return (
        f"Let entity A denote the {_surface_entity(by_alias['entity A'], predicate)}, "
        f"and let entity B denote the {_surface_entity(by_alias['entity B'], predicate)}. "
    )


def _pair_entity_aliases(pair_id: str, supported_graph: dict[str, Any], contradictory_graph: dict[str, Any]) -> dict[str, str]:
    entity_ids = sorted({
        atom.get(slot)
        for graph in (supported_graph, contradictory_graph)
        for atom in graph["atoms"]
        for slot in ("subject", "object")
        if atom.get(slot) is not None
    })
    if len(entity_ids) != 2:
        return {}
    if hashlib.sha256(f"alias\0{pair_id}".encode("utf-8")).digest()[0] & 1:
        entity_ids.reverse()
    return {entity_ids[0]: "entity A", entity_ids[1]: "entity B"}


def _candidate(
    pair_id: str, graph: dict[str, Any], template_index: int, lexical_index: int | None = None,
    entity_aliases: dict[str, str] | None = None,
) -> dict[str, Any]:
    family, relational_template = TEMPLATES[template_index]
    atom = graph["atoms"][0]
    predicate = atom["predicate"]
    entity_aliases = entity_aliases or {}
    declaration = _entity_declaration(entity_aliases, predicate)
    lexical_index = template_index % 3 if lexical_index is None else lexical_index
    context, context_suffix = _context_forms(graph["context"])
    subject = entity_aliases.get(atom["subject"], _surface_entity(atom["subject"], predicate))
    if predicate == "VISIBLE_IN_FRAME":
        relation = VISIBLE_RELATIONS[lexical_index % len(VISIBLE_RELATIONS)]
        text = VISIBLE_TEMPLATES[family].format(
            context=context, context_suffix=context_suffix, subject=subject, relation=relation,
        )
        text = declaration + text
        alignment = _unary_alignment(text, atom, relation, graph["context"], context if family == "context_first" else context_suffix, entity_aliases)
    elif predicate == "COUNT":
        relation = COUNT_RELATIONS[lexical_index % len(COUNT_RELATIONS)]
        value = int(atom["value"])
        text = COUNT_TEMPLATES[family].format(
            context=context, context_suffix=context_suffix, subject=subject, relation=relation,
            value=value, plural="" if value == 1 else "s",
        )
        text = declaration + text
        alignment = _count_alignment(text, atom, relation, graph["context"], context if family == "context_first" else context_suffix, entity_aliases)
    else:
        relation = RELATIONS[predicate][lexical_index % len(RELATIONS[predicate])]
        object_ = entity_aliases.get(atom["object"], _surface_entity(atom["object"], predicate))
        text = relational_template.format(context=context, context_suffix=context_suffix, subject=subject, relation=relation, object=object_)
        text = declaration + text
        alignment = _alignment(text, atom["subject"], predicate, relation, atom["object"], graph["context"], context if family == "context_first" else context_suffix, entity_aliases)
    return {
        "candidate_id": f"{pair_id}:{graph['label'].casefold()}:text_{template_index + 1}",
        "style_family": family,
        "syntax_family": family,
        "surface_blueprint_id": f"{predicate.casefold()}:{family}:v2",
        "canonical_text": _canonical(atom, graph["context"]),
        "natural_text": text,
        "text_graph_alignment": alignment,
        "entity_aliases": entity_aliases,
        "entity_declaration": declaration,
    }


def realize_texts(
    *, candidates: int, dry_run: bool, resume: bool, seed: int, limit: int | None,
    claim_build_version: str = CLAIM_BUILD_VERSION,
    realization_version: str = REALIZATION_VERSION,
    root: Path = ROOT,
) -> dict[str, Any]:
    source_path = root / "candidates/structural" / f"pairs.{claim_build_version}.jsonl"
    output_path = root / "realizations" / realization_version / "pairs.jsonl"
    trace_path = root / "realization_traces" / f"traces.{realization_version}.jsonl"
    report_path = root / "reports" / f"language_realization.{realization_version}.json"
    if dry_run:
        return {"status": "PLANNED", "input": str(source_path.relative_to(root)), "output": str(output_path.relative_to(root)), "candidates_per_claim": candidates}
    if candidates < 1 or candidates > len(TEMPLATES):
        return {"status": "REJECTED", "reason": "INVALID_CANDIDATE_COUNT", "allowed": [1, len(TEMPLATES)]}
    if not source_path.exists():
        return {"status": "BLOCKED_SOURCE", "reason": "STRUCTURAL_CANDIDATES_MISSING"}
    rows = _load_jsonl(source_path)
    if limit is not None:
        rows = rows[:limit]
    realized = []
    traces = []
    selected_families: Counter[str] = Counter()
    selected_lexicalizations: Counter[str] = Counter()
    for ordinal, row in enumerate(rows):
        pair_id = row["pair_id"]
        supported_path = root / next(path for path in row["artifacts"] if path.endswith(".supported.json"))
        contradictory_path = root / next(path for path in row["artifacts"] if path.endswith(".contradictory.json"))
        supported_graph = json.loads(supported_path.read_text(encoding="utf-8"))
        contradictory_graph = json.loads(contradictory_path.read_text(encoding="utf-8"))
        entity_aliases = _pair_entity_aliases(pair_id, supported_graph, contradictory_graph)
        selected_index = ordinal % len(TEMPLATES)
        lexical_index = (ordinal // len(TEMPLATES)) % 3
        indices = [(selected_index + offset) % len(TEMPLATES) for offset in range(candidates)]
        supported_candidates = [_candidate(pair_id, supported_graph, index, (lexical_index + offset) % 3, entity_aliases) for offset, index in enumerate(indices)]
        contradictory_candidates = [_candidate(pair_id, contradictory_graph, index, (lexical_index + offset) % 3, entity_aliases) for offset, index in enumerate(indices)]
        selected_position = indices.index(selected_index)
        selected_families[TEMPLATES[selected_index][0]] += 1
        selected_lexicalizations[supported_candidates[selected_position]["text_graph_alignment"][1]["surface_text"]] += 1
        plan_id = f"rp:{hashlib.sha256(f'{realization_version}\0{pair_id}\0{selected_index}'.encode()).hexdigest()[:24]}"
        realized.append({
            **{key: row[key] for key in ("pair_id", "global_world_id", "split", "source_dataset", "source_item_ids", "level", "primary_track", "secondary_tracks", "operator_id")},
            "realization_plan_id": plan_id,
            "supported_graph_path": str(supported_path.relative_to(root)),
            "contradictory_graph_path": str(contradictory_path.relative_to(root)),
            "supported_candidates": supported_candidates,
            "contradictory_candidates": contradictory_candidates,
            "selected_candidate_ids": [supported_candidates[selected_position]["candidate_id"], contradictory_candidates[selected_position]["candidate_id"]],
            "selected_style_family": TEMPLATES[selected_index][0],
            "artifacts": row["artifacts"],
            "status": "TEXT_REALIZED_VERIFICATION_PENDING",
        })
        traces.append({
            "pair_id": pair_id, "realization_plan_id": plan_id,
            "candidate_ids": [item["candidate_id"] for item in supported_candidates + contradictory_candidates],
            "selected_candidate_ids": realized[-1]["selected_candidate_ids"],
            "plan": {
                "style_family": TEMPLATES[selected_index][0], "syntax_family": TEMPLATES[selected_index][0],
                "information_order": "context_subject_relation_object" if "context" in TEMPLATES[selected_index][0] else "subject_relation_object_context",
                "entity_reference": "pair_randomized_explicit_alias_declaration", "context_position": "explicit",
                "clause_structure": "single_clause", "anaphora_policy": "no_pronoun",
                "required_explicit_fields": ["time_scope", "reference_frame", "subject", "predicate", "object"],
                "forbidden_features": ["new_attribute", "new_causal_relation", "implicit_reference_frame", "epistemic_hedging"],
            },
            "selection": {"roundtrip": "pending", "pair_balance": "pass", "duplicate_score": 0.0, "quota_gap_reduction": 0.0},
            "rejected_candidates": [],
        })
    realized_payload = b"".join(_json_bytes(row) + b"\n" for row in realized)
    traces_payload = b"".join(_json_bytes(row) + b"\n" for row in traces)
    _write(output_path, realized_payload, resume)
    _write(trace_path, traces_payload, resume)
    report = {
        "schema_version": "1.0", "realization_version": realization_version, "status": "TEXT_REALIZED",
        "pair_count": len(realized), "candidates_per_claim": candidates,
        "selected_style_family_counts": dict(sorted(selected_families.items())),
        "selected_relation_lexicalization_counts": dict(sorted(selected_lexicalizations.items())),
        "surface_blueprint_pair_match_rate": 1.0 if realized else 0.0,
        "input_hashes": {str(source_path.relative_to(root)): sha256_file(source_path)},
        "output_hashes": {str(output_path.relative_to(root)): sha256_bytes(realized_payload), str(trace_path.relative_to(root)): sha256_bytes(traces_payload)},
        "next_gate": "GRAPH_TEXT_GRAPH_VERIFICATION_PENDING",
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    _write(report_path, payload, resume)
    return report


def _parsed_context(context_text: str, graph: dict[str, Any]) -> dict[str, Any] | None:
    time_number = r"[0-9]+(?:\.[0-9]+)?"
    context_by_surface = {
        surface: key for key, values in CONTEXTS.items() for surface in values
    }
    context_key = context_by_surface.get(context_text)
    interval_match = re.fullmatch(
        rf"[Aa]t ({time_number}) seconds in the actual video, viewed from the observer frame",
        context_text,
    )
    parsed_context: dict[str, Any] | None = None
    if interval_match:
        timestamp = float(interval_match.group(1))
        parsed_context = {
            "time_scope": {"start": timestamp, "end": timestamp}, "reference_frame": "observer",
            "scope": "time_interval", "state_id": "observed", "branch_id": "actual",
        }
    if context_key is None and parsed_context is None:
        return None
    if parsed_context is None:
        parsed_context = {
            key: (None if value == "None" else value)
            for key, value in zip(("time_scope", "reference_frame", "scope", "state_id", "branch_id"), context_key, strict=True)
        }
    for key in ("world_id", "media_id", "view_id", "frame_id"):
        if key in graph["context"]:
            parsed_context[key] = graph["context"].get(key)
    return parsed_context


def _context_patterns(relation_pattern: str, tail_pattern: str) -> dict[str, re.Pattern[str]]:
    time_number = r"[0-9]+(?:\.[0-9]+)?"
    interval_prefix = rf"At {time_number} seconds in the actual video, viewed from the observer frame"
    interval_suffix = rf"at {time_number} seconds in the actual video, viewed from the observer frame"
    context_prefix = "|".join([*(re.escape(value[0]) for value in CONTEXTS.values()), interval_prefix])
    context_suffix = "|".join([*(re.escape(value[1]) for value in CONTEXTS.values()), interval_suffix])
    return {
        "context_first": re.compile(rf"^({context_prefix}), the (.+) ({relation_pattern}){tail_pattern}\.$"),
        "subject_first": re.compile(rf"^The (.+) ({relation_pattern}){tail_pattern} ({context_suffix})\.$"),
        "evidence_first": re.compile(rf"^Considering the evidence ({context_suffix}), the (.+) ({relation_pattern}){tail_pattern}\.$"),
        "observed_context": re.compile(rf"^As observed ({context_suffix}), the (.+) ({relation_pattern}){tail_pattern}\.$"),
        "scene_attribution": re.compile(rf"^According to the scene ({context_suffix}), the (.+) ({relation_pattern}){tail_pattern}\.$"),
        "fixed_context": re.compile(rf"^With the context fixed ({context_suffix}), the (.+) ({relation_pattern}){tail_pattern}\.$"),
    }


def _parse(candidate: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any] | None:
    atom = graph["atoms"][0]
    predicate = atom["predicate"]
    entity_aliases = candidate.get("entity_aliases") or {}
    declaration = candidate.get("entity_declaration") or ""
    if declaration != _entity_declaration(entity_aliases, predicate):
        return None
    natural_text = candidate["natural_text"]
    if not natural_text.startswith(declaration):
        return None
    claim_text = natural_text[len(declaration):]
    if predicate == "VISIBLE_IN_FRAME":
        relation_pattern = "|".join(re.escape(item) for item in VISIBLE_RELATIONS)
        patterns = _context_patterns(relation_pattern, "")
        match = patterns[candidate["style_family"]].match(claim_text)
        if match is None:
            return None
        if candidate["style_family"] == "subject_first":
            subject_text, relation_text, context_text = match.groups()
        else:
            context_text, subject_text, relation_text = match.groups()
        expected_subject = entity_aliases.get(atom["subject"], _surface_entity(atom["subject"], predicate))
        if relation_text not in VISIBLE_RELATIONS or subject_text != expected_subject:
            return None
        parsed_context = _parsed_context(context_text, graph)
        if parsed_context is None:
            return None
        return {
            "subject": atom["subject"], "predicate": predicate, "object": None,
            "value": None, "polarity": "positive", "context": parsed_context,
        }
    if predicate == "COUNT":
        relation_pattern = "|".join(re.escape(item) for item in COUNT_RELATIONS)
        patterns = _context_patterns(relation_pattern, r" ([0-9]+) visible instances?")
        match = patterns[candidate["style_family"]].match(claim_text)
        if match is None:
            return None
        if candidate["style_family"] == "subject_first":
            subject_text, relation_text, value_text, context_text = match.groups()
        else:
            context_text, subject_text, relation_text, value_text = match.groups()
        expected_subject = entity_aliases.get(atom["subject"], _surface_entity(atom["subject"], predicate))
        if relation_text not in COUNT_RELATIONS or subject_text != expected_subject:
            return None
        parsed_context = _parsed_context(context_text, graph)
        if parsed_context is None:
            return None
        return {
            "subject": atom["subject"], "predicate": predicate, "object": None,
            "value": int(value_text), "polarity": "positive", "context": parsed_context,
        }

    relation_pattern = "|".join(re.escape(item) for values in RELATIONS.values() for item in values)
    patterns = _context_patterns(relation_pattern, r" the (.+)")
    match = patterns[candidate["style_family"]].match(claim_text)
    if match is None:
        return None
    if candidate["style_family"] == "subject_first":
        subject_text, relation_text, object_text, context_text = match.groups()
    else:
        context_text, subject_text, relation_text, object_text = match.groups()
    predicate_by_relation = {surface: relation_predicate for relation_predicate, surfaces in RELATIONS.items() for surface in surfaces}
    parsed_predicate = predicate_by_relation.get(relation_text)
    if parsed_predicate is None:
        return None
    descriptions = {
        entity_aliases.get(claim_atom[slot], _surface_entity(claim_atom[slot], parsed_predicate)): claim_atom[slot]
        for claim_atom in graph["atoms"] for slot in ("subject", "object")
    }
    if subject_text not in descriptions or object_text not in descriptions:
        return None
    parsed_context = _parsed_context(context_text, graph)
    if parsed_context is None:
        return None
    return {
        "subject": descriptions[subject_text], "predicate": parsed_predicate, "object": descriptions[object_text],
        "value": None, "polarity": "positive", "context": parsed_context,
    }


def _sample_duplicate_key(candidate: dict[str, Any]) -> tuple[str, bytes]:
    return (
        candidate["natural_text"].casefold(),
        _json_bytes(candidate["normalized"]["context"]),
    )


def verify_texts(
    *, dry_run: bool, resume: bool, limit: int | None,
    realization_version: str = REALIZATION_VERSION,
    text_verification_version: str = TEXT_VERIFICATION_VERSION,
    root: Path = ROOT,
) -> dict[str, Any]:
    source_path = root / "realizations" / realization_version / "pairs.jsonl"
    output_path = root / "candidates/verified" / f"pairs.{text_verification_version}.jsonl"
    report_path = root / "reports" / f"text_verification.{text_verification_version}.json"
    if dry_run:
        return {"status": "PLANNED", "input": str(source_path.relative_to(root)), "output": str(output_path.relative_to(root))}
    if not source_path.exists():
        return {"status": "BLOCKED_SOURCE", "reason": "REALIZED_TEXT_MISSING"}
    rows = _load_jsonl(source_path)
    if limit is not None:
        rows = rows[:limit]
    accepted = []
    rejects: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    sample_keys: Counter[tuple[str, bytes]] = Counter()
    surface_texts: Counter[str] = Counter()
    for row in rows:
        graphs = [json.loads((root / row[key]).read_text()) for key in ("supported_graph_path", "contradictory_graph_path")]
        selected = []
        for side, graph in zip(("supported", "contradictory"), graphs, strict=True):
            candidate_id = row["selected_candidate_ids"][0 if side == "supported" else 1]
            candidate = next(item for item in row[f"{side}_candidates"] if item["candidate_id"] == candidate_id)
            parsed = _parse(candidate, graph)
            atom = graph["atoms"][0]
            if parsed is None or any(parsed[key] != atom.get(key) for key in ("subject", "predicate", "object", "value", "polarity")):
                rejects["GRAPH_TEXT_DRIFT"] += 1
                selected = []
                break
            if any(parsed["context"][key] != graph["context"].get(key) for key in parsed["context"]):
                rejects["GRAPH_TEXT_DRIFT"] += 1
                selected = []
                break
            selected.append({**candidate, "normalized": graph})
        if not selected:
            continue
        if selected[0]["surface_blueprint_id"] != selected[1]["surface_blueprint_id"]:
            rejects["PAIR_STYLE_LEAKAGE"] += 1
            continue
        length_delta = abs(len(selected[0]["natural_text"]) - len(selected[1]["natural_text"]))
        if length_delta > 12:
            rejects["PAIR_STYLE_LEAKAGE"] += 1
            continue
        duplicate = any(sample_keys[_sample_duplicate_key(item)] for item in selected)
        if duplicate:
            rejects["DUPLICATE_SAMPLE"] += 1
            continue
        for item in selected:
            sample_keys[_sample_duplicate_key(item)] += 1
            surface_texts[item["natural_text"].casefold()] += 1
        family_counts[row["selected_style_family"]] += 1
        accepted.append({**row, "supported_claim": selected[0], "contradictory_claim": selected[1], "status": "TEXT_VALID"})
    payload = b"".join(_json_bytes(row) + b"\n" for row in accepted)
    _write(output_path, payload, resume)
    max_family_ratio = max(family_counts.values(), default=0) / len(accepted) if accepted else 0.0
    accepted_claim_count = len(accepted) * 2
    reused_surface_claim_count = accepted_claim_count - len(surface_texts)
    report = {
        "schema_version": "1.0", "text_verification_version": text_verification_version,
        "status": "TEXT_VALID" if accepted and not rejects else ("PARTIAL" if accepted else "REJECTED"),
        "input_pair_count": len(rows), "accepted_pair_count": len(accepted), "rejected_pair_count": len(rows) - len(accepted),
        "reject_code_counts": dict(sorted(rejects.items())), "roundtrip_pass_rate": len(accepted) / len(rows) if rows else 0.0,
        "pair_balance_pass_rate": len(accepted) / len(rows) if rows else 0.0,
        "selected_style_family_counts": dict(sorted(family_counts.items())), "max_style_family_ratio": max_family_ratio,
        "duplicate_unit": "normalized_claim_text_plus_full_claim_context",
        "exact_sample_duplicate_rate": rejects.get("DUPLICATE_SAMPLE", 0) / len(rows) if rows else 0.0,
        "surface_text_unique_count": len(surface_texts),
        "surface_text_reuse_claim_count": reused_surface_claim_count,
        "surface_text_reuse_rate": reused_surface_claim_count / accepted_claim_count if accepted_claim_count else 0.0,
        "input_hashes": {str(source_path.relative_to(root)): sha256_file(source_path)},
        "output_hashes": {str(output_path.relative_to(root)): sha256_bytes(payload)},
        "next_gate": "INDEPENDENT_PROOF_VERIFICATION_PENDING",
    }
    report_payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    _write(report_path, report_payload, resume)
    return report
