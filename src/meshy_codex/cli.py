"""Command-line access to the resumable Meshy workflow."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from collections.abc import Callable, Sequence
from typing import Any

from . import workflow
from .client import MeshyClient, MeshyError


class CLIUsageError(ValueError):
    """An invalid command line, reported without a traceback."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CLIUsageError(message)


def error_result(error: Exception) -> dict[str, Any]:
    """Build a compact error without exposing unexpected exception contents."""
    if isinstance(error, CLIUsageError):
        code = "invalid_arguments"
    elif isinstance(error, MeshyError):
        code = "meshy_error"
    elif isinstance(error, workflow.WorkflowError):
        code = "workflow_error"
    elif isinstance(error, ValueError):
        code = "invalid_configuration"
    elif isinstance(error, OSError):
        code = "filesystem_error"
    else:
        return {
            "ok": False,
            "error": {
                "code": "internal_error",
                "message": "Unexpected failure. Inspect the saved workflow before retrying.",
            },
        }
    message = str(error)
    api_key = os.environ.get("MESHY_API_KEY")
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    message = re.sub(r"(?i)bearer\s+[^\s,;]+", "Bearer [REDACTED]", message)
    message = re.sub(r"data:[^\s]+", "[REDACTED DATA URI]", message)
    message = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[REDACTED]", message)
    message = " ".join(message.split())[:500]
    return {"ok": False, "error": {"code": code, "message": message or code}}


def safe_call(
    function: Callable[..., dict[str, Any]], /, *args: Any, **kwargs: Any
) -> dict[str, Any]:
    """Call an interface operation and return sanitized structured failures."""
    try:
        return function(*args, **kwargs)
    except Exception as error:
        return error_result(error)


def list_tasks(kind: str, limit: int = 10) -> dict[str, Any]:
    """List remote tasks without submitting or changing them."""
    if kind not in {"multi-image-to-3d", "remesh"}:
        raise ValueError("kind must be multi-image-to-3d or remesh")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    client = MeshyClient()
    try:
        result = client.list_tasks(kind, limit=limit)
        return {"kind": kind, "tasks": result}
    finally:
        client.close()


def _positive_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive number of seconds") from error
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("must be a finite, positive number of seconds")
    return result


