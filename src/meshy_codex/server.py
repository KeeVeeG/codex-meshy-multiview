"""Short, resumable MCP tools for the Meshy four-view workflow."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import workflow
from .cli import list_tasks, safe_call

mcp = FastMCP(
    "Meshy Multi-View for Codex",
    instructions=(
        "Create a textured 3D model from front, back, left, and right images, then create "
        "an adaptive low-poly remesh. Start submits a paid generation task. Advance can "
        "submit a paid remesh when generation succeeds. Use plan before starting. "
        "Call advance separately to check progress; tools never wait for remote completion. "
        "Save run_dir from each response. If submission is uncertain, do not repeat start "
        "or create another workflow: inspect existing tasks and recover the verified ID."
    ),
    log_level="WARNING",
)

_LOCAL_READ = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
_REMOTE_READ = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
_PAID_WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
)
_LOCAL_WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
)


@mcp.tool(annotations=_LOCAL_READ)
def meshy_doctor() -> dict[str, Any]:
    """Check whether local Meshy credentials are configured, without exposing them or calling the API."""
    return safe_call(workflow.doctor)


@mcp.tool(annotations=_LOCAL_READ)
def meshy_plan_multiview(
    front: str,
    back: str,
    left: str,
    right: str,
    output_dir: str,
    texture_prompt: str | None = None,
) -> dict[str, Any]:
    """Validate four image paths/HTTPS URLs and preview redacted requests. No paid task is submitted."""
    return safe_call(
        workflow.plan_workflow, front, back, left, right, output_dir, texture_prompt=texture_prompt
    )


@mcp.tool(annotations=_PAID_WRITE)
def meshy_start_multiview(
    front: str,
    back: str,
    left: str,
    right: str,
    output_dir: str,
    texture_prompt: str | None = None,
) -> dict[str, Any]:
    """Submit one PAID textured Multi-Image to 3D task using four views; return the saved run directory.

    Local images are sent to Meshy. Continue this run with meshy_advance_workflow.
    Do not repeat start after an uncertain submission; inspect tasks and recover its ID.
    """
    return safe_call(
        workflow.start_workflow, front, back, left, right, output_dir, texture_prompt=texture_prompt
    )


@mcp.tool(annotations=_PAID_WRITE)
def meshy_advance_workflow(run_dir: str) -> dict[str, Any]:
    """Check progress once and submit PAID adaptive low-poly remesh when generation succeeds.

    Returns promptly without polling. Saved IDs prevent resubmitting completed stages.
    An uncertain submission requires recovery, never a repeat submission or a new run.
    """
    return safe_call(workflow.advance_workflow, run_dir)


@mcp.tool(annotations=_LOCAL_READ)
def meshy_workflow_status(run_dir: str) -> dict[str, Any]:
    """Read a saved workflow and its next step. Local only; does not refresh remote task status."""
    return safe_call(workflow.workflow_status, run_dir)


@mcp.tool(annotations=_LOCAL_WRITE)
def meshy_download_workflow(run_dir: str) -> dict[str, Any]:
    """Download completed model and texture artifacts into the saved run directory; submits no paid tasks."""
    return safe_call(workflow.download_workflow, run_dir)


@mcp.tool(annotations=_LOCAL_WRITE)
def meshy_recover_submission(
    run_dir: str, stage: Literal["generation", "remesh"], task_id: str
) -> dict[str, Any]:
    """Attach a verified existing task ID after an uncertain submission. Never creates a task.

    Inspect Meshy task history first and select the task belonging to this exact run and stage.
    """
    return safe_call(workflow.recover_submission, run_dir, stage, task_id)


@mcp.tool(annotations=_REMOTE_READ)
def meshy_list_tasks(
    kind: Literal["multi-image-to-3d", "remesh"], limit: int = 10
) -> dict[str, Any]:
    """List up to 100 existing Meshy tasks for inspection or uncertain-submission recovery; read only."""
    return safe_call(list_tasks, kind, limit)


def main() -> None:
    """Run the MCP server using stdio, reserving stdout for protocol messages."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
