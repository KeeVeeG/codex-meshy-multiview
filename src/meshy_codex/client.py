"""Small synchronous Meshy API client with conservative submission semantics."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import httpx

from .images import prepare_images, validate_https_url

BASE_URL = "https://api.meshy.ai/openapi/v1"
TASK_KINDS = frozenset({"multi-image-to-3d", "remesh"})
MAX_ASSET_BYTES = 1024 * 1024 * 1024
MAX_ASSETS = 64
REQUEST_TIMEOUT = httpx.Timeout(10.0)
UNCERTAIN_HINT = (
    "Meshy may already have accepted this paid submission. Do not submit again "
    "automatically; inspect recent tasks and recover the existing task ID first."
)


class MeshyError(RuntimeError):
    """A sanitized, actionable Meshy operation error."""


class SubmissionUncertain(MeshyError):
    """A POST may have succeeded; retrying could create a second paid task."""


def _credentials(api_key: str | None) -> str:
    key = api_key if api_key is not None else os.environ.get("MESHY_API_KEY")
    if api_key is None and not (key or "").strip():
        key_file = os.environ.get("MESHY_API_KEY_FILE")
        if key_file:
            try:
                with Path(key_file).expanduser().open("r", encoding="utf-8") as source:
                    key = source.read(4097)
            except (OSError, UnicodeError):
                raise MeshyError("Could not read MESHY_API_KEY_FILE.") from None
    if not isinstance(key, str) or not key.strip():
        raise MeshyError("Set MESHY_API_KEY or MESHY_API_KEY_FILE before using Meshy.")
    key = key.strip()
    if len(key) > 4096 or any(ord(char) <= 32 or ord(char) > 126 for char in key):
        raise MeshyError("The Meshy API key has an invalid format.")
    return key


def _kind(kind: str) -> str:
    if kind not in TASK_KINDS:
        raise ValueError("Task kind must be 'multi-image-to-3d' or 'remesh'.")
    return kind


def _task_id(task_id: str) -> str:
    # Meshy explicitly does not promise UUID-shaped IDs. Quote a single path
    # segment, but reject traversal/control characters before constructing URLs.
    if (
        not isinstance(task_id, str)
        or not task_id
        or len(task_id) > 256
        or task_id in {".", ".."}
        or any(ord(c) <= 32 for c in task_id)
        or any(c in task_id for c in "/\\?#%")
    ):
        raise ValueError("Invalid Meshy task ID.")
    return quote(task_id, safe="")


def _status_error(status: int) -> str:
    hints = {
        400: "Check the image URLs, supported formats, and request parameters.",
        401: "Check MESHY_API_KEY; authentication failed.",
        402: "The Meshy account has insufficient API credits.",
        403: "The API key or account is not permitted to perform this operation.",
        404: "The task was not found or may have expired.",
        413: "The request is too large; use smaller images or public HTTPS URLs.",
        422: "Meshy rejected the request parameters.",
        429: "Meshy rate limit reached; wait before retrying.",
    }
    return f"Meshy API returned HTTP {status}. " + hints.get(
        status, "Try a read-only status check later."
    )


class MeshyClient:
    """Use an API key only for the fixed Meshy API origin.

    Injected clients remain caller-owned. API requests and asset downloads use
    standalone Request objects so client-default credentials/cookies cannot leak
    to asset hosts. All POSTs are attempted exactly once.
    """

    def __init__(self, api_key: str | None = None, http_client: httpx.Client | None = None) -> None:
        self._api_key = _credentials(api_key)
        self._owns_http = http_client is None
        self._http = http_client or httpx.Client(
            timeout=REQUEST_TIMEOUT, follow_redirects=False, trust_env=False
        )

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> MeshyClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        attempts = 1 if method == "POST" else 2
        for attempt in range(attempts):
            request = httpx.Request(
                method,
                f"{BASE_URL}/{path}",
                headers={"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"},
                json=payload,
                params=params,
                extensions={"timeout": REQUEST_TIMEOUT.as_dict()},
            )
            try:
                response = self._http.send(request, auth=None, follow_redirects=False)
            except httpx.RequestError:
                if method == "POST":
                    raise SubmissionUncertain(UNCERTAIN_HINT) from None
                if attempt + 1 < attempts:
                    time.sleep(0.25)
                    continue
                raise MeshyError(
                    "Could not reach Meshy. Retry the read-only request later."
                ) from None
            try:
                status = response.status_code
                if method == "POST" and (status >= 500 or status == 408):
                    raise SubmissionUncertain(f"Meshy API returned HTTP {status}. {UNCERTAIN_HINT}")
                if not 200 <= status < 300:
                    if (status == 429 or status >= 500) and attempt + 1 < attempts:
                        time.sleep(0.25)
                        continue
                    raise MeshyError(_status_error(status))
                try:
                    return response.json()
                except (ValueError, UnicodeError):
                    if method == "POST":
                        raise SubmissionUncertain(UNCERTAIN_HINT) from None
                    raise MeshyError("Meshy returned an invalid JSON response.") from None
            finally:
                response.close()
        raise AssertionError("Unreachable request state")

    def _submit(self, kind: str, payload: dict[str, Any]) -> str:
        result = self._request("POST", kind, payload=payload)
        task_id = result.get("result") if isinstance(result, dict) else None
        try:
            _task_id(task_id)
        except ValueError:
            raise SubmissionUncertain(UNCERTAIN_HINT) from None
        return task_id

    def create_multi_image(
        self,
        images: list[str],
        *,
        ai_model: str = "meshy-7.1",
        enable_pbr: bool = True,
        texture_prompt: str | None = None,
    ) -> str:
        """Submit four references, with the front view first, for textured GLB."""
        if ai_model not in {"meshy-7.1", "latest"}:
            raise ValueError("Use meshy-7.1 or latest for multi-view texturing.")
        if not isinstance(enable_pbr, bool):
            raise ValueError("enable_pbr must be a boolean.")
        if texture_prompt is not None and (
            not isinstance(texture_prompt, str)
            or not texture_prompt.strip()
            or len(texture_prompt) > 800
        ):
            raise ValueError("texture_prompt must contain 1 to 800 characters.")
        prepared = prepare_images(images)
        payload: dict[str, Any] = {
            "image_urls": prepared,
            "ai_model": ai_model,
            "geometry_resolution": "standard",
            "texture_resolution": "2k",
            "should_texture": True,
            "should_remesh": False,
            "enable_pbr": enable_pbr,
            "target_formats": ["glb"],
        }
        if texture_prompt is None:
            payload["texture_image_urls"] = prepared
        else:
            payload["texture_prompt"] = texture_prompt
        return self._submit("multi-image-to-3d", payload)

    def create_remesh(self, model_url: str) -> str:
        """Remesh the original textured GLB using adaptive low triangle density."""
        validate_https_url(model_url)
        return self._submit(
            "remesh",
            {
                "model_url": model_url,
                "topology": "triangle",
                "decimation_mode": 4,
                "target_formats": ["glb"],
            },
        )

    def get_task(self, kind: str, task_id: str) -> dict[str, Any]:
        task = self._request("GET", f"{_kind(kind)}/{_task_id(task_id)}")
        if not isinstance(task, dict) or not isinstance(task.get("status"), str):
            raise MeshyError("Meshy returned an invalid task object.")
        return task

    def list_tasks(self, kind: str, limit: int = 10) -> list[dict[str, Any]]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100.")
        result = self._request(
            "GET", _kind(kind), params={"page_num": 1, "page_size": limit, "sort_by": "-created_at"}
        )
        if not isinstance(result, list) or any(not isinstance(task, dict) for task in result):
            raise MeshyError("Meshy returned an invalid task list.")
        return result

    def download_task(self, task: dict[str, Any], directory: Path) -> dict[str, str]:
        """Save a successful task's GLB, texture maps, and previews.

        Return generated filenames mapped to absolute paths. Identical existing
        files are reused; different existing files are never overwritten. Reruns
        compare bytes instead of trusting a stale or unrelated manifest.
        """
        assets = _task_assets(task)
        destination = Path(directory).expanduser().resolve()
        try:
            destination.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise MeshyError("Could not create the asset output directory.") from None
        paths: dict[str, str] = {}
        for name, url in assets:
            target = destination / name
            self._download_asset(url, target)
            paths[name] = str(target)
        return paths

    def _download_asset(self, url: str, target: Path) -> None:
        if target.is_symlink():
            raise MeshyError("Refusing to write an asset over a symbolic link.")
        temporary: Path | None = None
        start = time.monotonic()
        try:
            # Check every redirect explicitly: HTTPS cannot downgrade to HTTP,
            # and no API credentials are attached even on same-origin redirects.
            for redirect in range(4):
                validate_https_url(url)
                request = httpx.Request(
                    "GET", url, extensions={"timeout": REQUEST_TIMEOUT.as_dict()}
                )
                response = self._http.send(request, auth=None, follow_redirects=False, stream=True)
                try:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location or redirect == 3:
                            raise MeshyError(
                                "Asset download returned too many or invalid redirects."
                            )
                        url = urljoin(url, location)
                        continue
                    if response.status_code != 200:
                        raise MeshyError(
                            f"Asset download returned HTTP {response.status_code}. "
                            "Refresh the task to obtain current download URLs."
                        )
                    length = response.headers.get("content-length")
                    if length and (not length.isdecimal() or int(length) > MAX_ASSET_BYTES):
                        raise MeshyError(
                            "Asset exceeds the 1 GiB download limit or has invalid size."
                        )
                    size = 0
                    with tempfile.NamedTemporaryFile(
                        prefix=".meshy-", suffix=".part", dir=target.parent, delete=False
                    ) as output:
                        temporary = Path(output.name)
                        for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                            size += len(chunk)
                            if size > MAX_ASSET_BYTES:
                                raise MeshyError("Asset exceeds the 1 GiB download limit.")
                            if time.monotonic() - start > 30:
                                raise MeshyError(
                                    "Asset download exceeded its 30 second time limit."
                                )
                            output.write(chunk)
                    if not size:
                        raise MeshyError("Meshy returned an empty asset.")
                    # A hard link creates the final file atomically without an
                    # overwrite window, on both Windows and POSIX filesystems.
                    try:
                        os.link(temporary, target)
                    except FileExistsError:
                        if (
                            target.is_symlink()
                            or not target.is_file()
                            or _digest(target) != _digest(temporary)
                        ):
                            raise MeshyError(
                                "A different file already exists in the output directory. "
                                "Choose another directory; existing files were preserved."
                            ) from None
                    return
                finally:
                    response.close()
        except httpx.RequestError:
            raise MeshyError(
                "Asset download failed. Refresh the task and retry downloading."
            ) from None
        except (ValueError, httpx.InvalidURL):
            raise MeshyError("Asset download requires HTTPS URLs without credentials.") from None
        except OSError:
            raise MeshyError(
                "Could not save an asset. Check the output directory and available disk space."
            ) from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def _digest(path: Path) -> bytes:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").digest()


def _image_extension(url: str) -> str:
    suffix = Path(urlsplit(url).path).suffix.lower()
    return suffix if suffix in {".png", ".jpg", ".jpeg", ".webp"} else ".png"


def _task_assets(task: dict[str, Any]) -> list[tuple[str, str]]:
    if not isinstance(task, dict) or task.get("status") != "SUCCEEDED":
        raise MeshyError("Only SUCCEEDED tasks can be downloaded.")
    models = task.get("model_urls")
    if not isinstance(models, dict) or not models.get("glb"):
        raise MeshyError("The successful task does not contain a GLB download URL.")
    assets: list[tuple[str, str]] = [("model.glb", models["glb"])]
    textures = task.get("texture_urls") or []
    if not isinstance(textures, list):
        raise MeshyError("Meshy returned an invalid texture list.")
    for index, texture in enumerate(textures):
        if not isinstance(texture, dict):
            raise MeshyError("Meshy returned an invalid texture object.")
        for map_name, url in sorted(texture.items()):
            if not url:
                continue
            if not isinstance(map_name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", map_name):
                raise MeshyError("Meshy returned an invalid texture map name.")
            validate_https_url(url)
            assets.append((f"texture_{index}_{map_name}{_image_extension(url)}", url))
    for field, name in (("thumbnail_url", "thumbnail"), ("alpha_thumbnail_url", "alpha_thumbnail")):
        url = task.get(field)
        if url:
            validate_https_url(url)
            assets.append((name + _image_extension(url), url))
    views = task.get("thumbnail_urls") or {}
    if not isinstance(views, dict):
        raise MeshyError("Meshy returned invalid view thumbnails.")
    for view in ("front", "right", "back", "left"):
        url = views.get(view)
        if url:
            validate_https_url(url)
            assets.append((f"thumbnail_{view}{_image_extension(url)}", url))
    if len(assets) > MAX_ASSETS:
        raise MeshyError("The task exceeds the 64 asset download limit.")
    for _, url in assets:
        validate_https_url(url)
    return assets
