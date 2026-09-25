"""Small public interface for a bounded pagination experiment."""

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from typing import Protocol
import uuid
import xml.etree.ElementTree as ET

from .supervisor import Worker


@dataclass(frozen=True)
class Fixture:
    """Independent records and an explicit, complete pagination schedule."""

    name: str
    records: tuple[tuple[str, str], ...]
    pages: tuple[tuple[str, ...], ...]
    retry_page: int | None = None
    restart_page: int | None = None
    initial_ids: tuple[str, ...] | None = None

    def validate(self) -> None:
        if not isinstance(self.name, str) or not self.name or len(self.name) > 100 or not self.name.isprintable():
            raise ValueError("fixture name must contain 1–100 characters")
        if not 1 <= len(self.pages) <= 100 or len(self.records) > 1000:
            raise ValueError("fixture limit: 1–100 pages and at most 1000 records")
        for row in self.records:
            if len(row) != 2 or any(not isinstance(v, str) or not v or len(v) > 256 for v in row):
                raise ValueError("records require nonempty string id/version, at most 256 characters")
        ids = [row[0] for row in self.records]
        served = [key for page in self.pages for key in page]
        if any(not isinstance(key, str) for key in served):
            raise ValueError("page IDs must be strings")
        if len(ids) != len(set(ids)) or sorted(served) != sorted(ids):
            raise ValueError("each unique record ID must appear in exactly one page")
        for index in (self.retry_page, self.restart_page):
            if index is not None and (type(index) is not int or not 0 < index < len(self.pages)):
                raise ValueError("fault page must be an existing noninitial page")
        if sum(x is not None for x in (self.retry_page, self.restart_page, self.initial_ids)) > 1:
            raise ValueError("this fixture version supports one scenario mechanism at a time")
        if self.initial_ids is not None:
            if any(not isinstance(key, str) for key in self.initial_ids):
                raise ValueError("initial IDs must be strings")
            if not self.initial_ids or len(set(self.initial_ids)) != len(self.initial_ids) or not set(self.initial_ids) < set(ids):
                raise ValueError("initial IDs must be a nonempty proper subset of record IDs")
            if len({version for _, version in self.records}) != 1:
                raise ValueError("equal-cursor scenario requires one common boundary version")

    def as_dict(self) -> dict:
        self.validate()
        return {"schema_version": 2, "name": self.name,
                "records": [list(row) for row in self.records],
                "pages": [list(page) for page in self.pages],
                "retry_page": self.retry_page, "restart_page": self.restart_page,
                "initial_ids": list(self.initial_ids) if self.initial_ids is not None else None}

    @classmethod
    def load(cls, path: Path) -> "Fixture":
        if path.stat().st_size > 1_000_000:
            raise ValueError("fixture exceeds 1 MB")
        data = json.loads(path.read_text(encoding="utf-8"))
        base = {"schema_version", "name", "records", "pages"}
        if not isinstance(data, dict) or set(data) not in (base, base | {"retry_page", "restart_page", "initial_ids"}):
            raise ValueError("invalid fixture fields")
        if type(data["schema_version"]) is not int or data["schema_version"] not in (1, 2):
            raise ValueError("unsupported fixture schema")
        if (data["schema_version"] == 1) != (set(data) == base):
            raise ValueError("fixture fields do not match schema version")
        if not isinstance(data["records"], list) or not isinstance(data["pages"], list):
            raise ValueError("records and pages must be arrays")
        if any(not isinstance(row, list) for row in data["records"] + data["pages"]):
            raise ValueError("records and pages must contain arrays")
        initial = data.get("initial_ids")
        if initial is not None and not isinstance(initial, list):
            raise ValueError("initial_ids must be an array or null")
        fixture = cls(data["name"], tuple(tuple(row) for row in data["records"]),
                      tuple(tuple(page) for page in data["pages"]), data.get("retry_page"),
                      data.get("restart_page"), tuple(initial) if initial is not None else None)
        fixture.validate()
        return fixture


def builtin_fixture(name: str) -> Fixture:
    records = (("alpha", "1"), ("beta", "1"), ("gamma", "2"), ("delta", "2"))
    pages = (("alpha", "beta"), ("gamma", "delta"))
    if name == "empty-middle-page":
        pages = (pages[0], (), pages[1])
    elif name == "retryable-page":
        return Fixture(name, records, pages, retry_page=1)
    elif name == "restart-between-pages":
        return Fixture(name, records, pages, restart_page=1)
    elif name == "equal-cursor-boundary":
        return Fixture(name, tuple((key, "2026-01-01T00:00:00Z") for key, _ in records), pages,
                       initial_ids=("alpha", "beta"))
    elif name != "all-pages":
        raise ValueError(f"unsupported scenario: {name}")
    return Fixture(name, records, pages)


class Adapter(Protocol):
    """Trusted project code: wire a real worker, then read its durable output.

    This implementation supports owned workers and upsert output only.
    Optional restart_supported and incremental_supported flags opt into recovery.
    """

    def command(self, run_dir: Path, source_url: str) -> list[str]: ...

    def snapshot(self, run_dir: Path) -> list[tuple[str, str]]: ...


class _ExecutionError(Exception):
    """Harness-authored diagnostic safe to include in a report."""


