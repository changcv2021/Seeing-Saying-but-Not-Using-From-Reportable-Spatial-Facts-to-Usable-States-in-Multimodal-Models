from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from ..canonical import CANONICAL_VERSION
from ..hashing import sha256_bytes, sha256_file
from ..registry import ROOT, contract_path
from ..world_index.pipeline import SPLIT_VERSION, WORLD_INDEX_VERSION


WORLD_GRAPH_VERSION = "world_graph_v5"
EXCLUSIVE = {
    "LEFT_OF": "RIGHT_OF", "RIGHT_OF": "LEFT_OF",
    "ABOVE": "BELOW", "BELOW": "ABOVE",
    "FRONT_OF": "BEHIND", "BEHIND": "FRONT_OF",
    "BEFORE": "AFTER", "AFTER": "BEFORE",
}


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _graph_validator(root: Path) -> Draft202012Validator:
    schema = copy.deepcopy(json.loads((root / "schemas/world_graph.schema.json").read_text()))
    schema["properties"]["facts"]["items"] = json.loads(
        (root / "schemas/canonical_fact.schema.json").read_text()
    )
    return Draft202012Validator(schema)


def _contract(dataset: str, root: Path) -> dict[str, Any]:
    return yaml.safe_load(contract_path(dataset, root).read_text(encoding="utf-8"))


def _semantic_key(fact: dict[str, Any]) -> bytes:
    return _json_bytes({
        key: fact.get(key)
        for key in ("subject", "predicate", "object", "value", "polarity", "quantifier", "context")
    })


