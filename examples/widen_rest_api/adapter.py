"""Run the unmodified Widen tap and materialize its Singer records in SQLite.

This disposable sink deliberately does not acknowledge or restore Singer state.
It tests extraction completeness, not a production target's recovery protocol.
"""

from contextlib import closing
from importlib.metadata import version
from importlib.util import find_spec
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

UPSTREAM_REVISION = "071b54032beecba75f6100b90281c1d88a47dfde"


class WidenAdapter:
    required_modules = ("tap_rest_api_msdk",)
    restart_supported = False
    incremental_supported = False

    def command(self, run_dir: Path, source_url: str) -> list[str]:
        config = {
            "api_url": source_url,
            "next_page_token_path": "$.next", "pagination_next_page_param": "cursor",
            "pagination_request_style": "jsonpath_paginator", "pagination_response_style": "page",
            "backoff_type": "header", "backoff_param": "Retry-After",
            "streams": [{"name": "records", "path": "", "primary_keys": ["id"],
                         "records_path": "$.items[*]", "schema": {"type": "object", "properties": {
                             "id": {"type": "string"}, "version": {"type": "string"}}}}],
        }
        (run_dir / "tap-config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
        (run_dir / "adapter.json").write_text(json.dumps({
            "tap-rest-api-msdk": version("tap-rest-api-msdk"), "singer-sdk": version("singer-sdk"),
            "upstream_base_revision": UPSTREAM_REVISION,
            "streams_sha256_lf": hashlib.sha256(Path(find_spec("tap_rest_api_msdk").origin)
                                                .with_name("streams.py").read_bytes()
                                                .replace(b"\r\n", b"\n")).hexdigest(),
            "destination": "disposable Singer RECORD-to-SQLite sink",
            "production_target": False,
        }, indent=2), encoding="utf-8")
        return [sys.executable, str(Path(__file__).resolve()), "load"]

    def snapshot(self, run_dir: Path) -> list[tuple[str, str]]:
        with closing(sqlite3.connect((run_dir / "destination.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
            return db.execute("SELECT id, version FROM records ORDER BY id").fetchall()


def build_adapter() -> WidenAdapter:
    return WidenAdapter()


def extract():
    from tap_rest_api_msdk.tap import TapRestApiMsdk

    config = json.loads(Path("tap-config.json").read_text(encoding="utf-8"))
    tap = TapRestApiMsdk(config=config, parse_env_config=False)
    streams = list(tap.streams.values())
    for stream in streams:
        stream.requests_session.trust_env = False
    try:
        tap.sync_all()
    finally:
        for stream in streams:
            stream.requests_session.close()


def load():
    # A real tap subprocess emits the Singer protocol. Propagate its exit code;
    # explicit connector errors must never be classified as silent loss.
    with Path("singer.jsonl").open("wb") as messages:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "extract"], stdout=messages)
    if result.returncode:
        raise SystemExit(result.returncode)
    with closing(sqlite3.connect("destination.sqlite")) as db:
        db.execute("CREATE TABLE records (id TEXT PRIMARY KEY, version TEXT NOT NULL)")
        with Path("singer.jsonl").open(encoding="utf-8") as messages, db:
            for line in messages:
                message = json.loads(line)
                if message["type"] == "RECORD":
                    if message["stream"] != "records":
                        raise ValueError("unexpected stream")
                    row = message["record"]
                    db.execute("INSERT OR REPLACE INTO records VALUES (?, ?)", (row["id"], row["version"]))


if __name__ == "__main__":
    {"extract": extract, "load": load}[sys.argv[1]]()
