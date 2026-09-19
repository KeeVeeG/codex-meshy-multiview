"""Exercise the persisted workflow through the real client, with no network traffic."""

import base64
import json
import struct
import zlib
from pathlib import Path

import httpx
import pytest

from meshy_codex import workflow
from meshy_codex.client import MeshyClient


def _png() -> bytes:
    def chunk(kind, payload):
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff\xff"))
        + chunk(b"IEND", b"")
    )


def _textured_glb(triangles: int) -> bytes:
    positions = struct.pack("<12f", 0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0)
    uvs = struct.pack("<8f", 0, 0, 1, 0, 1, 1, 0, 1)
    indices = struct.pack("<" + "H" * (3 * triangles), *(0, 1, 2, 0, 2, 3)[: 3 * triangles])
    payload = bytearray()
    views = []
    for part in (positions, uvs, indices, _png()):
        payload.extend(b"\x00" * (-len(payload) % 4))
        views.append({"buffer": 0, "byteOffset": len(payload), "byteLength": len(part)})
        payload.extend(part)
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "buffers": [{"byteLength": len(payload)}],
        "bufferViews": views,
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 4,
                "type": "VEC3",
                "min": [0, 0, 0],
                "max": [1, 1, 0],
            },
            {"bufferView": 1, "componentType": 5126, "count": 4, "type": "VEC2"},
            {"bufferView": 2, "componentType": 5123, "count": 3 * triangles, "type": "SCALAR"},
        ],
        "meshes": [
            {
                "primitives": [
                    {"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0}
                ]
            }
        ],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
        "textures": [{"source": 0}],
        "images": [{"bufferView": 3, "mimeType": "image/png"}],
    }
    encoded = json.dumps(document).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    payload.extend(b"\x00" * (-len(payload) % 4))
    length = 12 + 8 + len(encoded) + 8 + len(payload)
    return (
        struct.pack("<4sII", b"glTF", 2, length)
        + struct.pack("<II", len(encoded), 0x4E4F534A)
        + encoded
        + struct.pack("<II", len(payload), 0x004E4942)
        + payload
    )


class MeshyService:
    """Model accepted tasks separately from potentially lost HTTP responses."""

    def __init__(self, lost_stage=None):
        self.lost_stage = lost_stage
        self.submissions = {"generation": 0, "remesh": 0}
        self.requests = []
        self.original = _textured_glb(2)
        self.reduced = _textured_glb(1)

    def task(self, stage):
        return {
            "id": f"{stage}-1",
            "status": "SUCCEEDED",
            "progress": 100,
            "model_urls": {"glb": f"https://assets.example/{stage}.glb?signature=signed-download"},
            "texture_urls": [{"base_color": f"https://assets.example/{stage}.png"}],
            "thumbnail_url": f"https://assets.example/{stage}-preview.png",
        }

    def __call__(self, request):
        self.requests.append(request)
        if request.url.host == "assets.example":
            assert "authorization" not in request.headers
            assert "cookie" not in request.headers
            if request.url.path == "/generation.glb":
                return httpx.Response(200, content=self.original)
            if request.url.path == "/remesh.glb":
                return httpx.Response(200, content=self.reduced)
            return httpx.Response(200, content=_png())
        assert request.url.host == "api.meshy.ai"
        assert request.headers["Authorization"] == "Bearer integration-secret"
        kind = request.url.path.removeprefix("/openapi/v1/").split("/")[0]
        stage = "generation" if kind == "multi-image-to-3d" else "remesh"
        if request.method == "POST":
            self.submissions[stage] += 1
            payload = json.loads(request.content)
            if stage == "generation":
                assert len(payload["image_urls"]) == 4
                assert payload["image_urls"] == payload["texture_image_urls"]
                assert all(
                    url.startswith("data:image/png;base64,") for url in payload["image_urls"]
                )
                assert payload["should_texture"] and payload["enable_pbr"]
                assert not payload["should_remesh"]
            else:
                assert payload == {
                    "model_url": self.task("generation")["model_urls"]["glb"],
                    "topology": "triangle",
                    "decimation_mode": 4,
                    "target_formats": ["glb"],
                }
            if self.lost_stage == stage:
                self.lost_stage = None
                raise httpx.ReadTimeout("server accepted task; response lost", request=request)
            return httpx.Response(200, json={"result": f"{stage}-1"})
        if request.url.path.endswith(f"{stage}-1"):
            assert self.submissions[stage] == 1
            return httpx.Response(200, json=self.task(stage))
        return httpx.Response(200, json=[self.task(stage)] if self.submissions[stage] else [])


