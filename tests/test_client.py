import json
from pathlib import Path

import httpx
import pytest

from meshy_codex.client import MeshyClient, MeshyError, SubmissionUncertain

IMAGES = [f"https://images.example/{view}.png" for view in ("front", "right", "back", "left")]


def make_client(handler, **kwargs):
    return MeshyClient(
        "test-secret-key", httpx.Client(transport=httpx.MockTransport(handler), **kwargs)
    )


def succeeded_task(**extras):
    return {
        "id": "task-1",
        "status": "SUCCEEDED",
        "model_urls": {"glb": "https://assets.example/model.glb"},
        **extras,
    }


def test_multiview_submission_uses_all_four_views_for_geometry_and_texturing():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"result": "created-1"})

    client = make_client(handler)
    assert client.create_multi_image(IMAGES) == "created-1"
    (request,) = requests
    assert request.method == "POST"
    assert str(request.url) == "https://api.meshy.ai/openapi/v1/multi-image-to-3d"
    assert request.headers["Authorization"] == "Bearer test-secret-key"
    assert json.loads(request.content) == {
        "image_urls": IMAGES,
        "texture_image_urls": IMAGES,
        "ai_model": "meshy-7.1",
        "geometry_resolution": "standard",
        "texture_resolution": "2k",
        "should_texture": True,
        "should_remesh": False,
        "enable_pbr": True,
        "target_formats": ["glb"],
    }


def test_texture_prompt_omits_conflicting_texture_images():
    payloads = []

    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"result": "created-1"})

    make_client(handler).create_multi_image(IMAGES, texture_prompt="Painted wood")
    assert payloads[0]["texture_prompt"] == "Painted wood"
    assert "texture_image_urls" not in payloads[0]


def test_remesh_uses_model_url_and_adaptive_low_without_fixed_target():
    payloads = []

    def handler(request):
        assert request.url.path == "/openapi/v1/remesh"
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"result": "remesh-1"})

    model_url = "https://assets.example/original.glb?signature=abc"
    assert make_client(handler).create_remesh(model_url) == "remesh-1"
    assert payloads == [
        {
            "model_url": model_url,
            "topology": "triangle",
            "decimation_mode": 4,
            "target_formats": ["glb"],
        }
    ]


@pytest.mark.parametrize(
    "failure", ["timeout", "network", "500", "408", "invalid_json", "missing_id", "invalid_id"]
)
def test_ambiguous_paid_submissions_are_never_retried(failure):
    calls = []

    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("test-secret-key secret image payload", request=request)
        if failure == "network":
            raise httpx.ConnectError("test-secret-key", request=request)
        if failure in {"500", "408"}:
            return httpx.Response(int(failure), text="test-secret-key")
        if failure == "invalid_json":
            return httpx.Response(200, text="test-secret-key invalid JSON")
        if failure == "invalid_id":
            return httpx.Response(200, json={"result": "../test-secret-key"})
        return httpx.Response(200, json={"wrong_field": "test-secret-key"})

    with pytest.raises(SubmissionUncertain) as exc:
        make_client(handler).create_multi_image(IMAGES)
    assert len(calls) == 1
    assert "Do not submit again" in str(exc.value)
    assert "test-secret-key" not in str(exc.value)
    assert "https://images" not in str(exc.value)


@pytest.mark.parametrize(
    "status, hint",
    [(401, "authentication"), (402, "credits"), (429, "rate limit"), (400, "parameters")],
)
def test_explicit_rejections_are_clear_and_do_not_echo_response(status, hint):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"message": "test-secret-key"})

    with pytest.raises(MeshyError) as exc:
        make_client(handler).create_multi_image(IMAGES)
    assert not isinstance(exc.value, SubmissionUncertain)
    assert len(calls) == 1
    assert f"HTTP {status}" in str(exc.value)
    assert hint in str(exc.value)
    assert "test-secret-key" not in str(exc.value)


def test_read_only_requests_retry_at_most_twice(monkeypatch):
    monkeypatch.setattr("meshy_codex.client.time.sleep", lambda _: None)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"id": "task-1", "status": "IN_PROGRESS"})

    assert make_client(handler).get_task("remesh", "task-1")["status"] == "IN_PROGRESS"
    assert len(calls) == 2


def test_list_uses_latest_first_pagination():
    def handler(request):
        assert dict(request.url.params) == {
            "page_num": "1",
            "page_size": "7",
            "sort_by": "-created_at",
        }
        return httpx.Response(200, json=[{"id": "latest"}])

    assert make_client(handler).list_tasks("remesh", 7) == [{"id": "latest"}]


@pytest.mark.parametrize("task_id", ["../bad", "..", "a/b", "a\\b", "a?secret", "a%2fb", "a\n"])
def test_task_ids_cannot_change_endpoint(task_id):
    def handler(_):
        pytest.fail("Invalid task IDs must fail before a request")

    with pytest.raises(ValueError, match="task ID"):
        make_client(handler).get_task("remesh", task_id)


def test_invalid_task_kind_cannot_change_origin():
    client = make_client(lambda _: pytest.fail("No request expected"))
    with pytest.raises(ValueError, match="Task kind"):
        client.list_tasks("https://evil.example/")