def _stop(process: subprocess.Popen | None) -> None:
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def _save_reports(directory: Path, report: dict) -> None:
    (directory / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    status = report["status"]
    suite = ET.Element("testsuite", name="cursorcheck", tests="1",
                       failures=str(int(status == "fail")), errors=str(int(status == "error")),
                       skipped=str(int(status == "unsupported")))
    case = ET.SubElement(suite, "testcase", name=report["scenario"], classname="cursorcheck")
    if status == "unsupported":
        ET.SubElement(case, "skipped", message=report["message"])
    elif status != "pass":
        ET.SubElement(case, "failure" if status == "fail" else "error",
                      message=report["message"]).text = json.dumps(report, indent=2)
    ET.ElementTree(suite).write(directory / "junit.xml", encoding="utf-8", xml_declaration=True)


def run_case(fixture: Fixture, adapter: Adapter, output: Path, *, timeout: float = 10,
             max_requests: int = 100) -> dict:
    """Run fresh HTTP and worker processes, compare durable rows, save evidence.

    The deadline bounds child execution. Adapter methods are trusted local calls
    and must return promptly. A worker error is never labeled silent data loss.
    """
    fixture.validate()
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0.1 <= timeout <= 300:
        raise ValueError("timeout must be between 0.1 and 300 seconds")
    if type(max_requests) is not int or not 1 <= max_requests <= 1000:
        raise ValueError("max_requests must be between 1 and 1000")
    directory = output.resolve() / uuid.uuid4().hex
    directory.mkdir(parents=True)
    fixture_path = directory / "replay.json"
    fixture_path.write_text(json.dumps(fixture.as_dict(), indent=2), encoding="utf-8")
    env = os.environ.copy()
    # Preserve importability for source checkouts and explicitly selected adapters.
    env["PYTHONPATH"] = os.pathsep.join(str(Path(p).resolve()) for p in sys.path if p)
    secret = secrets.token_hex(16)
    server = worker = None
    report = {"schema_version": 1, "scenario": fixture.name, "status": "error",
              "message": "run did not complete", "adapter": f"{type(adapter).__module__}:{type(adapter).__qualname__}",
              "python": sys.version.split()[0], "run_dir": str(directory),
              "expected_count": len(fixture.records), "observed_count": None,
              "missing": [], "unexpected": [], "worker_exit_code": None, "events": []}
    if ((fixture.restart_page is not None and not getattr(adapter, "restart_supported", False)) or
        (fixture.initial_ids is not None and not getattr(adapter, "incremental_supported", False))):
        report.update(status="unsupported", message="adapter has not declared the required persistence capability")
        _save_reports(directory, report)
        return report
    started = time.monotonic()
    deadline = started + timeout
    try:
        server = subprocess.Popen(
            [sys.executable, "-m", "cursorcheck.source", str(directory), secret, str(max_requests)],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ready = directory / "ready.json"
        while not ready.exists():
            if server.poll() is not None:
                raise _ExecutionError("fixture server exited before readiness")
            if time.monotonic() >= deadline:
                raise _ExecutionError("fixture server startup exceeded case deadline")
            time.sleep(0.01)
        port = json.loads(ready.read_text(encoding="utf-8"))["port"]
        command = adapter.command(directory, f"http://127.0.0.1:{port}/{secret}")
        if not isinstance(command, list) or not command or any(not isinstance(arg, str) for arg in command):
            raise ValueError("adapter.command must return a nonempty argv list")
        worker = Worker(command, cwd=directory, env=env)
        if fixture.restart_page is not None:
            while not (directory / "request-blocked").exists():
                if worker.poll() is not None:
                    raise _ExecutionError("worker exited before the required interruption boundary")
                if time.monotonic() >= deadline:
                    raise _ExecutionError("case deadline exceeded before interruption boundary")
                time.sleep(0.01)
            worker.close()
            report["events"].append("worker terminated while next source request was blocked")
            (directory / "release-request").touch()
            worker = Worker(command, cwd=directory, env=env)
            report["events"].append("worker restarted with existing destination and state")
        report["worker_exit_code"] = worker.wait(timeout=max(0.001, deadline - time.monotonic()))
        if fixture.initial_ids is not None and report["worker_exit_code"] == 0:
            worker.close()
            (directory / "phase-two").touch()
            report["events"].append("second sync exposes new IDs at inclusive saved cursor boundary")
            worker = Worker(command, cwd=directory, env=env)
            report["worker_exit_code"] = worker.wait(timeout=max(0.001, deadline - time.monotonic()))
        if server.poll() is not None:
            raise _ExecutionError("fixture server exited during the case")
        if (directory / "limit-exceeded").exists():
            raise _ExecutionError("source request limit exceeded")
        if report["worker_exit_code"] != 0:
            raise _ExecutionError(f"connector explicitly failed (exit {report['worker_exit_code']}); completeness unassessed")
        observed = adapter.snapshot(directory)
        if not isinstance(observed, list) or len(observed) > 1000:
            raise ValueError("snapshot must return at most 1000 durable id/version pairs")
        if any(not isinstance(row, tuple) or len(row) != 2 or
               any(not isinstance(v, str) for v in row) for row in observed):
            raise ValueError("snapshot rows must be string (id, version) tuples")
        if len({row[0] for row in observed}) != len(observed):
            raise ValueError("snapshot violates declared upsert semantics: duplicate IDs")
        expected, actual = set(fixture.records), set(observed)
        report.update(observed_count=len(observed), missing=sorted(expected - actual),
                      unexpected=sorted(actual - expected))
        good = expected == actual
        report.update(status="pass" if good else "fail",
                      message="all expected records materialized" if good else "successful connector output differs from source oracle")
    except Exception as exc:
        # Do not export adapter exception messages: they may contain credentials.
        report.update(status="error", message="case deadline exceeded" if isinstance(exc, subprocess.TimeoutExpired)
                      else f"execution or adapter error ({type(exc).__name__})")
        if isinstance(exc, _ExecutionError):
            report["message"] = str(exc)
    finally:
        try:
            if worker is not None:
                worker.close()
        finally:
            _stop(server)
    report["duration_seconds"] = round(time.monotonic() - started, 3)
    _save_reports(directory, report)
    return report
