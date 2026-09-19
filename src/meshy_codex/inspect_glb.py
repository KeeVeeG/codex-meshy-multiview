"""Inspect GLB counts and texture bindings without claiming full glTF validation."""

from __future__ import annotations

import base64
import binascii
import json
import struct
from pathlib import Path
from typing import BinaryIO

_SIGNATURES = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "image/ktx2": b"\xabKTX 20\xbb\r\n\x1a\n",
}


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"GLB {label} must be an object.")
    return value


def _objects(document: dict, name: str) -> list[dict]:
    items = document.get(name, [])
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError(f"GLB {name} must be an array of objects.")
    return items


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"GLB {label} must be an integer of at least {minimum}.")
    return value


def _index(value: object, items: list, label: str) -> int:
    index = _integer(value, label)
    if index >= len(items):
        raise ValueError(f"GLB {label} is outside its array.")
    return index


def _read_chunks(stream: BinaryIO, file_size: int) -> tuple[dict, int, int]:
    header = stream.read(12)
    if len(header) != 12:
        raise ValueError("Truncated GLB header.")
    magic, version, length = struct.unpack("<4sII", header)
    if magic != b"glTF" or version != 2 or length != file_size:
        raise ValueError("Invalid GLB 2.0 file.")
    chunk = stream.read(8)
    if len(chunk) != 8:
        raise ValueError("Missing GLB JSON chunk.")
    size, kind = struct.unpack("<II", chunk)
    if kind != 0x4E4F534A or size % 4 or size > min(length - 20, 32 * 1024 * 1024):
        raise ValueError("Invalid or oversized GLB JSON chunk.")
    try:
        document = _object(json.loads(stream.read(size)), "JSON document")
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("Invalid GLB JSON document.") from None
    remaining = length - 20 - size
    binary_offset, binary_size = 0, 0
    while remaining:
        chunk = stream.read(8)
        if remaining < 8 or len(chunk) != 8:
            raise ValueError("Truncated GLB chunk.")
        chunk_size, chunk_kind = struct.unpack("<II", chunk)
        if chunk_size % 4 or chunk_size > remaining - 8:
            raise ValueError("Invalid or truncated GLB data chunk.")
        if chunk_kind == 0x004E4942:
            if binary_offset:
                raise ValueError("GLB contains multiple binary chunks.")
            binary_offset, binary_size = stream.tell(), chunk_size
        stream.seek(chunk_size, 1)
        remaining -= chunk_size + 8
    return document, binary_offset, binary_size


def _signature_matches(prefix: bytes, mime_type: str | None) -> bool:
    if mime_type is not None:
        signature = _SIGNATURES.get(mime_type)
        return bool(signature and prefix.startswith(signature))
    return any(prefix.startswith(signature) for signature in _SIGNATURES.values())


def _embedded_image(
    image: dict, views: list[dict], buffers: list[dict], stream: BinaryIO, binary_offset: int
) -> bool:
    mime_type = image.get("mimeType")
    if mime_type is not None and not isinstance(mime_type, str):
        raise ValueError("GLB image mimeType must be a string.")
    if "uri" in image:
        uri = image["uri"]
        if not isinstance(uri, str):
            raise ValueError("GLB image URI must be a string.")
        if "bufferView" in image:
            raise ValueError("GLB image must not specify both URI and bufferView.")
        if not uri.startswith("data:"):
            return False
        header, separator, encoded = uri.partition(",")
        if not separator or not header.endswith(";base64"):
            return False
        uri_type = header[5:-7]
        if uri_type not in _SIGNATURES or (mime_type and mime_type != uri_type):
            return False
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            return False
        return _signature_matches(content[:12], uri_type)
    if "bufferView" not in image:
        return False
    view = views[_index(image["bufferView"], views, "image bufferView")]
    if view.get("buffer", 0) != 0 or not binary_offset:
        return False
    if buffers and "uri" in buffers[0]:
        return False
    stream.seek(binary_offset + view.get("byteOffset", 0))
    prefix = stream.read(min(view["byteLength"], 12))
    return _signature_matches(prefix, mime_type)


