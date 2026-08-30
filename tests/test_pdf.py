import asyncio
import io
import threading
from contextlib import contextmanager
from unittest.mock import Mock, patch

import nudenet
import pytest
from fastapi import HTTPException
from PIL import Image
from starlette.datastructures import Headers

with patch.object(nudenet, "NudeDetector", return_value=Mock()):
    import app


def create_pdf(page_count: int) -> bytes:
    pages = [Image.new("RGB", (24, 16), color=(index * 40, 80, 120)) for index in range(page_count)]
    output = io.BytesIO()
    pages[0].save(output, format="PDF", save_all=True, append_images=pages[1:], resolution=72)
    return output.getvalue()


def test_source_exposes_corresponding_source_location() -> None:
    assert asyncio.run(app.source()) == {
        "license": "AGPL-3.0-or-later",
        "source": "https://github.com/cmiic/media-screener-api",
    }


def test_source_url_targets_revision() -> None:
    assert app.source_url("abc123") == "https://github.com/cmiic/media-screener-api/tree/abc123"


def test_read_upload_rejects_content_beyond_limit() -> None:
    upload = app.UploadFile(file=io.BytesIO(b"12345"), filename="large.jpg")

    with patch.object(app, "MAX_UPLOAD_SIZE", 4), pytest.raises(HTTPException) as exc_info:
        asyncio.run(app.read_upload(upload))

    assert exc_info.value.status_code == 413


def test_classify_video_preserves_first_frame_timestamp() -> None:
    upload = app.UploadFile(
        file=io.BytesIO(b"video"),
        filename="video.mp4",
        headers=Headers({"content-type": "video/mp4"}),
    )
    unsafe_result = {
        "unsafe": True,
        "confidence": 0.8,
        "detected_classes": ["FEMALE_BREAST_EXPOSED"],
        "all_detections": [],
    }

    with (
        patch.object(app, "extract_video_frames", return_value=[(b"frame", 0.0)]),
        patch.object(app, "classify_image", return_value=unsafe_result),
    ):
        response = asyncio.run(
            app.classify(upload, threshold=0.35, sample_interval=5.0, early_exit=True)
        )

    assert response["unsafe"] is True
    assert response["first_unsafe_at"] == 0.0


def test_render_pdf_pages_renders_each_page_as_png() -> None:
    with app.render_pdf_pages(create_pdf(2)) as (total_pages, pages):
        rendered_pages = list(pages)

    assert total_pages == 2
    assert [page_number for _, page_number in rendered_pages] == [1, 2]
    assert all(image_bytes.startswith(b"\x89PNG\r\n\x1a\n") for image_bytes, _ in rendered_pages)


def test_render_pdf_pages_rejects_excess_pages() -> None:
    with patch.object(app, "MAX_PDF_PAGES", 1), pytest.raises(HTTPException) as exc_info:
        with app.render_pdf_pages(create_pdf(2)):
            pass

    assert exc_info.value.status_code == 422


def test_render_pdf_pages_rejects_excess_rendered_pixels() -> None:
    with patch.object(app, "MAX_PDF_RENDERED_PIXELS", 1), pytest.raises(HTTPException) as exc_info:
        with app.render_pdf_pages(create_pdf(1)) as (_, pages):
            next(pages)

    assert exc_info.value.status_code == 422


def test_extract_video_frames_rejects_excess_duration() -> None:
    capture = Mock()
    capture.get.side_effect = lambda prop: 30 if prop == app.cv2.CAP_PROP_FPS else 18_001

    with patch.object(app.cv2, "VideoCapture", return_value=capture), pytest.raises(HTTPException) as exc_info:
        app.extract_video_frames(b"video")

    assert exc_info.value.status_code == 422
    capture.release.assert_called_once()


