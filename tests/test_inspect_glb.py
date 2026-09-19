"""Artifact inspection verifies counts, image signatures, and primitive UV bindings."""

import base64
import json
import struct

import pytest

from meshy_codex.inspect_glb import inspect_glb

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)


def glb(document, binary=PNG):
    data = json.dumps(document).encode()
    data += b" " * (-len(data) % 4)
    binary += b"\x00" * (-len(binary) % 4)
    chunks = struct.pack("<II", len(data), 0x4E4F534A) + data
    chunks += struct.pack("<II", len(binary), 0x004E4942) + binary
    return struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks


@pytest.fixture
def document():
    return {
        "asset": {"version": "2.0"},
        "accessors": [
            {"count": 12, "type": "SCALAR"},
            {"count": 8, "type": "VEC3"},
            {"count": 8, "type": "VEC2"},
        ],
        "meshes": [
            {
                "primitives": [
                    {"indices": 0, "attributes": {"POSITION": 1, "TEXCOORD_0": 2}, "material": 0}
                ]
            }
        ],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
        "textures": [{"source": 0}],
        "images": [{"bufferView": 0, "mimeType": "image/png"}],
        "bufferViews": [{"buffer": 0, "byteLength": len(PNG)}],
        "buffers": [{"byteLength": len(PNG)}],
    }


def inspect(tmp_path, document, binary=PNG):
    path = tmp_path / "model.glb"
    path.write_bytes(glb(document, binary))
    return inspect_glb(path)


def test_counts_triangles_and_bound_embedded_texture(tmp_path, document):
    result = inspect(tmp_path, document)
    assert result["triangles"] == 4
    assert result["has_embedded_base_color_texture"] is True
    assert result["visual_quality_checked"] is False


def test_orphan_images_and_external_textures_do_not_count_as_embedded(tmp_path):
    document = {
        "accessors": [{"count": 6}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "images": [{"uri": "texture.png"}],
    }
    result = inspect(tmp_path, document)
    assert result["triangles"] == 2
    assert result["has_embedded_base_color_texture"] is False


@pytest.mark.parametrize("bad_uv", [None, "wrong_type", "wrong_count", "wrong_set"])
def test_texture_requires_matching_uv_on_its_primitive(tmp_path, document, bad_uv):
    primitive = document["meshes"][0]["primitives"][0]
    if bad_uv is None:
        del primitive["attributes"]["TEXCOORD_0"]
    elif bad_uv == "wrong_type":
        document["accessors"][2]["type"] = "SCALAR"
    elif bad_uv == "wrong_count":
        document["accessors"][2]["count"] = 3
    else:
        document["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"]["texCoord"] = 1
    assert inspect(tmp_path, document)["has_embedded_base_color_texture"] is False


def test_uv_on_another_untextured_primitive_does_not_verify_binding(tmp_path, document):
    primitives = document["meshes"][0]["primitives"]
    del primitives[0]["attributes"]["TEXCOORD_0"]
    primitives.append({"attributes": {"POSITION": 1, "TEXCOORD_0": 2}})
    assert inspect(tmp_path, document)["has_embedded_base_color_texture"] is False


def test_texture_transform_can_select_another_uv_set(tmp_path, document):
    attributes = document["meshes"][0]["primitives"][0]["attributes"]
    attributes["TEXCOORD_1"] = attributes.pop("TEXCOORD_0")
    info = document["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"]
    info["extensions"] = {"KHR_texture_transform": {"texCoord": 1}}
    assert inspect(tmp_path, document)["has_embedded_base_color_texture"] is True


@pytest.mark.parametrize(
    "mime,payload",
    [
        ("image/png", PNG),
        ("image/jpeg", b"\xff\xd8\xff\xe0" + b"\x00" * 12),
        ("image/ktx2", b"\xabKTX 20\xbb\r\n\x1a\n" + b"\x00" * 12),
    ],
)
@pytest.mark.parametrize("storage", ["buffer", "data_uri"])
def test_supported_image_signatures(tmp_path, document, mime, payload, storage):
    document["buffers"][0]["byteLength"] = len(payload)
    document["bufferViews"][0]["byteLength"] = len(payload)
    if storage == "buffer":
        document["images"][0]["mimeType"] = mime
    else:
        document["images"][0] = {"uri": f"data:{mime};base64," + base64.b64encode(payload).decode()}
    if mime == "image/ktx2":
        document["textures"][0] = {"extensions": {"KHR_texture_basisu": {"source": 0}}}
    assert inspect(tmp_path, document, payload)["has_embedded_base_color_texture"] is True


@pytest.mark.parametrize(
    "image",
    [
        {"bufferView": 0, "mimeType": "image/jpeg"},
        {"uri": "data:image/png;base64,not-base64!"},
        {"uri": "data:image/png;base64," + base64.b64encode(b"not an image").decode()},
        {"uri": "texture.png"},
    ],
)
def test_invalid_signatures_and_external_images_are_not_verified(tmp_path, document, image):
    document["images"][0] = image
    assert inspect(tmp_path, document)["has_embedded_base_color_texture"] is False


def test_bin_bytes_must_have_actual_image_signature(tmp_path, document):
    assert (
        inspect(tmp_path, document, b"\x00" * len(PNG))["has_embedded_base_color_texture"] is False
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("byteOffset", -1),
        ("byteOffset", True),
        ("byteOffset", 0.5),
        ("byteLength", -1),
        ("byteLength", 0),
        ("byteLength", "4"),
        ("byteLength", len(PNG) + 1),
        ("buffer", -1),
    ],
)
def test_invalid_buffer_ranges_raise_value_error(tmp_path, document, field, value):
    document["bufferViews"][0][field] = value
    with pytest.raises(ValueError, match="GLB"):
        inspect(tmp_path, document)


@pytest.mark.parametrize("count", [-3, True, 1.5, "3", None])
def test_invalid_accessor_counts_raise_value_error(tmp_path, document, count):
    document["accessors"][0]["count"] = count
    with pytest.raises(ValueError, match="accessor count"):
        inspect(tmp_path, document)


@pytest.mark.parametrize(
    "field,value",
    [
        ("indices", True),
        ("indices", -1),
        ("indices", "0"),
        ("indices", 3),
        ("mode", -1),
        ("mode", 7),
        ("mode", 4.0),
        ("material", -1),
    ],
)
def test_invalid_primitive_numeric_fields_raise_value_error(tmp_path, document, field, value):
    document["meshes"][0]["primitives"][0][field] = value
    with pytest.raises(ValueError, match="GLB"):
        inspect(tmp_path, document)


@pytest.mark.parametrize(
    "document", [[], {"accessors": {}}, {"meshes": [None]}, {"meshes": [{"primitives": [1]}]}]
)
def test_malformed_metadata_raises_value_error(tmp_path, document):
    with pytest.raises(ValueError, match="GLB"):
        inspect(tmp_path, document)


def test_truncated_file_rejected(tmp_path):
    path = tmp_path / "model.glb"
    path.write_bytes(glb({})[:-1])
    with pytest.raises(ValueError, match="Invalid GLB"):
        inspect_glb(path)