@pytest.mark.parametrize("environment_value", [None, "", "  \n  "])
def test_credentials_can_be_read_from_file_and_whitespace_trimmed(
    tmp_path, monkeypatch, environment_value
):
    if environment_value is None:
        monkeypatch.delenv("MESHY_API_KEY", raising=False)
    else:
        monkeypatch.setenv("MESHY_API_KEY", environment_value)
    path = tmp_path / "key.txt"
    path.write_text("  file-secret\n", encoding="utf-8")
    monkeypatch.setenv("MESHY_API_KEY_FILE", str(path))

    def handler(request):
        assert request.headers["authorization"] == "Bearer file-secret"
        return httpx.Response(200, json=[])

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        MeshyClient(http_client=http).list_tasks("remesh")


def test_missing_credentials_fail_without_network(monkeypatch):
    monkeypatch.delenv("MESHY_API_KEY", raising=False)
    monkeypatch.delenv("MESHY_API_KEY_FILE", raising=False)
    with pytest.raises(MeshyError, match="Set MESHY_API_KEY"):
        MeshyClient()


def test_downloads_model_textures_and_thumbnails_without_any_auth(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        return httpx.Response(200, content=b"asset content")

    client = make_client(
        handler,
        headers={"Authorization": "Bearer injected-secret"},
        auth=("user", "password"),
        cookies={"session": "private"},
    )
    task = succeeded_task(
        texture_urls=[
            {
                "base_color": "https://assets.example/color.png?token=secret",
                "normal": "https://assets.example/normal.jpg",
            }
        ],
        thumbnail_url="https://assets.example/preview.png",
        thumbnail_urls={"front": "https://assets.example/front.png"},
    )
    files = client.download_task(task, tmp_path)
    assert set(files) == {
        "model.glb",
        "texture_0_base_color.png",
        "texture_0_normal.jpg",
        "thumbnail.png",
        "thumbnail_front.png",
    }
    for path in files.values():
        assert Path(path).is_absolute()
        assert Path(path).read_bytes() == b"asset content"
    assert len(requests) == 5
    assert not list(tmp_path.glob("*.part"))


def test_identical_downloads_can_be_repeated_without_clobbering(tmp_path):
    client = make_client(lambda _: httpx.Response(200, content=b"model"))
    first = client.download_task(succeeded_task(), tmp_path)
    assert client.download_task(succeeded_task(), tmp_path) == first
    assert (tmp_path / "model.glb").read_bytes() == b"model"


def test_existing_different_file_is_never_overwritten(tmp_path):
    target = tmp_path / "model.glb"
    target.write_bytes(b"precious unrelated file")
    client = make_client(lambda _: httpx.Response(200, content=b"new model"))
    with pytest.raises(MeshyError, match="different file already exists"):
        client.download_task(succeeded_task(), tmp_path)
    assert target.read_bytes() == b"precious unrelated file"
    assert not list(tmp_path.glob("*.part"))


def test_asset_redirects_cannot_downgrade_https(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "http://assets.example/unsafe.glb"})

    with pytest.raises(MeshyError, match="HTTPS"):
        make_client(handler).download_task(succeeded_task(), tmp_path)
    assert len(requests) == 1
    assert not list(tmp_path.iterdir())


def test_https_redirects_do_not_send_bearer_or_cookies(tmp_path):
    hosts = []

    def handler(request):
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        hosts.append(request.url.host)
        if len(hosts) == 1:
            return httpx.Response(
                302,
                headers={
                    "Location": "https://cdn.example/final.glb",
                    "Set-Cookie": "session=secret",
                },
            )
        return httpx.Response(200, content=b"model")

    make_client(handler).download_task(succeeded_task(), tmp_path)
    assert hosts == ["assets.example", "cdn.example"]


def test_download_size_cap_cleans_partial_file(tmp_path, monkeypatch):
    monkeypatch.setattr("meshy_codex.client.MAX_ASSET_BYTES", 2)
    client = make_client(lambda _: httpx.Response(200, content=b"oversized"))
    with pytest.raises(MeshyError, match="download limit"):
        client.download_task(succeeded_task(), tmp_path)
    assert not list(tmp_path.iterdir())


def test_network_failure_during_download_is_sanitized(tmp_path):
    class BrokenStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"first bytes"
            raise httpx.ReadError("signed URL token: secret")

    client = make_client(lambda _: httpx.Response(200, stream=BrokenStream()))
    with pytest.raises(MeshyError, match="Asset download failed") as exc:
        client.download_task(succeeded_task(), tmp_path)
    assert "secret" not in str(exc.value)
    assert not list(tmp_path.iterdir())


def test_unsafe_texture_name_rejected_before_saving(tmp_path):
    client = make_client(lambda _: pytest.fail("No network expected"))
    task = succeeded_task(texture_urls=[{"../../evil": "https://assets.example/color.png"}])
    with pytest.raises(MeshyError, match="texture map name"):
        client.download_task(task, tmp_path)
    assert not list(tmp_path.iterdir())


def test_only_successful_task_can_be_downloaded(tmp_path):
    client = make_client(lambda _: pytest.fail("No network expected"))
    with pytest.raises(MeshyError, match="SUCCEEDED"):
        client.download_task({"status": "IN_PROGRESS"}, tmp_path)


def test_closing_wrapper_preserves_caller_owned_http_client():
    http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    client = MeshyClient("test-key", http)
    client.close()
    assert not http.is_closed
    http.close()