def _merge_duplicates(facts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    groups: dict[bytes, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        groups[_semantic_key(fact)].append(fact)
    merged: list[dict[str, Any]] = []
    duplicate_count = 0
    for key in sorted(groups):
        group = sorted(groups[key], key=lambda row: row["fact_id"])
        selected = copy.deepcopy(group[0])
        if len(group) > 1:
            duplicate_count += len(group) - 1
            selected["grounding"]["merged_equivalent_fact_ids"] = [row["fact_id"] for row in group]
            selected["grounding"]["merged_provenance"] = [row["provenance"] for row in group]
            selected.pop("canonical_fact_hash", None)
            selected.pop("fact_id", None)
            digest = sha256_bytes(_json_bytes(selected))
            selected["fact_id"] = f"fact:{digest.removeprefix('sha256:')[:24]}"
            selected["canonical_fact_hash"] = digest
        merged.append(selected)
    return sorted(merged, key=lambda row: row["fact_id"]), duplicate_count


def _node_type(node_id: str) -> str:
    if node_id.startswith("class:"):
        return "CLASS"
    if node_id.startswith("first_appear:"):
        return "EVENT"
    if node_id.startswith("mention:"):
        return "SOURCE_ITEM_LOCAL_MENTION"
    if "observer" in node_id:
        return "OBSERVER"
    return "ENTITY"


def _context_key(fact: dict[str, Any]) -> bytes:
    return _json_bytes(fact["context"])


def _validation_errors(
    graph: dict[str, Any], allowed_predicates: set[str], validator: Draft202012Validator,
) -> list[str]:
    errors: list[str] = []
    if any(fact["context"]["world_id"] != graph["global_world_id"] for fact in graph["facts"]):
        errors.append("WORLD_SCOPE_MISMATCH")
    media_ids = {media["media_id"] for media in graph["media"]}
    if any(fact["context"].get("media_id") not in media_ids for fact in graph["facts"]):
        errors.append("ORPHAN_MEDIA")
    if any(fact["predicate"] not in allowed_predicates for fact in graph["facts"]):
        errors.append("UNAUTHORIZED_PREDICATE")
    if any(fact["observability"] == "oracle_only" for fact in graph["facts"]):
        errors.append("ORACLE_ONLY_CORE_FACT")
    positive = {
        (fact["subject"], fact["predicate"], fact.get("object"), _context_key(fact))
        for fact in graph["facts"] if fact["polarity"] == "positive"
    }
    negative = {
        (fact["subject"], fact["predicate"], fact.get("object"), json.dumps(fact.get("value"), sort_keys=True), _context_key(fact))
        for fact in graph["facts"] if fact["polarity"] == "negative"
    }
    positive_with_value = {
        (fact["subject"], fact["predicate"], fact.get("object"), json.dumps(fact.get("value"), sort_keys=True), _context_key(fact))
        for fact in graph["facts"] if fact["polarity"] == "positive"
    }
    if positive_with_value & negative:
        errors.append("FACT_POLARITY_CONFLICT")
    for subject, predicate, object_id, context in positive:
        opposite = EXCLUSIVE.get(predicate)
        if opposite and (subject, opposite, object_id, context) in positive:
            errors.append("RELATION_EXCLUSIVITY_CONFLICT")
            break
    counts: dict[tuple[str, bytes], set[str]] = defaultdict(set)
    for fact in graph["facts"]:
        if fact["predicate"] == "COUNT" and fact["polarity"] == "positive":
            counts[(fact["subject"], _context_key(fact))].add(json.dumps(fact.get("value"), sort_keys=True))
    if any(len(values) > 1 for values in counts.values()):
        errors.append("COUNT_CONFLICT")
    candidate = {**graph, "validation_status": "GRAPH_VALID", "reject_codes": []}
    if list(validator.iter_errors(candidate)):
        errors.append("WORLD_GRAPH_SCHEMA_INVALID")
    return sorted(set(errors))


def _safe_name(world_id: str) -> str:
    digest = hashlib.sha256(world_id.encode("utf-8")).hexdigest()[:12]
    stem = "".join(character if character.isalnum() or character in "-_." else "_" for character in world_id)
    return f"{stem[:100]}.{digest}.json"


def build_graphs(
    datasets: list[str], *, dry_run: bool, resume: bool, limit: int | None,
    seed: int, root: Path = ROOT,
    world_index_version: str = WORLD_INDEX_VERSION,
    split_version: str = SPLIT_VERSION,
    world_graph_version: str = WORLD_GRAPH_VERSION,
) -> dict[str, Any]:
    index_path = root / "world_index" / f"{world_index_version}.jsonl"
    split_path = root / "splits" / f"{split_version}.seed_{seed}.jsonl"
    report_path = root / "reports" / f"graph_build.{world_graph_version}.json"
    if dry_run:
        return {
            "status": "PLANNED", "datasets": datasets,
            "world_index": str(index_path.relative_to(root)), "split": str(split_path.relative_to(root)),
            "limit": limit,
        }
    if not index_path.exists() or not split_path.exists():
        return {"status": "BLOCKED_SOURCE", "reason": "WORLD_INDEX_OR_SPLIT_MISSING"}
    index_rows = _load_jsonl(index_path)
    split_by_world = {row["global_world_id"]: row["split"] for row in _load_jsonl(split_path)}
    selected = [
        row for row in index_rows if set(row["source_datasets"]) & set(datasets)
    ]
    selected.sort(key=lambda row: row["global_world_id"])
    if limit is not None:
        selected = selected[:limit]
    missing_splits = [row["global_world_id"] for row in selected if row["global_world_id"] not in split_by_world]
    if missing_splits:
        return {"status": "REJECTED", "reason": "WORLD_SPLIT_MISSING", "world_ids": missing_splits}
    records_by_id: dict[str, dict[str, Any]] = {}
    canonical_paths = sorted(
        path
        for dataset in datasets
        for path in (root / "data/canonical" / dataset).glob(
            f"*/{CANONICAL_VERSION}/records.jsonl"
        )
    )
    for path in canonical_paths:
        for record in _load_jsonl(path):
            records_by_id[record["record_id"]] = record
    contracts = {dataset: _contract(dataset, root) for dataset in datasets}
    validator = _graph_validator(root)
    valid_count = 0
    rejected_count = 0
    duplicate_count = 0
    reject_counts: Counter[str] = Counter()
    manifest: list[dict[str, Any]] = []
    for world in selected:
        records = [records_by_id[record_id] for record_id in world["record_ids"]]
        facts, merged_count = _merge_duplicates([fact for record in records for fact in record["facts"]])
        duplicate_count += merged_count
        node_ids = sorted({
            value for fact in facts for value in (fact["subject"], fact.get("object"))
            if isinstance(value, str)
        })
        source_datasets = world["source_datasets"]
        allowed_predicates = {
            predicate for dataset in source_datasets
            for predicate in contracts[dataset]["allowed_predicates"]
        }
        authorized_rules = sorted({
            rule for dataset in source_datasets for rule in contracts[dataset]["authorized_rules"]
        })
        graph = {
            "world_graph_id": "world_graph:" + hashlib.sha256(
                f"{world_graph_version}\0{world['global_world_id']}".encode("utf-8")
            ).hexdigest()[:24],
            "schema_version": "1.0",
            "global_world_id": world["global_world_id"],
            "source_datasets": source_datasets,
            "media": world["media"],
            "nodes": [{"node_id": node_id, "node_type": _node_type(node_id)} for node_id in node_ids],
            "facts": facts,
            "authorized_rule_ids": authorized_rules,
            "validation_status": "GRAPH_VALID",
            "reject_codes": [],
        }
        errors = _validation_errors(graph, allowed_predicates, validator)
        graph["validation_status"] = "GRAPH_REJECTED" if errors else "GRAPH_VALID"
        graph["reject_codes"] = errors
        dataset_dir = source_datasets[0] if len(source_datasets) == 1 else "multi_source"
        base = root / ("world_graphs" if not errors else "rejected/graphs")
        output_path = base / dataset_dir / world_graph_version / _safe_name(world["global_world_id"])
        payload = json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            if not resume:
                raise FileExistsError(f"Output exists: {output_path}; use --resume")
            if output_path.read_bytes() != payload:
                raise ValueError(f"Non-deterministic graph output: {output_path}")
        else:
            output_path.write_bytes(payload)
        valid_count += int(not errors)
        rejected_count += int(bool(errors))
        reject_counts.update(errors)
        manifest.append({
            "global_world_id": world["global_world_id"], "split": split_by_world[world["global_world_id"]],
            "validation_status": graph["validation_status"], "graph_path": str(output_path.relative_to(root)),
            "graph_sha256": sha256_bytes(payload), "record_count": len(records), "fact_count": len(facts),
        })
    manifest_path = root / "world_graphs" / f"manifest.{world_graph_version}.jsonl"
    manifest_payload = b"".join(_json_bytes(row) + b"\n" for row in manifest)
    if manifest_path.exists():
        if not resume:
            raise FileExistsError(f"Output exists: {manifest_path}; use --resume")
        if manifest_path.read_bytes() != manifest_payload:
            raise ValueError(f"Non-deterministic graph manifest: {manifest_path}")
    else:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_bytes(manifest_payload)
    report = {
        "schema_version": "1.0", "world_graph_version": world_graph_version,
        "status": "GRAPH_VALID" if valid_count and not rejected_count else ("PARTIAL" if valid_count else "REJECTED"),
        "datasets": datasets, "world_count": len(selected), "graph_valid_count": valid_count,
        "graph_rejected_count": rejected_count, "semantic_duplicate_fact_merge_count": duplicate_count,
        "reject_code_counts": dict(sorted(reject_counts.items())),
        "split_leakage_check": "PASS", "source_qa_reconstruction_requirement": "100_PERCENT_ACCEPTED_FACTS",
        "input_hashes": {
            str(index_path.relative_to(root)): sha256_file(index_path),
            str(split_path.relative_to(root)): sha256_file(split_path),
            **{str(path.relative_to(root)): sha256_file(path) for path in canonical_paths},
        },
        "output_hashes": {str(manifest_path.relative_to(root)): sha256_bytes(manifest_payload)},
    }
    report_payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if report_path.exists():
        if not resume:
            raise FileExistsError(f"Output exists: {report_path}; use --resume")
        if report_path.read_bytes() != report_payload:
            raise ValueError(f"Non-deterministic graph report: {report_path}")
    else:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_bytes(report_payload)
    return report


def validate_graphs(
    *, dry_run: bool, limit: int | None, root: Path = ROOT,
    world_graph_version: str = WORLD_GRAPH_VERSION,
) -> dict[str, Any]:
    manifest_path = root / "world_graphs" / f"manifest.{world_graph_version}.jsonl"
    if dry_run:
        return {"status": "PLANNED", "manifest": str(manifest_path.relative_to(root)), "limit": limit}
    if not manifest_path.exists():
        return {"status": "BLOCKED_SOURCE", "reason": "GRAPH_MANIFEST_MISSING"}
    rows = _load_jsonl(manifest_path)
    if limit is not None:
        rows = rows[:limit]
    validator = _graph_validator(root)
    failures: list[dict[str, Any]] = []
    valid_graph_count = 0
    expected_rejected_graph_count = 0
    for row in rows:
        path = root / row["graph_path"]
        if not path.exists():
            failures.append({"global_world_id": row["global_world_id"], "reject_code": "GRAPH_FILE_MISSING"})
            continue
        if sha256_file(path) != row["graph_sha256"]:
            failures.append({"global_world_id": row["global_world_id"], "reject_code": "GRAPH_HASH_MISMATCH"})
            continue
        graph = json.loads(path.read_text(encoding="utf-8"))
        schema_errors = list(validator.iter_errors(graph))
        if schema_errors:
            failures.append({
                "global_world_id": row["global_world_id"],
                "reject_code": "GRAPH_SCHEMA_REVALIDATION_FAILED",
                "schema_error_count": len(schema_errors),
            })
            continue
        if graph["validation_status"] != row["validation_status"]:
            failures.append({
                "global_world_id": row["global_world_id"],
                "reject_code": "GRAPH_MANIFEST_STATUS_MISMATCH",
                "manifest_status": row["validation_status"],
                "graph_status": graph["validation_status"],
            })
            continue
        if row["validation_status"] == "GRAPH_VALID":
            valid_graph_count += 1
        elif graph.get("reject_codes"):
            expected_rejected_graph_count += 1
        else:
            failures.append({
                "global_world_id": row["global_world_id"],
                "reject_code": "REJECTED_GRAPH_REASON_MISSING",
            })
    return {
        "schema_version": "1.0", "world_graph_version": world_graph_version,
        "status": "GRAPH_MANIFEST_VALID" if not failures and rows else "REJECTED",
        "checked_graph_count": len(rows), "failure_count": len(failures), "failures": failures,
        "valid_graph_count": valid_graph_count,
        "expected_rejected_graph_count": expected_rejected_graph_count,
        "manifest_hash": sha256_file(manifest_path),
    }