def _limit(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer between 1 and 100") from error
    if not 1 <= result <= 100:
        raise argparse.ArgumentTypeError("must be between 1 and 100")
    return result


def _add_inputs(parser: argparse.ArgumentParser) -> None:
    for view in ("front", "back", "left", "right"):
        parser.add_argument(
            f"--{view}", required=True, help=f"{view.title()} view: local image or HTTPS URL"
        )
    parser.add_argument("--output", required=True, help="Directory for the new resumable workflow")
    parser.add_argument("--texture-prompt", help="Optional guidance for texture generation")


def _add_polling(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=1800,
        help="Polling time limit in seconds (default: 1800)",
    )
    parser.add_argument(
        "--poll-interval",
        type=_positive_float,
        default=10,
        help="Seconds between status checks (default: 10)",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Stop when remesh finishes; download artifacts separately",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="codex-meshy-multiview",
        description="Generate a textured Meshy model from four views, then create an adaptive low-poly remesh.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check local credential configuration without calling Meshy")
    _add_inputs(
        commands.add_parser(
            "plan", help="Validate inputs and preview the workflow without submitting paid tasks"
        )
    )
    _add_inputs(
        commands.add_parser("start", help="Submit one paid textured Multi-Image to 3D task")
    )
    run = commands.add_parser(
        "run", help="Submit generation, poll, submit remesh, and download the results"
    )
    _add_inputs(run)
    _add_polling(run)
    resume = commands.add_parser(
        "resume", help="Continue polling an existing workflow without resubmitting generation"
    )
    resume.add_argument("run_dir", help="Existing workflow directory")
    _add_polling(resume)
    for name, help_text in (
        ("advance", "Check the current task once; submit paid remesh when generation succeeds"),
        ("status", "Read the saved workflow without making API requests"),
        ("download", "Download available artifacts for a completed workflow"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("run_dir", help="Existing workflow directory")
    recover = commands.add_parser(
        "recover",
        help="Attach a verified task ID after an uncertain submission; never creates a task",
    )
    recover.add_argument("run_dir", help="Existing workflow directory")
    recover.add_argument("--stage", choices=("generation", "remesh"), required=True)
    recover.add_argument(
        "--task-id", required=True, help="Existing Meshy task ID, verified in task history"
    )
    listing = commands.add_parser(
        "list", help="List existing Meshy tasks for inspection and recovery"
    )
    listing.add_argument("--kind", choices=("multi-image-to-3d", "remesh"), required=True)
    listing.add_argument("--limit", type=_limit, default=10)
    return parser


def _inputs(arguments: argparse.Namespace) -> dict[str, Any]:
    return {
        "front": arguments.front,
        "back": arguments.back,
        "left": arguments.left,
        "right": arguments.right,
        "output_dir": arguments.output,
        "texture_prompt": arguments.texture_prompt,
    }


def _progress(snapshot: dict[str, Any]) -> None:
    # Do not print remote error details, signed URLs, or image data to stderr.
    stage = snapshot.get("status", "working")
    if stage not in {
        "generation",
        "remesh",
        "succeeded",
        "failed",
        "submission_uncertain",
        "submission_failed",
    }:
        stage = "working"
    step = snapshot.get("next_step", "unknown")
    if step not in {
        "advance",
        "download",
        "complete",
        "failed",
        "submission_uncertain",
        "submission_failed",
    }:
        step = "unknown"
    print(f"Workflow: {stage}; next step: {step}", file=sys.stderr, flush=True)


def _poll(
    snapshot: dict[str, Any], *, timeout: float, interval: float, download: bool
) -> tuple[dict[str, Any], int]:
    deadline = time.monotonic() + timeout
    run_dir = snapshot["run_dir"]
    try:
        while True:
            _progress(snapshot)
            step = snapshot.get("next_step")
            if step == "download":
                return (workflow.download_workflow(run_dir) if download else snapshot), 0
            if step == "complete":
                return snapshot, 0
            if step in {"failed", "submission_uncertain", "submission_failed"}:
                return snapshot, 1
            if snapshot.get("ok") is False:
                return snapshot, 1
            if step != "advance":
                return {
                    "ok": False,
                    "run_dir": run_dir,
                    "error": {
                        "code": "unexpected_state",
                        "message": "The workflow cannot advance from its saved state.",
                    },
                    "workflow": snapshot,
                }, 1
            if time.monotonic() >= deadline:
                return {
                    "ok": False,
                    "run_dir": run_dir,
                    "error": {
                        "code": "timeout",
                        "message": "Polling timed out. Resume this run directory to continue; remote tasks are not canceled.",
                    },
                    "workflow": snapshot,
                }, 3
            snapshot = workflow.advance_workflow(run_dir)
            if snapshot.get("next_step") == "advance":
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(min(interval, remaining))
    except KeyboardInterrupt:
        result, exit_code = _interrupted_result(), 130
    except Exception as error:
        result, exit_code = error_result(error), 2
    result["run_dir"] = run_dir
    # Read the durable state in case a remesh submission was interrupted after
    # saving its intent, so the caller sees the no-retry recovery instruction.
    try:
        result["workflow"] = workflow.workflow_status(run_dir)
    except Exception:
        pass
    return result, exit_code


def _dispatch(arguments: argparse.Namespace) -> tuple[dict[str, Any], int]:
    command = arguments.command
    if command == "doctor":
        return workflow.doctor(), 0
    if command == "plan":
        return workflow.plan_workflow(**_inputs(arguments)), 0
    if command in {"start", "run"}:
        snapshot = workflow.start_workflow(**_inputs(arguments))
        if command == "start":
            return snapshot, _state_exit_code(snapshot)
        return _poll(
            snapshot,
            timeout=arguments.timeout,
            interval=arguments.poll_interval,
            download=not arguments.no_download,
        )
    if command == "resume":
        return _poll(
            workflow.workflow_status(arguments.run_dir),
            timeout=arguments.timeout,
            interval=arguments.poll_interval,
            download=not arguments.no_download,
        )
    if command == "recover":
        result = workflow.recover_submission(arguments.run_dir, arguments.stage, arguments.task_id)
    elif command == "list":
        result = list_tasks(arguments.kind, arguments.limit)
    else:
        operation = {
            "advance": workflow.advance_workflow,
            "status": workflow.workflow_status,
            "download": workflow.download_workflow,
        }[command]
        result = operation(arguments.run_dir)
    return result, _state_exit_code(result)


def _state_exit_code(result: dict[str, Any]) -> int:
    return int(
        result.get("ok") is False
        or result.get("next_step") in {"failed", "submission_uncertain", "submission_failed"}
    )


def _interrupted_result() -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": "interrupted",
            "message": "Operation interrupted. Remote tasks are not canceled; inspect the saved workflow before retrying.",
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Write one final JSON result to stdout; all progress goes to stderr."""
    try:
        arguments = build_parser().parse_args(argv)
        result, exit_code = _dispatch(arguments)
    except KeyboardInterrupt:
        result = _interrupted_result()
        exit_code = 130
    except Exception as error:
        result, exit_code = error_result(error), 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
