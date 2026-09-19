import base64

import pytest

from meshy_codex.images import prepare_images, validate_https_url


def test_four_local_images_preserve_front_first_and_encode_by_signature(tmp_path):
    contents = [
        b"\x89PNG\r\n\x1a\nfront",
        b"\xff\xd8\xffright",
        b"\xff\xd8\xffback",
        b"\x89PNG\r\n\x1a\nleft",
    ]
    names = ["front.png", "right.jpg", "back.jpeg", "left.PNG"]
    paths = []
    for name, content in zip(names, contents, strict=True):
        path = tmp_path / name
        path.write_bytes(content)
        paths.append(str(path))
    result = prepare_images(paths)
    assert [base64.b64decode(value.split(",", 1)[1]) for value in result] == contents
    assert result[0].startswith("data:image/png;base64,")
    assert result[1].startswith("data:image/jpeg;base64,")


@pytest.mark.parametrize("count", [0, 1, 3, 5])
def test_requires_exactly_four_images(count):
    with pytest.raises(ValueError, match="Exactly four"):
        prepare_images(["https://images.example/front.png"] * count)


@pytest.mark.parametrize(
    "url",
    [
        "http://images.example/front.png",
        "https://user:secret@images.example/a.png",
        "https://images.example/a.png#fragment",
        "https:///a.png",
        "https://images.example:bad/a.png",
        "https://images.example/a\n.png",
        "data:image/png;base64,secret",
        "https://@images.example/a.png",
    ],
)
def test_unsafe_urls_rejected_without_echoing_input(url):
    with pytest.raises(ValueError) as exc:
        prepare_images([url] * 4)
    assert url not in str(exc.value)
    assert "secret" not in str(exc.value)


def test_public_https_urls_are_preserved_with_signed_query():
    urls = [
        f"https://images.example/{view}.png?signature=abc"
        for view in ("front", "right", "back", "left")
    ]
    assert prepare_images(urls) == urls
    assert validate_https_url(urls[0]) == urls[0]


def test_extension_and_signature_must_match(tmp_path):
    path = tmp_path / "fake.png"
    path.write_bytes(b"\xff\xd8\xff JPEG under the wrong extension")
    with pytest.raises(ValueError, match="signature"):
        prepare_images([str(path)] * 4)


def test_size_checked_before_base64_encoding(tmp_path, monkeypatch):
    monkeypatch.setattr("meshy_codex.images.MAX_IMAGE_BYTES", 8)
    path = tmp_path / "too_large.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nextra")
    with pytest.raises(ValueError, match="20 MiB"):
        prepare_images([str(path)] * 4)


def test_missing_file_has_clear_private_error(tmp_path):
    with pytest.raises(ValueError, match="could not be read") as exc:
        prepare_images([str(tmp_path / "private-project.png")] * 4)
    assert "private-project" not in str(exc.value)


def test_prepared_data_uris_can_be_validated_again(tmp_path):
    path = tmp_path / "front.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nreference")
    prepared = prepare_images([str(path)] * 4)
    assert prepare_images(prepared) == prepared


@pytest.mark.parametrize(
    "uri",
    [
        "data:image/png;base64,not-valid-%-base64",
        "data:image/png;base64,YWJj",
        "data:image/gif;base64,R0lGODlh",
        "data:image/png,raw-image-data",
        "data:image/jpeg;base64,iVBORw0KGgo=",
    ],
)
def test_data_uri_mime_base64_and_signature_are_checked(uri):
    with pytest.raises(ValueError) as exc:
        prepare_images([uri] * 4)
    assert uri not in str(exc.value)


def test_data_uri_limit_checked_before_decoding(monkeypatch):
    monkeypatch.setattr("meshy_codex.images.MAX_IMAGE_BYTES", 8)
    uri = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nextra").decode("ascii")
    with pytest.raises(ValueError, match="20 MiB"):
        prepare_images([uri] * 4)
