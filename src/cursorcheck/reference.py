"""Synthetic reference connector with an explicitly seeded empty-page defect."""

import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import build_opener, ProxyHandler


class ReferenceAdapter:
    restart_supported = True
    incremental_supported = True

    def __init__(self, defective: bool = False, *, mode: str | None = None):
        self.mode = mode or ("empty-page" if defective else "correct")

    def command(self, run_dir: Path, source_url: str) -> list[str]:
        (run_dir / "adapter.json").write_text(json.dumps({"adapter": "reference", "mode": self.mode,
                                                        "synthetic_configuration": True}), encoding="utf-8")
        return [sys.executable, "-m", "cursorcheck.reference", source_url,
                str(run_dir / "destination.sqlite"), self.mode]

    def snapshot(self, run_dir: Path) -> list[tuple[str, str]]:
        uri = (run_dir / "destination.sqlite").as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as database:
            return database.execute("SELECT id, version FROM records ORDER BY id").fetchall()


def build_adapter() -> ReferenceAdapter:
    return ReferenceAdapter()


def build_retry_defect() -> ReferenceAdapter:
    return ReferenceAdapter(mode="retry-as-eof")


def build_restart_defect() -> ReferenceAdapter:
    return ReferenceAdapter(mode="checkpoint-ahead")


def build_boundary_defect() -> ReferenceAdapter:
    return ReferenceAdapter(mode="exclusive-boundary")


def extract(url: str, path: str, mode: str) -> None:
    # Explicitly bypass environment proxies for the owned loopback source.
    client = build_opener(ProxyHandler({}))
    with closing(sqlite3.connect(path)) as database:
        database.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, version TEXT NOT NULL)")
        database.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)")
        saved = dict(database.execute("SELECT key, value FROM state"))
        token, since = saved.get("token"), saved.get("since")
        pending = []
        retries = 0
        newest = since
        while True:
            params = {}
            if token is not None:
                params["cursor"] = token
            if since is not None:
                params["since"] = since
            request_url = url + ("?" + urlencode(params) if params else "")
            try:
                with client.open(request_url, timeout=5) as response:
                    page = json.load(response)
            except HTTPError as exc:
                if exc.code != 429 or retries >= 2:
                    raise
                if mode == "retry-as-eof":
                    break
                retries += 1
                time.sleep(min(float(exc.headers.get("Retry-After", "1")), 2))
                continue
            rows = [(row["id"], row["version"]) for row in page["items"]]
            if mode == "exclusive-boundary" and since is not None:
                rows = [(key, version) for key, version in rows if version > since]
            if rows:
                newest = max([version for _, version in rows] + ([newest] if newest else []))
            # Correct mode commits output and next token in one transaction.
            # Seeded checkpoint defect saves the token while output remains buffered.
            materialize = pending if mode == "checkpoint-ahead" else rows
            database.executemany("INSERT OR REPLACE INTO records VALUES (?, ?)", materialize)
            pending = rows if mode == "checkpoint-ahead" else []
            database.execute("INSERT OR REPLACE INTO state VALUES ('token', ?)", (page["next"],))
            database.commit()
            if mode == "empty-page" and not page["items"]:
                break  # Seeded defect: an empty page does not mean no continuation.
            if mode == "first-page":
                break
            token = page["next"]
            if token is None:
                database.executemany("INSERT OR REPLACE INTO records VALUES (?, ?)", pending)
                database.execute("INSERT OR REPLACE INTO state VALUES ('since', ?)", (newest,))
                database.commit()
                break


if __name__ == "__main__":
    extract(sys.argv[1], sys.argv[2], sys.argv[3])
