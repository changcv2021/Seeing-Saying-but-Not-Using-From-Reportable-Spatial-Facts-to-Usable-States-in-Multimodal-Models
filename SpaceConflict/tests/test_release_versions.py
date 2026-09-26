from pathlib import Path

import pytest

from spaceconflict.cli import build_parser
from spaceconflict.release import _configured_paths, _versions


def test_release_versions_are_config_driven(tmp_path: Path) -> None:
    config = tmp_path / "release.yaml"
    config.write_text(
        "quota_version: quota_test_v1\nexport_version: release_test_v1\n",
        encoding="utf-8",
    )
    quota, export, policy = _versions(config)
    assert (quota, export) == ("quota_test_v1", "release_test_v1")
    assert policy["export_version"] == "release_test_v1"


def test_release_versions_reject_path_traversal(tmp_path: Path) -> None:
    config = tmp_path / "release.yaml"
    config.write_text("export_version: ../escape\n", encoding="utf-8")
    with pytest.raises(ValueError, match="UNSAFE_RELEASE_VERSION"):
        _versions(config)


def test_export_cli_accepts_version_config() -> None:
    args = build_parser().parse_args([
        "export-benchmark", "--config", "configs/production_available_v1.yaml", "--dry-run",
    ])
    assert args.config == Path("configs/production_available_v1.yaml")


def test_release_configured_paths_are_root_scoped(tmp_path: Path) -> None:
    default = tmp_path / "candidates" / "default.jsonl"
    assert _configured_paths(root=tmp_path, policy={}, key="inputs", default=default) == [default.resolve()]
    configured = _configured_paths(
        root=tmp_path, policy={"inputs": ["candidates/one.jsonl", "candidates/two.jsonl"]},
        key="inputs", default=default,
    )
    assert configured == [
        (tmp_path / "candidates/one.jsonl").resolve(),
        (tmp_path / "candidates/two.jsonl").resolve(),
    ]
    with pytest.raises(ValueError, match="CONFIGURED_PATH_ESCAPES_ROOT"):
        _configured_paths(root=tmp_path, policy={"inputs": ["../escape.jsonl"]}, key="inputs", default=default)
