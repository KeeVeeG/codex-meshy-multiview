"""Interface behavior, bounded polling, and MCP contracts; no live API calls."""

from __future__ import annotations

import asyncio
import json

import pytest

from meshy_codex import cli, server

VIEWS = [
    "--front",
    "front.png",
    "--back",
    "back.png",
    "--left",
    "left.png",
    "--right",
    "right.png",
    "--output",
    "run",
]


def test_plan_maps_named_views_without_submitting(monkeypatch, capsys):
    received = {}

    def plan(**kwargs):
        received.update(kwargs)
        return {"paid_tasks": 0}

    monkeypatch.setattr(cli.workflow, "plan_workflow", plan)
    monkeypatch.setattr(
        cli.workflow, "start_workflow", lambda **_: pytest.fail("plan submitted a task")
    )
    assert cli.main(["plan", *VIEWS, "--texture-prompt", "brushed metal"]) == 0
    assert received == {
        "front": "front.png",
        "back": "back.png",
        "left": "left.png",
        "right": "right.png",
        "output_dir": "run",
        "texture_prompt": "brushed metal",
    }
    assert json.loads(capsys.readouterr().out) == {"paid_tasks": 0}


def test_run_submits_once_polls_and_downloads(monkeypatch, capsys):
    calls = []
    initial = {"run_dir": "run", "status": "generation", "next_step": "advance"}
    next_states = iter(
        [
            {"run_dir": "run", "status": "remesh", "next_step": "advance"},
            {"run_dir": "run", "status": "succeeded", "next_step": "download"},
        ]
    )

    def start(**_):
        calls.append("start")
        return initial

    def advance(run_dir):
        assert run_dir == "run"
        calls.append("advance")
        return next(next_states)

    def download(run_dir):
        assert run_dir == "run"
        calls.append("download")
        return {"run_dir": "run", "next_step": "complete", "artifacts": ["model.glb"]}

    monkeypatch.setattr(cli.workflow, "start_workflow", start)
    monkeypatch.setattr(cli.workflow, "advance_workflow", advance)
    monkeypatch.setattr(cli.workflow, "download_workflow", download)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    assert cli.main(["run", *VIEWS]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["artifacts"] == ["model.glb"]
    assert "Workflow:" in output.err
    assert calls == ["start", "advance", "advance", "download"]


@pytest.mark.parametrize("step", ["submission_uncertain", "submission_failed", "failed"])
def test_resume_stops_without_retrying_failed_submission(monkeypatch, capsys, step):
    monkeypatch.setattr(
        cli.workflow, "workflow_status", lambda _: {"run_dir": "run", "next_step": step}
    )
    monkeypatch.setattr(
        cli.workflow, "advance_workflow", lambda _: pytest.fail("failed run advanced")
    )
    monkeypatch.setattr(
        cli.workflow, "start_workflow", lambda **_: pytest.fail("resume started a new run")
    )
    assert cli.main(["resume", "run"]) == 1
    assert json.loads(capsys.readouterr().out)["next_step"] == step


def test_resume_timeout_is_bounded_and_resumable(monkeypatch, capsys):
    now = [100.0]
    snapshot = {"run_dir": "run", "status": "generation", "next_step": "advance"}
    calls = []
    monkeypatch.setattr(cli.workflow, "workflow_status", lambda _: snapshot)
    monkeypatch.setattr(
        cli.workflow, "advance_workflow", lambda _: calls.append("advance") or snapshot
    )
    monkeypatch.setattr(cli.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    assert cli.main(["resume", "run", "--timeout", "3", "--poll-interval", "2"]) == 3
    result = json.loads(capsys.readouterr().out)
    assert result["error"]["code"] == "timeout"
    assert result["run_dir"] == "run"
    assert len(calls) == 2
    assert now[0] == 103.0


def test_no_download_leaves_finished_run_available(monkeypatch, capsys):
    snapshot = {"run_dir": "run", "status": "succeeded", "next_step": "download"}
    monkeypatch.setattr(cli.workflow, "workflow_status", lambda _: snapshot)
    monkeypatch.setattr(
        cli.workflow, "download_workflow", lambda _: pytest.fail("download was disabled")
    )
    assert cli.main(["resume", "run", "--no-download"]) == 0
    assert json.loads(capsys.readouterr().out)["next_step"] == "download"


@pytest.mark.parametrize("interrupted", [False, True])
def test_poll_errors_keep_run_directory_and_latest_saved_state(monkeypatch, capsys, interrupted):
    snapshot = {"run_dir": "run", "status": "generation", "next_step": "advance"}
    saved = {
        "run_dir": "run",
        "status": "submission_uncertain",
        "next_step": "submission_uncertain",
    }
    statuses = iter([snapshot, saved])
    monkeypatch.setattr(cli.workflow, "workflow_status", lambda _: next(statuses))

    def advance(_):
        if interrupted:
            raise KeyboardInterrupt
        raise cli.MeshyError("Temporary network failure")

    monkeypatch.setattr(cli.workflow, "advance_workflow", advance)
    assert cli.main(["resume", "run"]) == (130 if interrupted else 2)
    result = json.loads(capsys.readouterr().out)
    assert result["run_dir"] == "run"
    assert result["workflow"]["next_step"] == "submission_uncertain"


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_invalid_polling_arguments_do_not_start_task(monkeypatch, capsys, value):
    monkeypatch.setattr(
        cli.workflow, "start_workflow", lambda **_: pytest.fail("invalid command submitted a task")
    )
    assert cli.main(["run", *VIEWS, "--timeout", value]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_arguments"


def test_errors_never_expose_secret_or_traceback(monkeypatch, capsys):
    monkeypatch.setenv("MESHY_API_KEY", "secret-api-token")

    def fail():
        raise ValueError(
            "Invalid secret-api-token Bearer another-secret https://host/file?signature=private"
        )

    monkeypatch.setattr(cli.workflow, "doctor", fail)
    assert cli.main(["doctor"]) == 2
    output = capsys.readouterr()
    for secret in ("secret-api-token", "another-secret", "signature=private", "Traceback"):
        assert secret not in output.out + output.err
    assert json.loads(output.out)["ok"] is False


def test_unexpected_errors_return_generic_message():
    result = cli.error_result(RuntimeError("private exception details"))
    assert result["error"]["code"] == "internal_error"
    assert "private" not in json.dumps(result)


def test_list_closes_client_when_request_fails(monkeypatch):
    closed = []

    class Client:
        def list_tasks(self, kind, *, limit):
            assert kind == "remesh"
            assert limit == 2
            raise ValueError("request failed")

        def close(self):
            closed.append(True)

    monkeypatch.setattr(cli, "MeshyClient", Client)
    with pytest.raises(ValueError, match="request failed"):
        cli.list_tasks("remesh", 2)
    assert closed == [True]


def test_mcp_registers_expected_tools_with_paid_action_annotations():
    tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}
    assert set(tools) == {
        "meshy_doctor",
        "meshy_plan_multiview",
        "meshy_start_multiview",
        "meshy_advance_workflow",
        "meshy_workflow_status",
        "meshy_download_workflow",
        "meshy_recover_submission",
        "meshy_list_tasks",
    }
    for name in ("meshy_start_multiview", "meshy_advance_workflow"):
        assert tools[name].annotations.readOnlyHint is False
        assert tools[name].annotations.idempotentHint is False
        assert "PAID" in tools[name].description
    assert tools["meshy_workflow_status"].annotations.openWorldHint is False
    assert tools["meshy_list_tasks"].annotations.readOnlyHint is True
    schema = tools["meshy_start_multiview"].inputSchema
    assert set(schema["required"]) == {"front", "back", "left", "right", "output_dir"}


def test_mcp_advance_calls_workflow_once(monkeypatch):
    calls = []
    monkeypatch.setattr(
        server.workflow,
        "advance_workflow",
        lambda directory: calls.append(directory) or {"next_step": "advance"},
    )
    assert server.meshy_advance_workflow("run") == {"next_step": "advance"}
    assert calls == ["run"]


def test_mcp_returns_sanitized_failure(monkeypatch):
    def fail(_):
        raise RuntimeError("sensitive transport details")

    monkeypatch.setattr(server.workflow, "advance_workflow", fail)
    result = server.meshy_advance_workflow("run")
    assert result["ok"] is False
    assert "sensitive" not in json.dumps(result)
