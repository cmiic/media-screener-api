"""The response of /classify and /infer for every format, with the detector and the extractors stubbed."""

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from unittest.mock import Mock, patch

import nudenet
import pytest

with patch.object(nudenet, "NudeDetector", return_value=Mock()):
    import app

SAFE = [{"class": "FACE_FEMALE", "score": 0.9, "box": [0, 0, 1, 1]}]
UNSAFE = [
    {"class": "FEMALE_BREAST_EXPOSED", "score": 0.6, "box": [0, 0, 1, 1]},
    {"class": "BUTTOCKS_EXPOSED", "score": 0.5, "box": [0, 0, 1, 1]},
    {"class": "FACE_FEMALE", "score": 0.95, "box": [0, 0, 1, 1]},
]
MORE_UNSAFE = [
    {"class": "MALE_GENITALIA_EXPOSED", "score": 0.9, "box": [0, 0, 1, 1]},
    {"class": "FEMALE_BREAST_EXPOSED", "score": 0.7, "box": [0, 0, 1, 1]},
]
BELOW_THRESHOLD = [{"class": "ANUS_EXPOSED", "score": 0.2, "box": [0, 0, 1, 1]}]
DETECTIONS = {b"safe": SAFE, b"unsafe": UNSAFE, b"more": MORE_UNSAFE, b"faint": BELOW_THRESHOLD, b"none": []}

