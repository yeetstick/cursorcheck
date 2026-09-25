"""Owned loopback fixture process; transcript captures IDs, never payloads."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
import time
from urllib.parse import parse_qs, urlsplit

from .core import Fixture


def serve(directory: Path, secret: str, max_requests: int) -> None:
    fixture = Fixture.load(directory / "replay.json")
    records = dict(fixture.records)
    tokens = [f"opaque-{i}-end" for i in range(len(fixture.pages))]
    count = 0
    retried = blocked = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            nonlocal count, retried, blocked
            count += 1
            parts = urlsplit(self.path)
            query = parse_qs(parts.query)
            token = query.get("cursor", [tokens[0]])[0]
            status = 200
            page = None
            if count > max_requests:
                (directory / "limit-exceeded").touch()
                status, body = 429, {"error": "request limit exceeded"}
            elif parts.path != f"/{secret}" or set(query) - {"cursor", "since"} or token not in tokens:
                status, body = 400, {"error": "invalid source request"}
            else:
                page = tokens.index(token)
                if page == fixture.restart_page and not blocked:
                    blocked = True
                    (directory / "request-blocked").touch()
                    while not (directory / "release-request").exists():
                        time.sleep(0.01)
                ids = fixture.pages[page]
                if fixture.initial_ids is not None and not (directory / "phase-two").exists():
                    ids = tuple(key for key in ids if key in fixture.initial_ids)
                since = query.get("since", [None])[0]
                if since is not None:
                    ids = tuple(key for key in ids if records[key] >= since)
                body = {"items": [{"id": key, "version": records[key]} for key in ids],
                        "next": tokens[page + 1] if page + 1 < len(tokens) else None}
                if page == fixture.retry_page and not retried:
                    retried = True
                    status, body = 429, {"error": "scheduled retryable response"}
            # Cap journal growth even if a worker disregards errors.
            if count <= max_requests + 1:
                with (directory / "requests.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"request": count, "page": page, "status": status,
                                             "ids": [row["id"] for row in body.get("items", [])],
                                             "has_next": bool(body.get("next"))}) + "\n")
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            if status == 429:
                self.send_header("Retry-After", "1")
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        ready = directory / "ready.tmp"
        ready.write_text(json.dumps({"port": server.server_port}), encoding="utf-8")
        ready.replace(directory / "ready.json")
        server.serve_forever()


if __name__ == "__main__":
    serve(Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]))
