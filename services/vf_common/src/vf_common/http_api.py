"""Minimal JSON/HTML HTTP API for the services (standard library only, like the ops gateway): routes are
(method, regular expression) -> handler(request) -> Response. Used by erp, alarms and sustainability."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

log = logging.getLogger("vf.http")


@dataclass
class Request:
    method: str
    path: str
    params: dict[str, str]
    match: re.Match
    body: Any = None


@dataclass
class Response:
    status: int = 200
    body: Any = field(default_factory=dict)
    content_type: str = "application/json"

    def encode(self) -> bytes:
        if isinstance(self.body, bytes):
            return self.body
        if isinstance(self.body, str):
            return self.body.encode()
        return json.dumps(self.body, default=str).encode()


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


Handler = Callable[[Request], Response | dict | list]


class Router:
    def __init__(self):
        self.routes: list[tuple[str, re.Pattern, Handler]] = []

    def add(self, method: str, pattern: str, handler: Handler) -> None:
        self.routes.append((method, re.compile(f"^{pattern}$"), handler))

    def dispatch(self, method: str, url: str, raw: bytes = b"") -> Response:
        parsed = urlparse(url)
        params = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        allowed = False
        for route_method, pattern, handler in self.routes:
            match = pattern.match(parsed.path.rstrip("/") or "/")
            if not match:
                continue
            allowed = True
            if route_method != method:
                continue
            return self._call(handler, Request(method, parsed.path, params, match), raw)
        return Response(405 if allowed else 404, {"error": "method not allowed" if allowed else "not found"})

    @staticmethod
    def _call(handler: Handler, request: Request, raw: bytes) -> Response:
        try:
            request.body = json.loads(raw) if raw.strip() else None
        except ValueError:
            return Response(400, {"error": "body is not valid JSON"})
        try:
            result = handler(request)
        except ApiError as exc:
            return Response(exc.status, {"error": str(exc)})
        except (KeyError, ValueError, TypeError) as exc:
            return Response(400, {"error": f"invalid request: {exc}"})
        return result if isinstance(result, Response) else Response(200, result)


def make_handler(router: Router) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        def _serve(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            response = router.dispatch(self.command, self.path, self.rfile.read(length) if length else b"")
            data = response.encode()
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = do_PUT = do_DELETE = _serve  # noqa: N815

        def do_OPTIONS(self) -> None:  # noqa: N802 - CORS preflight (browser clients)
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def log_message(self, fmt: str, *args) -> None:
            log.debug(fmt, *args)

    return _Handler


def serve(router: Router, port: int) -> ThreadingHTTPServer:
    """Server on all interfaces; call serve_forever() (or run it in a thread)."""
    return ThreadingHTTPServer(("0.0.0.0", port), make_handler(router))