def _bound_image(
    primitive: dict,
    materials: list[dict],
    textures: list[dict],
    images: list[dict],
    accessors: list[dict],
) -> int | None:
    if "material" not in primitive:
        return None
    material = materials[_index(primitive["material"], materials, "primitive material")]
    pbr = _object(material.get("pbrMetallicRoughness", {}), "material PBR settings")
    if "baseColorTexture" not in pbr:
        return None
    info = _object(pbr["baseColorTexture"], "base-color texture")
    texture = textures[_index(info.get("index"), textures, "base-color texture index")]
    tex_coord = _integer(info.get("texCoord", 0), "texture coordinate set")
    extensions = _object(info.get("extensions", {}), "texture info extensions")
    transform = _object(extensions.get("KHR_texture_transform", {}), "texture transform")
    if "texCoord" in transform:
        tex_coord = _integer(transform["texCoord"], "transformed texture coordinate set")
    attributes = _object(primitive.get("attributes", {}), "primitive attributes")
    uv_id = attributes.get(f"TEXCOORD_{tex_coord}")
    if uv_id is None:
        return None
    uv = accessors[_index(uv_id, accessors, "texture coordinate accessor")]
    if uv.get("type") != "VEC2" or uv["count"] == 0:
        return None
    position = accessors[_index(attributes.get("POSITION"), accessors, "position accessor")]
    if uv["count"] != position["count"]:
        return None
    extensions = _object(texture.get("extensions", {}), "texture extensions")
    basis = _object(extensions.get("KHR_texture_basisu", {}), "Basis texture extension")
    source = basis.get("source", texture.get("source"))
    if source is None:
        return None
    return _index(source, images, "texture image source")


def inspect_glb(path: Path) -> dict:
    """Count stored triangles and verify an embedded image has a usable UV binding.

    PNG, JPEG, and KTX2 signatures are checked; pixels and accessor payloads are
    not decoded. This is an artifact sanity check, not a full glTF validator.
    """
    with path.open("rb") as stream:
        document, binary_offset, binary_size = _read_chunks(stream, path.stat().st_size)
        accessors = _objects(document, "accessors")
        materials = _objects(document, "materials")
        textures = _objects(document, "textures")
        images = _objects(document, "images")
        views = _objects(document, "bufferViews")
        buffers = _objects(document, "buffers")
        for accessor in accessors:
            _integer(accessor.get("count"), "accessor count")
            _integer(accessor.get("byteOffset", 0), "accessor byte offset")
            if "bufferView" in accessor:
                _index(accessor["bufferView"], views, "accessor bufferView")
            if "componentType" in accessor:
                _integer(accessor["componentType"], "accessor component type")
        for buffer in buffers:
            _integer(buffer.get("byteLength"), "buffer byte length")
        for view in views:
            buffer_id = _integer(view.get("buffer", 0), "bufferView buffer")
            offset = _integer(view.get("byteOffset", 0), "bufferView byte offset")
            size = _integer(view.get("byteLength"), "bufferView byte length", minimum=1)
            if "byteStride" in view:
                _integer(view["byteStride"], "bufferView byte stride", minimum=1)
            if buffers and buffer_id >= len(buffers):
                raise ValueError("GLB bufferView buffer is outside its array.")
            if buffers and offset + size > buffers[buffer_id]["byteLength"]:
                raise ValueError("GLB bufferView extends beyond its declared buffer.")
            if buffer_id == 0 and not (buffers and "uri" in buffers[0]):
                if offset + size > binary_size:
                    raise ValueError("GLB bufferView extends beyond its binary chunk.")
        triangles = 0
        embedded_bound = False
        verified_images: dict[int, bool] = {}
        for mesh in _objects(document, "meshes"):
            for primitive in _objects(mesh, "primitives"):
                attributes = _object(primitive.get("attributes", {}), "primitive attributes")
                position = _index(attributes.get("POSITION"), accessors, "position accessor")
                index = _index(primitive.get("indices", position), accessors, "count accessor")
                count = accessors[index]["count"]
                mode = _integer(primitive.get("mode", 4), "primitive mode")
                if mode > 6:
                    raise ValueError("GLB primitive mode must be between 0 and 6.")
                triangles += count // 3 if mode == 4 else max(count - 2, 0) if mode in (5, 6) else 0
                image_id = _bound_image(primitive, materials, textures, images, accessors)
                if image_id is not None:
                    if image_id not in verified_images:
                        verified_images[image_id] = _embedded_image(
                            images[image_id], views, buffers, stream, binary_offset
                        )
                    embedded_bound |= verified_images[image_id]
    return {
        "triangles": triangles,
        "materials": len(materials),
        "images": len(images),
        "has_embedded_base_color_texture": embedded_bound,
        "count_scope": "stored mesh primitives (not scene instances)",
        "visual_quality_checked": False,
    }