# What each extractor yields for an upload: (image bytes, location).
VIDEO_FRAMES = [(b"safe", 0.0), (b"unsafe", 5.004), (b"more", 10.0)]
PDF_PAGES = [(b"safe", 1), (b"unsafe", 2), (b"more", 3)]
DOCX_IMAGES = [(b"safe", "media/image1.png"), (b"unsafe", "media/image2.png"), (b"more", "media/image3.png")]
PPTX_IMAGES = [(b"safe", "slide_1"), (b"unsafe", "slide_2"), (b"more", "slide_3")]
CLEAN_ITEMS = {
    "video": [(b"safe", 0.0), (b"faint", 5.0)],
    "pdf": [(b"safe", 1), (b"faint", 2)],
    "docx": [(b"safe", "media/image1.png"), (b"faint", "media/image2.png")],
    "pptx": [(b"safe", "slide_1"), (b"faint", "slide_2")],
}
CONTENT_TYPES = {
    "image": "image/png",
    "video": "video/mp4",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


@contextmanager
def extracted(file_type: str, items: list) -> Iterator[None]:
    """Stub the extractor for file_type to yield items, and the detector to answer from DETECTIONS."""

    @contextmanager
    def render_pdf_pages(_pdf_bytes: bytes):
        yield len(items), iter(items)

    extractors = {
        "video": patch.object(app, "extract_video_frames", return_value=items),
        "pdf": patch.object(app, "render_pdf_pages", render_pdf_pages),
        "docx": patch.object(app, "extract_docx_images", return_value=items),
        "pptx": patch.object(app, "extract_pptx_images", return_value=items),
    }
    detector = Mock()
    detector.detect.side_effect = lambda image_bytes: DETECTIONS[image_bytes]
    with patch.object(app, "detector", detector), extractors.get(file_type, nullcontext()):
        yield


def classify(file_type: str, items: list, early_exit: bool, contents: bytes = b"upload") -> dict:
    with extracted(file_type, items):
        response = app.classify_contents(contents, CONTENT_TYPES[file_type], "upload", 0.35, 5.0, early_exit)
    response["detected_classes"] = sorted(response["detected_classes"])
    return response


def infer(file_type: str, items: list, contents: bytes = b"upload") -> dict:
    with extracted(file_type, items):
        return app.infer_contents(contents, CONTENT_TYPES[file_type], "upload", 5.0)


def test_classify_image() -> None:
    assert classify("image", [], early_exit=True, contents=b"unsafe") == {
        "format": "image",
        "unsafe": True,
        "confidence": 0.6,
        "detected_classes": ["BUTTOCKS_EXPOSED", "FEMALE_BREAST_EXPOSED"],
    }


def test_classify_clean_image() -> None:
    assert classify("image", [], early_exit=True, contents=b"faint") == {
        "format": "image",
        "unsafe": False,
        "confidence": 0.0,
        "detected_classes": [],
    }


@pytest.mark.parametrize(
    ("file_type", "items", "checked", "total", "first_hit"),
    [
        ("video", VIDEO_FRAMES, "frames_checked", "total_frames", 5.0),
        ("pdf", PDF_PAGES, "pages_checked", "total_pages", 2),
        ("docx", DOCX_IMAGES, "images_checked", "total_images", "media/image2.png"),
        ("pptx", PPTX_IMAGES, "images_checked", "total_images", "slide_2"),
    ],
)
def test_classify_stops_at_the_first_unsafe_item(file_type, items, checked, total, first_hit) -> None:
    assert classify(file_type, items, early_exit=True) == {
        "format": file_type,
        "unsafe": True,
        "confidence": 0.6,
        "detected_classes": ["BUTTOCKS_EXPOSED", "FEMALE_BREAST_EXPOSED"],
        checked: 2,
        total: 3,
        "first_unsafe_at": first_hit,
    }


@pytest.mark.parametrize(
    ("file_type", "items", "checked", "total", "first_hit"),
    [
        ("video", VIDEO_FRAMES, "frames_checked", "total_frames", 5.0),
        ("pdf", PDF_PAGES, "pages_checked", "total_pages", 2),
        ("docx", DOCX_IMAGES, "images_checked", "total_images", "media/image2.png"),
        ("pptx", PPTX_IMAGES, "images_checked", "total_images", "slide_2"),
    ],
)
def test_classify_checks_every_item_without_early_exit(file_type, items, checked, total, first_hit) -> None:
    assert classify(file_type, items, early_exit=False) == {
        "format": file_type,
        "unsafe": True,
        "confidence": 0.9,
        "detected_classes": ["BUTTOCKS_EXPOSED", "FEMALE_BREAST_EXPOSED", "MALE_GENITALIA_EXPOSED"],
        checked: 3,
        total: 3,
        "first_unsafe_at": first_hit,
    }


@pytest.mark.parametrize(
    ("file_type", "checked", "total"),
    [
        ("video", "frames_checked", "total_frames"),
        ("pdf", "pages_checked", "total_pages"),
        ("docx", "images_checked", "total_images"),
        ("pptx", "images_checked", "total_images"),
    ],
)
@pytest.mark.parametrize("early_exit", [True, False])
def test_classify_clean_items(file_type, checked, total, early_exit: bool) -> None:
    assert classify(file_type, CLEAN_ITEMS[file_type], early_exit=early_exit) == {
        "format": file_type,
        "unsafe": False,
        "confidence": 0.0,
        "detected_classes": [],
        checked: 2,
        total: 2,
        "first_unsafe_at": None,
    }


def test_classify_unsupported_type() -> None:
    with extracted("unknown", []):
        response = app.classify_contents(b"zip", "application/zip", "archive.zip", 0.35, 5.0, True)

    assert response == {"error": "Unsupported file type: application/zip", "filename": "archive.zip"}


def test_infer_image() -> None:
    assert infer("image", [], contents=b"unsafe") == {"format": "image", "prediction": UNSAFE}


@pytest.mark.parametrize(
    ("file_type", "items", "checked", "location"),
    [
        ("video", VIDEO_FRAMES, "frames_checked", "timestamp"),
        ("pdf", PDF_PAGES, "pages_checked", "page"),
        ("docx", DOCX_IMAGES, "images_checked", "image"),
        ("pptx", PPTX_IMAGES, "images_checked", "location"),
    ],
)
def test_infer_lists_every_item_with_detections(file_type, items, checked, location) -> None:
    items = [*items, (b"none", items[-1][1])]
    expected_locations = [round(loc, 2) if file_type == "video" else loc for _, loc in items[:3]]

    assert infer(file_type, items) == {
        "format": file_type,
        checked: 4,
        "predictions": [
            {location: expected_locations[0], "detections": SAFE},
            {location: expected_locations[1], "detections": UNSAFE},
            {location: expected_locations[2], "detections": MORE_UNSAFE},
        ],
    }


def test_infer_unsupported_type() -> None:
    with extracted("unknown", []):
        response = app.infer_contents(b"zip", "application/zip", "archive.zip", 5.0)

    assert response == {"error": "Unsupported file type: application/zip", "filename": "archive.zip"}


def test_classify_lists_each_class_once_in_first_seen_order() -> None:
    with extracted("pdf", PDF_PAGES):
        response = app.classify_contents(b"upload", CONTENT_TYPES["pdf"], "upload", 0.35, 5.0, False)

    assert response["detected_classes"] == ["FEMALE_BREAST_EXPOSED", "BUTTOCKS_EXPOSED", "MALE_GENITALIA_EXPOSED"]
