#!/usr/bin/env python3
"""Count proof-safe L2 chains and fully grounded L4 transitions.

This is a conservative feasibility gate. It does not generate claims and it
does not treat absent pre-state, target, invariant, or branch facts as false.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


L2_RULE_PREDICATES = {
    "AUTHORIZED_DIRECTION_TRANSITIVITY": {"LEFT_OF", "RIGHT_OF", "ABOVE", "BELOW"},
    "STRICT_ORDER_TRANSITIVITY": {"BEFORE", "AFTER"},
}


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def rows(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def graph_rows(root: Path, manifest: Path, limit: int | None) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
    checked = 0
    for row in rows(manifest):
        if row.get("validation_status") != "GRAPH_VALID":
            continue
        if limit is not None and checked >= limit:
            break
        path = root / row["graph_path"]
        if sha256(path) != row["graph_sha256"]:
            raise ValueError(f"GRAPH_HASH_MISMATCH:{row['global_world_id']}")
        checked += 1
        yield row, json.loads(path.read_text(encoding="utf-8"))


def l2_candidates(graph: dict[str, Any]) -> list[dict[str, Any]]:
    allowed: set[str] = set()
    for rule in graph.get("authorized_rule_ids", []):
        allowed.update(L2_RULE_PREDICATES.get(rule, set()))
    by_context_predicate: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for fact in graph.get("facts", []):
        if (
            fact.get("polarity") == "positive"
            and fact.get("predicate") in allowed
            and isinstance(fact.get("subject"), str)
            and isinstance(fact.get("object"), str)
            and fact["subject"] != fact["object"]
        ):
            by_context_predicate[(canonical(fact["context"]), fact["predicate"])].append(fact)
    candidates: list[dict[str, Any]] = []
    for (_, predicate), facts in sorted(by_context_predicate.items()):
        outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fact in facts:
            outgoing[fact["subject"]].append(fact)
        seen: set[tuple[str, str]] = set()
        for first in facts:
            for second in outgoing.get(first["object"], []):
                if first["subject"] == second["object"]:
                    continue
                key = tuple(sorted((first["fact_id"], second["fact_id"])))
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({
                    "predicate": predicate,
                    "premise_fact_ids": [first["fact_id"], second["fact_id"]],
                    "derived": [first["subject"], predicate, second["object"]],
                    "contradictory": [second["object"], predicate, first["subject"]],
                })
    return candidates


def l4_branch_inventory(graph: dict[str, Any]) -> dict[str, Any]:
    branches: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "pre": [], "post": [], "interventions": set(), "target_ids": set(),
        "affected_sets": set(), "invariant_sets": set(),
    })
    for fact in graph.get("facts", []):
        context = fact.get("context", {})
        branch = str(context.get("branch_id"))
        state = str(context.get("state_id"))
        entry = branches[branch]
        if state == "pre_intervention":
            entry["pre"].append(fact["fact_id"])
        if state == "post_intervention":
            entry["post"].append(fact["fact_id"])
        intervention = context.get("intervention")
        if isinstance(intervention, dict) and intervention.get("context_change"):
            entry["interventions"].add(canonical(intervention))
            if intervention.get("target_id"):
                entry["target_ids"].add(str(intervention["target_id"]))
            if intervention.get("affected_set"):
                entry["affected_sets"].add(canonical(intervention["affected_set"]))
            if intervention.get("invariant_set"):
                entry["invariant_sets"].add(canonical(intervention["invariant_set"]))
    complete = []
    for branch, entry in branches.items():
        if all((entry["pre"], entry["post"], entry["interventions"], entry["target_ids"], entry["affected_sets"])):
            complete.append(branch)
    return {
        "branch_count": len(branches),
        "branches_with_pre_state": sum(bool(row["pre"]) for row in branches.values()),
        "branches_with_post_state": sum(bool(row["post"]) for row in branches.values()),
        "branches_with_intervention": sum(bool(row["interventions"]) for row in branches.values()),
        "branches_with_target_binding": sum(bool(row["target_ids"]) for row in branches.values()),
        "branches_with_affected_set": sum(bool(row["affected_sets"]) for row in branches.values()),
        "branches_with_invariant_set": sum(bool(row["invariant_sets"]) for row in branches.values()),
        "complete_branch_ids": complete,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--l2-manifest", type=Path, required=True)
    parser.add_argument("--l4-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    root = args.root.resolve()
    l2_manifest = args.l2_manifest.resolve()
    l4_manifest = args.l4_manifest.resolve()
    output = args.output.resolve()
    for path in (l2_manifest, l4_manifest, output.parent):
        path.relative_to(root)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    if args.dry_run:
        print(json.dumps({
            "status": "PLANNED", "l2_manifest": str(l2_manifest),
            "l4_manifest": str(l4_manifest), "output": str(output), "limit": args.limit,
        }, indent=2, sort_keys=True))
        return 0

    l2_by_dataset: Counter[str] = Counter()
    l2_by_predicate: Counter[str] = Counter()
    l2_worlds = 0
    l2_candidate_rows: list[dict[str, Any]] = []
    for manifest_row, graph in graph_rows(root, l2_manifest, args.limit):
        l2_worlds += 1
        candidates = l2_candidates(graph)
        for candidate in candidates:
            dataset = graph["source_datasets"][0] if len(graph["source_datasets"]) == 1 else "multi_source"
            l2_by_dataset[dataset] += 1
            l2_by_predicate[candidate["predicate"]] += 1
            if len(l2_candidate_rows) < 100:
                l2_candidate_rows.append({
                    "global_world_id": graph["global_world_id"],
                    "split": manifest_row["split"], "source_dataset": dataset, **candidate,
                })

    l4_totals: Counter[str] = Counter()
    l4_worlds = 0
    for _, graph in graph_rows(root, l4_manifest, args.limit):
        l4_worlds += 1
        inventory = l4_branch_inventory(graph)
        for key, value in inventory.items():
            if key != "complete_branch_ids":
                l4_totals[key] += int(value)
        l4_totals["complete_l4_branches"] += len(inventory["complete_branch_ids"])

    l2_count = sum(l2_by_dataset.values())
    l4_count = l4_totals["complete_l4_branches"]
    report = {
        "schema_version": "1.0", "audit_version": "level_feasibility_v1",
        "status": "FEASIBILITY_AUDITED", "seed": args.seed, "run_id": args.run_id,
        "quality_policy": "count_only_candidates_that_meet_all_proof_prerequisites",
        "l2": {
            "checked_worlds": l2_worlds, "irreducible_two_fact_chain_count": l2_count,
            "by_dataset": dict(sorted(l2_by_dataset.items())),
            "by_predicate": dict(sorted(l2_by_predicate.items())),
            "examples": l2_candidate_rows,
            "next_gate": "IMPLEMENT_VERSIONED_L2_OPERATOR_AND_INDEPENDENT_REPLAY" if l2_count else "L2_SOURCE_GRAPH_EXPANSION_REQUIRED",
        },
        "l4": {
            "checked_worlds": l4_worlds, **dict(sorted(l4_totals.items())),
            "proof_safe_candidate_count": l4_count,
            "required_fields": ["pre_state", "intervention", "target_binding", "affected_set", "branch", "post_state"],
            "next_gate": "IMPLEMENT_VERSIONED_L4_OPERATOR_AND_INDEPENDENT_REPLAY" if l4_count else "STRUCTURED_PRE_STATE_TARGET_AND_AFFECTED_SET_ADAPTER_REQUIRED",
        },
        "input_hashes": {
            str(l2_manifest.relative_to(root)): sha256(l2_manifest),
            str(l4_manifest.relative_to(root)): sha256(l4_manifest),
        },
        "success_count": l2_count + l4_count,
        "failure_count": 0,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        if not args.resume:
            raise FileExistsError(f"Output exists: {output}; use --resume")
        if output.read_bytes() != payload:
            raise ValueError(f"Non-deterministic output: {output}")
    else:
        output.write_bytes(payload)
    print(json.dumps({
        "status": report["status"], "l2_candidates": l2_count,
        "l4_candidates": l4_count, "output": str(output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
