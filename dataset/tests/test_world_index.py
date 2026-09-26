from __future__ import annotations

import json
from pathlib import Path

from spaceconflict.canonical import CANONICAL_VERSION
from spaceconflict.world_index.pipeline import (
    SPLIT_VERSION, WORLD_INDEX_VERSION, build_world_index, split_worlds,
)


def _write_records(root: Path) -> None:
    path = root / "data/canonical/demo/revision" / CANONICAL_VERSION / "records.jsonl"
    path.parent.mkdir(parents=True)
    rows = []
    for index in range(20):
        rows.append({
            "record_id": f"record:{index}", "source_dataset": "demo",
            "source_item_ids": [f"item:{index}"], "global_world_id": f"demo:world_{index}",
            "media": [{"media_id": f"media:{index}"}],
            "facts": [{"fact_id": f"fact:{index}"}],
        })
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_world_index_and_split_are_world_isolated(tmp_path: Path) -> None:
    _write_records(tmp_path)
    index = build_world_index(dry_run=False, resume=False, limit=None, root=tmp_path)
    assert index["status"] == "WORLD_INDEX_VALID"
    split = split_worlds(dry_run=False, resume=False, seed=17, limit=None, root=tmp_path)
    assert split["status"] == "WORLD_SPLIT_VALID"
    assert split["split_counts"] == {"dev": 3, "test": 5, "train": 12}
    rows = [
        json.loads(line)
        for line in (tmp_path / f"splits/{SPLIT_VERSION}.seed_17.jsonl").read_text().splitlines()
    ]
    assert len({row["global_world_id"] for row in rows}) == len(rows) == 20


def test_world_index_dry_run_does_not_write(tmp_path: Path) -> None:
    result = build_world_index(dry_run=True, resume=True, limit=2, root=tmp_path)
    assert result["status"] == "PLANNED"
    assert not (tmp_path / "world_index").exists()


def test_world_index_supports_isolated_dataset_and_version_namespaces(tmp_path: Path) -> None:
    _write_records(tmp_path)
    other = tmp_path / "data/canonical/other/revision" / CANONICAL_VERSION / "records.jsonl"
    other.parent.mkdir(parents=True)
    other.write_text(json.dumps({
        "record_id": "record:other", "source_dataset": "other",
        "source_item_ids": ["item:other"], "global_world_id": "other:world",
        "media": [{"media_id": "media:other"}], "facts": [{"fact_id": "fact:other"}],
    }) + "\n", encoding="utf-8")

    index = build_world_index(
        dry_run=False, resume=False, limit=None, root=tmp_path,
        datasets=["demo"], world_index_version="world_index_demo_v1",
    )
    assert index["world_count"] == 20
    assert index["source_dataset_counts"] == {"demo": 20}
    split = split_worlds(
        dry_run=False, resume=False, seed=17, limit=None, root=tmp_path,
        world_index_version="world_index_demo_v1", split_version="world_split_demo_v1",
    )
    assert split["world_count"] == 20
    assert (tmp_path / "splits/world_split_demo_v1.seed_17.jsonl").exists()