def test_extract_video_frames_rejects_excess_samples() -> None:
    capture = Mock()
    capture.get.side_effect = lambda prop: 1 if prop == app.cv2.CAP_PROP_FPS else 2
    capture.read.side_effect = [(True, Mock()), (True, Mock()), (False, None)]
    encoded = Mock()
    encoded.tobytes.return_value = b"frame"

    with (
        patch.object(app, "MAX_VIDEO_SAMPLED_FRAMES", 1),
        patch.object(app.cv2, "VideoCapture", return_value=capture),
        patch.object(app.cv2, "imencode", return_value=(True, encoded)),
        pytest.raises(HTTPException) as exc_info,
    ):
        app.extract_video_frames(b"video", sample_interval=1)

    assert exc_info.value.status_code == 422


def test_infer_times_out_without_releasing_running_worker_slot() -> None:
    upload = app.UploadFile(
        file=io.BytesIO(b"image"),
        filename="image.jpg",
        headers=Headers({"content-type": "image/jpeg"}),
    )

    started = threading.Event()
    finished = threading.Event()

    def blocking_infer(*_args):
        started.set()
        finished.wait(timeout=1)

    async def run_timeout() -> int:
        with (
            patch.object(app, "PROCESSING_TIMEOUT_SECONDS", 0.001),
            patch.object(app, "infer_contents", side_effect=blocking_infer),
            pytest.raises(HTTPException) as exc_info,
        ):
            await app.infer(upload, sample_interval=5.0)
        assert await asyncio.to_thread(started.wait, 1)
        assert app.scan_slots.locked()
        finished.set()
        await asyncio.wait_for(app.scan_slots.acquire(), timeout=1)
        app.scan_slots.release()
        return exc_info.value.status_code

    assert asyncio.run(run_timeout()) == 504


def test_cancelled_media_request_holds_worker_slot_until_work_stops() -> None:
    started = threading.Event()
    finished = threading.Event()

    def blocking_infer(*_args):
        started.set()
        finished.wait(timeout=1)

    async def run_cancel() -> None:
        slots = asyncio.Semaphore(1)
        with patch.object(app, "scan_slots", slots):
            task = asyncio.create_task(app.process_upload(app.UploadFile(file=io.BytesIO(b"image")), blocking_infer))
            while not started.is_set():
                await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert slots.locked()
            finished.set()
            await asyncio.wait_for(slots.acquire(), timeout=1)
            slots.release()
            assert not slots.locked()

    asyncio.run(run_cancel())


def test_worker_timeout_error_is_not_misclassified_as_deadline() -> None:
    def raise_timeout(*_args):
        raise TimeoutError("parser failure")

    async def run_worker_error() -> None:
        slots = asyncio.Semaphore(1)
        with patch.object(app, "scan_slots", slots), pytest.raises(TimeoutError, match="parser failure"):
            await app.process_upload(app.UploadFile(file=io.BytesIO(b"image")), raise_timeout)
        assert not slots.locked()

    asyncio.run(run_worker_error())


def test_classify_pdf_early_exit_stops_rendering() -> None:
    consumed_pages = []
    renderer_closed = False

    @contextmanager
    def fake_render_pdf_pages(_pdf_bytes: bytes):
        nonlocal renderer_closed

        def pages():
            for page_number in range(1, 4):
                consumed_pages.append(page_number)
                yield b"png", page_number

        try:
            yield 3, pages()
        finally:
            renderer_closed = True

    upload = app.UploadFile(
        file=io.BytesIO(b"pdf"),
        filename="document.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    unsafe_result = {
        "unsafe": True,
        "confidence": 0.8,
        "detected_classes": ["FEMALE_BREAST_EXPOSED"],
        "all_detections": [],
    }

    with (
        patch.object(app, "render_pdf_pages", fake_render_pdf_pages),
        patch.object(app, "classify_image", return_value=unsafe_result),
    ):
        response = asyncio.run(
            app.classify(upload, threshold=0.35, sample_interval=5.0, early_exit=True)
        )

    assert response["pages_checked"] == 1
    assert response["total_pages"] == 3
    assert response["first_unsafe_at"] == 1
    assert consumed_pages == [1]
    assert renderer_closed
