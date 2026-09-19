"""Persist paid submissions before sending them; resume by task ID, never by repetition."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock, Timeout

from .client import MeshyClient, MeshyError, SubmissionUncertain
from .images import prepare_images, validate_https_url
from .inspect_glb import inspect_glb

KINDS = {"generation": "multi-image-to-3d", "remesh": "remesh"}
TERMINAL_FAILURES = {"FAILED", "CANCELED", "CANCELLED", "EXPIRED"}


class WorkflowError(RuntimeError):
    """A workflow cannot safely proceed."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save(directory: Path, state: dict) -> None:
    state["updated_at"] = _now()
    fd, name = tempfile.mkstemp(prefix=".workflow-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, directory / "workflow.json")
    finally:
        Path(name).unlink(missing_ok=True)


def _load(directory: Path) -> dict:
    try:
        state = json.loads((directory / "workflow.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkflowError("Cannot read workflow.json in the supplied run directory.") from exc
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise WorkflowError("Unsupported workflow state format.")
    return state


@contextmanager
def _locked(directory: Path):
    if not directory.is_dir():
        raise WorkflowError("The run directory does not exist.")
    try:
        with FileLock(directory / ".workflow.lock", timeout=0):
            yield
    except Timeout as exc:
        raise WorkflowError("This workflow is busy in another process; retry later.") from exc


def _summary(directory: Path, state: dict) -> dict:
    status = state["status"]
    pending = state.get("submission", {}).get("status") in {"submitting", "uncertain"}
    if pending:
        status = "submission_uncertain"
    next_step = {
        "generation": "advance",
        "remesh": "advance",
        "succeeded": "download",
        "failed": "failed",
        "submission_uncertain": "submission_uncertain",
        "submission_failed": "submission_failed",
    }[status]
    if state.get("downloaded"):
        next_step = "complete"
    result = {"run_dir": str(directory), "status": status, "next_step": next_step}
    for stage in KINDS:
        if stage in state:
            result[stage] = {k: v for k, v in state[stage].items() if k != "response"}
    for field in ("submission", "error", "artifacts", "validation", "warnings"):
        if field in state:
            result[field] = state[field]
    return result


def doctor() -> dict:
    """Report credential presence without sending a network request or returning its value."""
    direct = bool(os.getenv("MESHY_API_KEY", "").strip())
    file_name = os.getenv("MESHY_API_KEY_FILE", "").strip()
    readable = False
    if not direct and file_name:
        try:
            readable = bool(Path(file_name).expanduser().read_text(encoding="utf-8").strip())
        except (OSError, UnicodeError):
            pass
    return {
        "api_key_configured": direct or readable,
        "api_key_source": "environment" if direct else "file" if readable else None,
        "api_key_file_configured": bool(file_name),
        "network_checked": False,
        "ai_model": "meshy-7.1",
        "decimation_mode": 4,
    }


def plan_workflow(
    front: str,
    back: str,
    left: str,
    right: str,
    output_dir: str,
    *,
    texture_prompt: str | None = None,
) -> dict:
    """Validate four inputs without uploading them or requiring API credentials."""
    prepare_images([front, right, back, left])
    if texture_prompt is not None and (not texture_prompt.strip() or len(texture_prompt) > 800):
        raise WorkflowError("Texture prompt must contain 1 to 800 characters.")
    if not output_dir.strip():
        raise WorkflowError("An explicit output directory is required.")
    return {
        "output_dir": str(Path(output_dir).expanduser().resolve()),
        "image_count": 4,
        "view_order": ["front", "right", "back", "left"],
        "generation": {
            "ai_model": "meshy-7.1",
            "should_texture": True,
            "enable_pbr": True,
            "should_remesh": False,
            "texture_guidance": "prompt" if texture_prompt else "four_views",
            "target_formats": ["glb"],
        },
        "remesh": {"topology": "triangle", "decimation_mode": 4, "target_formats": ["glb"]},
        "paid_submissions": 2,
        "submitted": False,
    }


def _submit(
    directory: Path,
    state: dict,
    client: MeshyClient,
    stage: str,
    images: list[str] | None = None,
    texture_prompt: str | None = None,
) -> None:
    if stage == "remesh":
        # Reject invalid provider output before recording an intent to submit.
        validate_https_url(state["generation"]["response"]["model_urls"]["glb"])
    # An interrupted save or POST must leave a durable intent that prevents duplicate charges.
    state["submission"] = {"stage": stage, "status": "submitting", "started_at": _now()}
    _save(directory, state)
    try:
        if stage == "generation":
            task_id = client.create_multi_image(images, texture_prompt=texture_prompt)
        else:
            task_id = client.create_remesh(state["generation"]["response"]["model_urls"]["glb"])
    except SubmissionUncertain:
        state["status"] = "submission_uncertain"
        state["submission"]["status"] = "uncertain"
        state["error"] = "Submission outcome is unknown. Find the existing task and recover its ID."
    except (MeshyError, ValueError) as exc:
        # Client ValueError is guaranteed to mean preflight rejection, before HTTP POST.
        state["status"] = "submission_failed"
        state["submission"]["status"] = "rejected"
        state["error"] = str(exc)
    else:
        state[stage] = {"id": task_id, "status": "PENDING"}
        state["status"] = stage
        state["submission"]["status"] = "accepted"
        state.pop("error", None)
    _save(directory, state)


def start_workflow(
    front: str,
    back: str,
    left: str,
    right: str,
    output_dir: str,
    *,
    texture_prompt: str | None = None,
) -> dict:
    """Submit one paid generation task; this is intentionally not a retry operation."""
    plan = plan_workflow(front, back, left, right, output_dir, texture_prompt=texture_prompt)
    # Snapshot local bytes before creating any paid task, preventing mid-submission file changes.
    images = prepare_images([front, right, back, left])
    client = MeshyClient()
    try:
        directory = Path(plan["output_dir"]) / ("meshy-" + uuid.uuid4().hex)
        directory.mkdir(parents=True, exist_ok=False)
        state = {"schema_version": 1, "created_at": _now(), "status": "generation", "plan": plan}
        with _locked(directory):
            _submit(directory, state, client, "generation", images, texture_prompt)
        return _summary(directory, state)
    finally:
        client.close()


def workflow_status(run_dir: str) -> dict:
    """Read the last saved state; no network calls or paid submissions."""
    directory = Path(run_dir).expanduser().resolve()
    return _summary(directory, _load(directory))


def advance_workflow(run_dir: str) -> dict:
    """Poll once and, after generation succeeds, submit Adaptive Low remesh exactly once."""
    directory = Path(run_dir).expanduser().resolve()
    with _locked(directory):
        state = _load(directory)
        if _summary(directory, state)["next_step"] != "advance":
            return _summary(directory, state)
        stage = state["status"]
        client = MeshyClient()
        try:
            task = client.get_task(KINDS[stage], state[stage]["id"])
            status = task.get("status")
            if status not in {"PENDING", "IN_PROGRESS", "SUCCEEDED"} | TERMINAL_FAILURES:
                raise WorkflowError(
                    "Meshy returned an unknown task status; no new task was submitted."
                )
            state[stage].update(status=status, progress=task.get("progress"), response=task)
            if status in TERMINAL_FAILURES:
                state["status"] = "failed"
                state["error"] = (
                    f"Meshy {stage} task ended with {status}. Inspect the task in Meshy."
                )
            elif status == "SUCCEEDED":
                if not task.get("model_urls", {}).get("glb"):
                    raise WorkflowError("Succeeded task has no GLB URL; no new task was submitted.")
                if stage == "generation":
                    _submit(directory, state, client, "remesh")
                else:
                    state["status"] = "succeeded"
            _save(directory, state)
            return _summary(directory, state)
        finally:
            client.close()


def recover_submission(run_dir: str, stage: str, task_id: str) -> dict:
    """Attach a user-identified existing task to an interrupted submission, without POST."""
    if stage not in KINDS:
        raise WorkflowError("Stage must be generation or remesh.")
    directory = Path(run_dir).expanduser().resolve()
    with _locked(directory):
        state = _load(directory)
        submission = state.get("submission", {})
        if submission.get("stage") != stage or submission.get("status") not in {
            "submitting",
            "uncertain",
        }:
            raise WorkflowError("Only the matching uncertain submission can be recovered.")
        client = MeshyClient()
        try:
            task = client.get_task(KINDS[stage], task_id)
        finally:
            client.close()
        if task.get("id") != task_id:
            raise WorkflowError("Meshy task ID did not match the requested recovery ID.")
        state[stage] = {"id": task_id, "status": task.get("status"), "response": task}
        state["status"] = stage
        state["submission"]["status"] = "accepted"
        state.pop("error", None)
        _save(directory, state)
        return _summary(directory, state)


def download_workflow(run_dir: str) -> dict:
    """Download both GLBs and inspect actual texture bindings and triangle counts."""
    directory = Path(run_dir).expanduser().resolve()
    with _locked(directory):
        state = _load(directory)
        if state["status"] != "succeeded":
            raise WorkflowError(
                "Both generation and remesh must succeed before downloading this workflow."
            )
        client = MeshyClient()
        try:
            state.setdefault("artifacts", {})
            state.setdefault("validation", {})
            warnings = []
            for stage in KINDS:
                # Fetch fresh signed URLs; saved URLs can expire between sessions.
                task = client.get_task(KINDS[stage], state[stage]["id"])
                files = client.download_task(task, directory / stage)
                state["artifacts"][stage] = files
                inspection = inspect_glb(Path(files["model.glb"]))
                state["validation"][stage] = inspection
                if not inspection["has_embedded_base_color_texture"]:
                    warnings.append(
                        f"{stage}: no embedded base-color texture binding was verified."
                    )
                _save(directory, state)
            original = state["validation"]["generation"]["triangles"]
            reduced = state["validation"]["remesh"]["triangles"]
            if original and reduced >= original:
                warnings.append(
                    "Remesh triangle count is not lower than the original; review the model."
                )
            state["warnings"] = warnings
            state["downloaded"] = True
            _save(directory, state)
            return _summary(directory, state)
        finally:
            client.close()
