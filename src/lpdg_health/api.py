from __future__ import annotations

import json
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .errors import InputError
from .ranker import RecencyRiskRanker
from .service import RankingService


def build_service(data_root: Path, output_root: Path) -> RankingService:
    return RankingService(data_root, output_root, RecencyRiskRanker())


def create_handler(service: RankingService):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed, query = urlparse(self.path), parse_qs(urlparse(self.path).query)
            try:
                if parsed.path == "/health":
                    return self._send(HTTPStatus.OK, {"status": "ok"})
                if parsed.path == "/rankings":
                    return self._send(HTTPStatus.OK, service.rankings(_week(query)))
                if parsed.path.startswith("/gateways/") and parsed.path.endswith("/explanation"):
                    gateway = parsed.path.removeprefix("/gateways/").removesuffix("/explanation").strip("/")
                    return self._send(HTTPStatus.OK, service.explanation(gateway, _week(query)))
                return self._send(HTTPStatus.NOT_FOUND, {"error": "route not found"})
            except KeyError as exc:
                return self._send(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except (InputError, ValueError) as exc:
                return self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

        def do_POST(self):  # noqa: N802
            if urlparse(self.path).path != "/run":
                return self._send(HTTPStatus.NOT_FOUND, {"error": "route not found"})
            try:
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")) or 0)
                payload = json.loads(body or b"{}")
                week = date.fromisoformat(payload["week_start"]) if payload.get("week_start") else None
                return self._send(HTTPStatus.OK, service.run(week))
            except (InputError, ValueError, json.JSONDecodeError) as exc:
                return self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

        def _send(self, status, payload):
            encoded = json.dumps(payload, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_args):
            pass
    return Handler


def _week(query: dict[str, list[str]]) -> date:
    values = query.get("week_start", [])
    if len(values) != 1:
        raise ValueError("week_start=YYYY-MM-DD is required.")
    return date.fromisoformat(values[0])


def serve(data_root: Path, output_root: Path, port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), create_handler(build_service(data_root, output_root)))
    print(f"Listening on http://127.0.0.1:{port}")
    server.serve_forever()

