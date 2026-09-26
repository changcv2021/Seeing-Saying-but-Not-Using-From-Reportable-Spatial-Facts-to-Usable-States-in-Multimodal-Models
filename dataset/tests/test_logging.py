from argparse import Namespace
from pathlib import Path

from spaceconflict import cli
from spaceconflict.logging_utils import run_envelope


def _args(**overrides):
    values = {
        "run_id": "test_run", "dry_run": False, "resume": True, "seed": 17,
        "limit": None, "world_id": None, "workers": 1, "config": None,
    }
    values.update(overrides)
    return Namespace(**values)


def test_run_envelope_captures_config_statuses_and_hashes(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("target_pairs: 10\n", encoding="utf-8")
    result = {
        "status": "PASS",
        "input_hashes": {"input.jsonl": "sha256:in"},
        "output_hashes": {"output.jsonl": "sha256:out"},
        "results": [{"status": "GRAPH_VALID"}, {"status": "REJECTED"}],
    }
    envelope = run_envelope("sample-quota", _args(config=config), result=result)
    assert envelope["git_commit"]
    assert envelope["config_snapshot"]["config_file"]["content"] == "target_pairs: 10\n"
    assert envelope["config_snapshot"]["config_file"]["sha256"].startswith("sha256:")
    assert envelope["status_counts"] == {"GRAPH_VALID": 1, "PASS": 1, "REJECTED": 1}
    assert envelope["input_hashes"]["result:input.jsonl"] == "sha256:in"
    assert envelope["output_hashes"]["result:output.jsonl"] == "sha256:out"
    assert envelope["exception"] is None


def test_cli_operational_exception_is_logged(monkeypatch) -> None:
    captured = {}

    def fail(_args):
        raise RuntimeError("intentional-test-error")

    def capture(envelope):
        captured.update(envelope)
        return Path("runs/test/discover.json")

    monkeypatch.setattr(cli, "_dispatch", fail)
    monkeypatch.setattr(cli, "write_run_log", capture)
    code = cli.main(["discover", "--run-id", "exception_test"])
    assert code == 1
    assert captured["result_status"] == "FAILED_EXCEPTION"
    assert captured["counts"] == {"success": 0, "failure": 1}
    assert captured["exception"] == {
        "type": "RuntimeError", "message": "intentional-test-error",
    }
