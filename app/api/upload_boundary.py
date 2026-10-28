"""Authenticate and cap upload bodies before multipart parsing or spooling."""

import tempfile

from starlette.responses import JSONResponse

from app.api.auth import valid_basic_header
from app.infrastructure.storage import MAX_COVER_BYTES, MAX_EPUB_BYTES

MAX_REQUEST_BYTES = MAX_EPUB_BYTES + MAX_COVER_BYTES + 1024 * 1024
MAX_OTHER_BODY_BYTES = 64 * 1024


class UploadBoundaryMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        upload = scope.get("method") == "POST" and scope.get("path") == "/api/v1/books"
        headers = dict(scope.get("headers", []))
        if upload and not valid_basic_header(headers.get(b"authorization")):
            await JSONResponse({"detail": "Invalid administrator credentials"}, status_code=401, headers={"WWW-Authenticate": "Basic"})(scope, receive, send)
            return
        max_bytes = MAX_REQUEST_BYTES if upload else MAX_OTHER_BODY_BYTES
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = 0
        if length > max_bytes:
            await JSONResponse({"detail": "Upload request too large"}, status_code=413)(scope, receive, send)
            return
        consumed = 0
        with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as spool:
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    await JSONResponse({"detail": "Client disconnected"}, status_code=400)(scope, receive, send)
                    return
                chunk = message.get("body", b"")
                consumed += len(chunk)
                if consumed > max_bytes:
                    await JSONResponse({"detail": "Upload request too large"}, status_code=413)(scope, receive, send)
                    return
                spool.write(chunk)
                if not message.get("more_body", False):
                    break
            spool.seek(0)
            replay_finished = False

            async def replay_receive():
                nonlocal replay_finished
                if replay_finished:
                    return await receive()
                chunk = spool.read(1024 * 1024)
                if chunk:
                    return {"type": "http.request", "body": chunk, "more_body": True}
                replay_finished = True
                return {"type": "http.request", "body": b"", "more_body": False}

            await self.app(scope, replay_receive, send)
