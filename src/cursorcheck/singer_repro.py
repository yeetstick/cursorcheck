"""Historical Singer SDK empty-page reproduction, with a minimal SQLite sink.

This is a synthetic RESTStream, not a production tap/target or recovery adapter.
The SDK owns requests, pagination and retries; only its documented extension
points are configured here. No pagination loop is copied or patched.
"""

from contextlib import closing
from pathlib import Path
import sqlite3
import sys


class SingerReproduction:
    required_modules = ("singer_sdk",)
    restart_supported = False
    incremental_supported = False

    def __init__(self, continue_empty=True):
        self.continue_empty = continue_empty

    def command(self, run_dir: Path, source_url: str) -> list[str]:
        return [sys.executable, "-m", "cursorcheck.singer_repro", source_url,
                "continue" if self.continue_empty else "default"]

    def snapshot(self, run_dir: Path) -> list[tuple[str, str]]:
        uri = (run_dir / "destination.sqlite").as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            return db.execute("SELECT id, version FROM records ORDER BY id").fetchall()


def build_adapter() -> SingerReproduction:
    return SingerReproduction()


def build_default_adapter() -> SingerReproduction:
    return SingerReproduction(continue_empty=False)


def load(source_url: str, continue_empty: bool) -> None:
    from importlib.metadata import version
    import json
    from singer_sdk import Tap, RESTStream
    from singer_sdk.pagination import JSONPathPaginator

    class ContinuingPaginator(JSONPathPaginator):
        # SDK <0.46.0 never calls this hook. The identical class demonstrates
        # both the historical limitation and the opt-in behavior after the fix.
        def continue_if_empty(self, response):
            return self.get_next(response) is not None

    class Records(RESTStream):
        name = "records"
        url_base = source_url
        path = ""
        records_jsonpath = "$.items[*]"
        primary_keys = ["id"]
        schema = {"type": "object", "properties": {
            "id": {"type": "string"}, "version": {"type": "string"}}}

        def get_new_paginator(self):
            paginator = ContinuingPaginator if continue_empty else JSONPathPaginator
            return paginator("$.next")

        def get_url_params(self, context, next_page_token):
            return {"cursor": next_page_token} if next_page_token is not None else {}

    class ReproductionTap(Tap):
        name = "cursorcheck-singer-reproduction"

        def discover_streams(self):
            return [Records(self)]

    Path("adapter.json").write_text(json.dumps({
        "singer-sdk": version("singer-sdk"), "continue_if_empty": continue_empty,
        "destination": "minimal SQLite sink (not a Singer target)",
        "synthetic_configuration": True,
    }, indent=2), encoding="utf-8")
    stream = Records(ReproductionTap(config={}))
    stream.requests_session.trust_env = False
    try:
        with closing(sqlite3.connect("destination.sqlite")) as db:
            db.execute("CREATE TABLE records (id TEXT PRIMARY KEY, version TEXT NOT NULL)")
            for row in stream.request_records(context=None):
                with db:
                    db.execute("INSERT OR REPLACE INTO records VALUES (?, ?)", (row["id"], row["version"]))
    finally:
        stream.requests_session.close()


if __name__ == "__main__":
    load(sys.argv[1], sys.argv[2] == "continue")
