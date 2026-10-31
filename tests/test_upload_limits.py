"""The limits UploadRoute applies to an upload request before FastAPI parses its body."""

import asyncio
import json
from unittest.mock import Mock, patch

import nudenet
import pytest

with patch.object(nudenet, "NudeDetector", return_value=Mock()):
    import app

BOUNDARY = "limits-test-boundary"


def multipart(*parts: tuple[str, bytes]) -> bytes:
    """A multipart/form-data body with one file part per (field name, content)."""
    body = b""
    for name, content in parts:
        body += (
            f"--{BOUNDARY}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{name}.bin"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        body += content + b"\r\n"
    return body + f"--{BOUNDARY}--\r\n".encode()


class Client:
    """Sends one POST through the ASGI app as uvicorn does, recording how much of the body the app asked for."""

    def __init__(self, chunks: list[bytes], content_length: int | None = None, stall: bool = False) -> None:
        self.chunks = chunks
        self.content_length = content_length
        self.stall = stall
        self.chunks_read = 0
        self.messages: list[dict] = []

    async def receive(self) -> dict:
        if self.chunks_read < len(self.chunks):
            chunk = self.chunks[self.chunks_read]
            self.chunks_read += 1
            more = self.stall or self.chunks_read < len(self.chunks)
            return {"type": "http.request", "body": chunk, "more_body": more}
        # Nothing more to send: a stalled client, or one waiting for its response.
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(self, message: dict) -> None:
        self.messages.append(message)

    async def post(self, path: str) -> tuple[int, dict]:
        headers = [(b"content-type", f"multipart/form-data; boundary={BOUNDARY}".encode())]
        if self.content_length is not None:
            headers.append((b"content-length", str(self.content_length).encode()))
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "client": ("127.0.0.1", 1),
            "server": ("test", 80),
        }
        await app.app(scope, self.receive, self.send)
        status = next(m["status"] for m in self.messages if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in self.messages if m["type"] == "http.response.body")
        return status, json.loads(body)


def chunked(body: bytes, size: int = 64) -> list[bytes]:
    return [body[i : i + size] for i in range(0, len(body), size)]


@pytest.fixture
def small_limits():
    """A 100-byte file limit with 200 bytes for the multipart framing, and one free scan slot."""
    with (
        patch.object(app, "MAX_UPLOAD_SIZE", 100),
        patch.object(app, "MULTIPART_OVERHEAD", 200),
        patch.object(app, "scan_slots", asyncio.Semaphore(1)),
        patch.object(app, "SCAN_QUEUE_TIMEOUT_SECONDS", 0.05),
        patch.object(app, "UPLOAD_TIMEOUT_SECONDS", 0.2),
    ):
        yield


@pytest.mark.parametrize(("path", "operation"), [("/infer", "infer_contents"), ("/classify", "classify_contents")])
def test_upload_within_limits_is_processed_in_its_slot(small_limits, path: str, operation: str) -> None:
    slot_held_while_processing = []

    def process(*_args):
        slot_held_while_processing.append(app.scan_slots.locked())
        return {}

    body = multipart(("file", b"x" * 100))
    client = Client(chunked(body), content_length=len(body))
    with patch.object(app, operation, side_effect=process):
        status, _ = asyncio.run(client.post(path))

    assert status == 200
    assert slot_held_while_processing == [True]
    assert not app.scan_slots.locked()


@pytest.mark.parametrize("path", ["/infer", "/classify"])
def test_declared_oversized_body_is_refused_unread(small_limits, path: str) -> None:
    body = multipart(("file", b"x" * 400))
    client = Client(chunked(body), content_length=len(body))
    with patch.object(app, "infer_contents") as infer_contents:
        status, response = asyncio.run(client.post(path))

    assert status == 413
    assert response["detail"] == "File exceeds the 100-byte upload limit"
    assert client.chunks_read == 0
    infer_contents.assert_not_called()
    assert not app.scan_slots.locked()


@pytest.mark.parametrize(
    "body",
    [
        multipart(("file", b"x" * 400)),
        # The selected file is within the limit; a second part is not.
        multipart(("file", b"x" * 10), ("extra", b"y" * 400)),
    ],
    ids=["oversized-file", "oversized-extra-part"],
)
def test_undeclared_oversized_body_is_refused_while_it_arrives(small_limits, body: bytes) -> None:
    client = Client(chunked(body))
    with patch.object(app, "infer_contents") as infer_contents:
        status, _ = asyncio.run(client.post("/infer"))

    assert status == 413
    # Refused at the chunk that crossed the 300-byte body limit, not at the end.
    assert client.chunks_read == 5 < len(client.chunks)
    infer_contents.assert_not_called()
    assert not app.scan_slots.locked()


def test_understated_content_length_does_not_widen_the_limit(small_limits) -> None:
    body = multipart(("file", b"x" * 400))
    client = Client(chunked(body), content_length=10)
    with patch.object(app, "infer_contents") as infer_contents:
        status, _ = asyncio.run(client.post("/infer"))

    assert status == 413
    infer_contents.assert_not_called()


def test_slow_body_times_out(small_limits) -> None:
    body = multipart(("file", b"x" * 50))
    client = Client(chunked(body)[:1], stall=True)
    with patch.object(app, "infer_contents") as infer_contents:
        status, response = asyncio.run(client.post("/infer"))

    assert status == 408
    assert response["detail"] == "Upload timed out"
    infer_contents.assert_not_called()
    assert not app.scan_slots.locked()


def test_buffered_chunk_after_the_deadline_times_out() -> None:
    async def buffered() -> dict:
        return {"type": "http.request", "body": b"late", "more_body": False}

    async def run() -> int:
        with patch.object(app, "UPLOAD_TIMEOUT_SECONDS", 0.01):
            receive = app.limit_body(buffered, 100)
            await asyncio.sleep(0.02)  # the parser was busy past the deadline
            with pytest.raises(app.HTTPException) as exc_info:
                await receive()
        return exc_info.value.status_code

    assert asyncio.run(run()) == 408


def test_upload_waits_for_a_slot_before_its_body_is_read(small_limits) -> None:
    body = multipart(("file", b"x" * 50))

    async def run() -> tuple[int, int]:
        await app.scan_slots.acquire()  # another upload is being received or scanned
        try:
            client = Client(chunked(body), content_length=len(body))
            status, _ = await client.post("/infer")
            return status, client.chunks_read
        finally:
            app.scan_slots.release()

    with patch.object(app, "infer_contents") as infer_contents:
        status, chunks_read = asyncio.run(run())

    assert status == 503
    assert chunks_read == 0
    infer_contents.assert_not_called()
