import json
from pathlib import Path

import pytest
from filelock import FileLock

from meshy_codex import workflow
from meshy_codex.client import MeshyError, SubmissionUncertain


class FakeClient:
    created = []
    calls = []
    tasks = {}
    fail_stage = None

    def create_multi_image(self, images, **kwargs):
        self.created.append("generation")
        if self.fail_stage == "generation":
            raise SubmissionUncertain("Lost response")
        return "generation-id"

    def create_remesh(self, model_url):
        assert model_url == "https://assets.meshy.ai/original.glb"
        self.created.append("remesh")
        if self.fail_stage == "remesh":
            raise SubmissionUncertain("Lost response")
        return "remesh-id"

    def get_task(self, kind, task_id):
        self.calls.append((kind, task_id))
        return self.tasks[task_id]

    def close(self):
        pass


@pytest.fixture
def client(monkeypatch):
    FakeClient.created, FakeClient.calls, FakeClient.tasks = [], [], {}
    FakeClient.fail_stage = None
    monkeypatch.setattr(workflow, "MeshyClient", FakeClient)
    monkeypatch.setattr(workflow, "prepare_images", lambda sources: sources)
    return FakeClient


def start(tmp_path):
    return workflow.start_workflow("front.png", "back.png", "left.png", "right.png", str(tmp_path))


def succeeded(task_id, url):
    return {"id": task_id, "status": "SUCCEEDED", "progress": 100, "model_urls": {"glb": url}}


def test_full_transition_and_repeat_advance_never_duplicates(client, tmp_path):
    first = start(tmp_path)
    run = first["run_dir"]
    client.tasks["generation-id"] = {"status": "IN_PROGRESS", "progress": 41}
    assert workflow.advance_workflow(run)["generation"]["progress"] == 41
    client.tasks["generation-id"] = succeeded(
        "generation-id", "https://assets.meshy.ai/original.glb"
    )
    assert workflow.advance_workflow(run)["status"] == "remesh"
    client.tasks["remesh-id"] = succeeded("remesh-id", "https://assets.meshy.ai/final.glb")
    assert workflow.advance_workflow(run)["next_step"] == "download"
    for _ in range(3):
        assert workflow.advance_workflow(run)["next_step"] == "download"
    assert client.created == ["generation", "remesh"]


@pytest.mark.parametrize("stage", ["generation", "remesh"])
def test_uncertain_submission_stops_and_recovers_without_post(client, tmp_path, stage):
    client.fail_stage = stage
    result = start(tmp_path)
    run = result["run_dir"]
    if stage == "remesh":
        client.tasks["generation-id"] = succeeded(
            "generation-id", "https://assets.meshy.ai/original.glb"
        )
        result = workflow.advance_workflow(run)
    assert result["next_step"] == "submission_uncertain"
    before = list(client.created)
    assert workflow.advance_workflow(run)["next_step"] == "submission_uncertain"
    task_id = f"{stage}-recovered"
    client.tasks[task_id] = {"id": task_id, "status": "IN_PROGRESS"}
    recovered = workflow.recover_submission(run, stage, task_id)
    assert recovered[stage]["id"] == task_id
    assert recovered["next_step"] == "advance"
    assert client.created == before


def test_crash_after_saving_intent_blocks_repetition(client, tmp_path):
    result = start(tmp_path)
    state_path = Path(result["run_dir"]) / "workflow.json"
    state = json.loads(state_path.read_text())
    state["submission"]["status"] = "submitting"
    state_path.write_text(json.dumps(state))
    assert workflow.advance_workflow(result["run_dir"])["next_step"] == "submission_uncertain"
    assert client.created == ["generation"]
    assert client.calls == []


def test_task_failure_does_not_create_remesh(client, tmp_path):
    result = start(tmp_path)
    client.tasks["generation-id"] = {
        "status": "FAILED",
        "task_error": {"message": "provider error"},
    }
    assert workflow.advance_workflow(result["run_dir"])["next_step"] == "failed"
    assert client.created == ["generation"]


def test_invalid_remesh_source_does_not_record_submission(client, tmp_path):
    result = start(tmp_path)
    client.tasks["generation-id"] = succeeded("generation-id", "http://invalid.example/model.glb")
    with pytest.raises(ValueError, match="HTTPS"):
        workflow.advance_workflow(result["run_dir"])
    saved = workflow.workflow_status(result["run_dir"])
    assert saved["next_step"] == "advance"
    assert saved["submission"]["stage"] == "generation"
    assert saved["submission"]["status"] == "accepted"
    assert client.created == ["generation"]


def test_rejected_post_is_saved_not_retried(client, tmp_path, monkeypatch):
    def reject(*args, **kwargs):
        raise MeshyError("Insufficient credits")

    monkeypatch.setattr(FakeClient, "create_multi_image", reject)
    result = start(tmp_path)
    assert result["next_step"] == "submission_failed"
    assert workflow.advance_workflow(result["run_dir"])["next_step"] == "submission_failed"


def test_local_status_needs_no_credentials_and_hides_response(client, tmp_path):
    result = start(tmp_path)
    result = workflow.workflow_status(result["run_dir"])
    assert result["generation"]["id"] == "generation-id"
    assert "response" not in result["generation"]
    assert client.calls == []


def test_other_process_lock_blocks_advance(client, tmp_path):
    result = start(tmp_path)
    with FileLock(Path(result["run_dir"]) / ".workflow.lock"):
        with pytest.raises(workflow.WorkflowError, match="busy"):
            workflow.advance_workflow(result["run_dir"])
    assert client.calls == []


def test_plan_makes_no_client_and_validates_prompt(client, tmp_path):
    result = workflow.plan_workflow("f", "b", "l", "r", str(tmp_path))
    assert result["submitted"] is False
    assert result["generation"]["texture_guidance"] == "four_views"
    with pytest.raises(workflow.WorkflowError):
        workflow.plan_workflow("f", "b", "l", "r", str(tmp_path), texture_prompt="x" * 801)
    assert client.created == []


def test_doctor_does_not_echo_secret(monkeypatch, tmp_path):
    keyfile = tmp_path / "key"
    keyfile.write_text("private-secret-value")
    monkeypatch.delenv("MESHY_API_KEY", raising=False)
    monkeypatch.setenv("MESHY_API_KEY_FILE", str(keyfile))
    result = workflow.doctor()
    assert result["api_key_source"] == "file"
    assert "private-secret-value" not in json.dumps(result)