def _inputs(tmp_path):
    # Different data after the valid PNG makes input order observable independently
    # of filenames, while preserving a real, decodable PNG image.
    inputs = {}
    for view in ("front", "back", "left", "right"):
        path = tmp_path / f"{view}.png"
        path.write_bytes(_png() + view.encode())
        inputs[view] = str(path)
    return inputs | {"output_dir": str(tmp_path / "runs")}


def test_complete_workflow_through_real_http_client(tmp_path, monkeypatch):
    service = MeshyService()
    with httpx.Client(transport=httpx.MockTransport(service)) as http:
        monkeypatch.setattr(
            workflow, "MeshyClient", lambda: MeshyClient("integration-secret", http)
        )
        inputs = _inputs(tmp_path)
        plan = workflow.plan_workflow(**inputs)
        assert not plan["submitted"]
        assert service.requests == []
        started = workflow.start_workflow(**inputs)
        run_dir = started["run_dir"]
        assert service.submissions == {"generation": 1, "remesh": 0}
        posted = json.loads(service.requests[0].content)
        assert [
            base64.b64decode(uri.split(",", 1)[1])[-len(view) :]
            for uri, view in zip(
                posted["image_urls"], ("front", "right", "back", "left"), strict=True
            )
        ] == [b"front", b"right", b"back", b"left"]
        assert workflow.advance_workflow(run_dir)["status"] == "remesh"
        assert workflow.advance_workflow(run_dir)["status"] == "succeeded"
        downloaded = workflow.download_workflow(run_dir)
        assert downloaded["next_step"] == "complete"
        assert service.submissions == {"generation": 1, "remesh": 1}
        assert downloaded["validation"]["generation"]["triangles"] == 2
        assert downloaded["validation"]["remesh"]["triangles"] == 1
        assert all(
            item["has_embedded_base_color_texture"] for item in downloaded["validation"].values()
        )
        assert downloaded["warnings"] == []
        assert (
            Path(downloaded["artifacts"]["generation"]["model.glb"]).read_bytes()
            == service.original
        )
        assert Path(downloaded["artifacts"]["remesh"]["model.glb"]).read_bytes() == service.reduced
        assert workflow.advance_workflow(run_dir)["next_step"] == "complete"
        assert workflow.download_workflow(run_dir)["next_step"] == "complete"
        assert service.submissions == {"generation": 1, "remesh": 1}
        state = (Path(run_dir) / "workflow.json").read_text(encoding="utf-8")
        assert "integration-secret" not in state
        assert "data:image/" not in state


@pytest.mark.parametrize("lost_stage", ["generation", "remesh"])
def test_lost_post_response_requires_task_recovery_without_duplicate_charge(
    tmp_path, monkeypatch, lost_stage
):
    service = MeshyService(lost_stage)
    with httpx.Client(transport=httpx.MockTransport(service)) as http:
        monkeypatch.setattr(
            workflow, "MeshyClient", lambda: MeshyClient("integration-secret", http)
        )
        started = workflow.start_workflow(**_inputs(tmp_path))
        run_dir = started["run_dir"]
        if lost_stage == "remesh":
            workflow.advance_workflow(run_dir)
        assert workflow.workflow_status(run_dir)["next_step"] == "submission_uncertain"
        request_count = len(service.requests)
        for _ in range(3):
            assert workflow.advance_workflow(run_dir)["next_step"] == "submission_uncertain"
        assert len(service.requests) == request_count
        assert service.submissions[lost_stage] == 1
        # Recovery inspects an already accepted task and never repeats its POST.
        kind = "multi-image-to-3d" if lost_stage == "generation" else "remesh"
        existing = MeshyClient("integration-secret", http).list_tasks(kind)
        assert existing[0]["id"] == f"{lost_stage}-1"
        workflow.recover_submission(run_dir, lost_stage, existing[0]["id"])
        if lost_stage == "generation":
            assert workflow.advance_workflow(run_dir)["status"] == "remesh"
        assert workflow.advance_workflow(run_dir)["status"] == "succeeded"
        assert workflow.download_workflow(run_dir)["next_step"] == "complete"
        assert service.submissions == {"generation": 1, "remesh": 1}
