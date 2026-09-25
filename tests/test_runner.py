import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET

from cursorcheck.core import Fixture, builtin_fixture, run_case
from cursorcheck.reference import ReferenceAdapter


class CommandAdapter:
    def __init__(self, script, rows=None):
        self.script = script
        self.rows = [] if rows is None else rows

    def command(self, run_dir, source_url):
        return [sys.executable, "-c", self.script, source_url]

    def snapshot(self, run_dir):
        return self.rows


class RunnerTests(unittest.TestCase):
    def setUp(self):
        # Normal inherited ACLs also work in restricted Windows environments.
        self.root = Path(tempfile.gettempdir()) / ("cursorcheck-test-" + uuid.uuid4().hex)
        self.root.mkdir()

    def tearDown(self):
        import shutil
        if self.root.name.startswith("cursorcheck-test-") and self.root.parent == Path(tempfile.gettempdir()):
            shutil.rmtree(self.root)

    def test_correct_connector_materializes_both_scenarios(self):
        for scenario in ("all-pages", "empty-middle-page"):
            with self.subTest(scenario=scenario):
                report = run_case(builtin_fixture(scenario), ReferenceAdapter(), self.root)
                self.assertEqual(report["status"], "pass", report)
                self.assertEqual(report["observed_count"], 4)
                with closing(sqlite3.connect(Path(report["run_dir"]) / "destination.sqlite")) as db:
                    self.assertEqual(db.execute("SELECT id FROM records ORDER BY id").fetchall(),
                                     [("alpha",), ("beta",), ("delta",), ("gamma",)])

    def test_seeded_empty_page_bug_has_exact_missing_records(self):
        report = run_case(builtin_fixture("empty-middle-page"), ReferenceAdapter(True), self.root)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["worker_exit_code"], 0)
        self.assertEqual(report["missing"], [("delta", "2"), ("gamma", "2")])
        run_dir = Path(report["run_dir"])
        requests = [json.loads(line) for line in (run_dir / "requests.jsonl").read_text().splitlines()]
        self.assertEqual([request["page"] for request in requests], [0, 1])
        self.assertTrue(requests[-1]["has_next"])
        self.assertEqual(requests[-1]["ids"], [])
        self.assertIsNotNone(ET.parse(run_dir / "junit.xml").find("testcase/failure"))
        # Replay means a fresh execution; switching to the fixed connector passes.
        fixed = run_case(Fixture.load(run_dir / "replay.json"), ReferenceAdapter(), self.root)
        self.assertEqual(fixed["status"], "pass")
        self.assertNotEqual(fixed["run_dir"], report["run_dir"])

    def test_defect_does_not_fail_ordinary_pages(self):
        report = run_case(builtin_fixture("all-pages"), ReferenceAdapter(True), self.root)
        self.assertEqual(report["status"], "pass")

    def test_first_page_only_defect_is_detected(self):
        report = run_case(builtin_fixture("all-pages"), ReferenceAdapter(mode="first-page"), self.root)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["missing"], [("delta", "2"), ("gamma", "2")])

    def test_explicit_worker_failure_is_not_silent_loss(self):
        report = run_case(builtin_fixture("all-pages"), CommandAdapter("raise SystemExit(7)"), self.root)
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["worker_exit_code"], 7)
        self.assertEqual(report["missing"], [])
        self.assertIsNotNone(ET.parse(Path(report["run_dir"]) / "junit.xml").find("testcase/error"))

    def test_hung_worker_is_bounded(self):
        report = run_case(builtin_fixture("all-pages"), CommandAdapter("import time; time.sleep(60)"),
                          self.root, timeout=1)
        self.assertEqual(report["status"], "error")
        self.assertIn("deadline", report["message"])

    def test_request_limit_cannot_pass(self):
        report = run_case(builtin_fixture("all-pages"), ReferenceAdapter(), self.root, max_requests=1)
        self.assertEqual(report["status"], "error")
        self.assertIn("request limit", report["message"])

    def test_wrong_version_and_extra_record_are_reported(self):
        adapter = CommandAdapter("pass", [("alpha", "wrong"), ("intruder", "1")])
        report = run_case(builtin_fixture("all-pages"), adapter, self.root)
        self.assertEqual(report["status"], "fail")
        self.assertIn(("alpha", "1"), report["missing"])
        self.assertEqual(report["unexpected"], [("alpha", "wrong"), ("intruder", "1")])

    def test_duplicate_destination_ids_are_not_silently_collapsed(self):
        adapter = CommandAdapter("pass", [("alpha", "1"), ("alpha", "1")])
        report = run_case(builtin_fixture("all-pages"), adapter, self.root)
        self.assertEqual(report["status"], "error")

    def test_empty_collection_with_terminal_page_passes(self):
        report = run_case(Fixture("empty", (), ((),)), ReferenceAdapter(), self.root)
        self.assertEqual(report["status"], "pass")

    def test_invalid_schedule_is_rejected_before_creating_run(self):
        with self.assertRaises(ValueError):
            run_case(Fixture("invalid", (("a", "1"),), ((),)), ReferenceAdapter(), self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_nonfinite_timeout_is_rejected(self):
        with self.assertRaises(ValueError):
            run_case(builtin_fixture("all-pages"), ReferenceAdapter(), self.root, timeout=float("nan"))

    def test_retries_recover_and_silent_retry_failure_is_detected(self):
        for mode, status in (("correct", "pass"), ("retry-as-eof", "fail")):
            with self.subTest(mode=mode):
                report = run_case(builtin_fixture("retryable-page"), ReferenceAdapter(mode=mode), self.root)
                self.assertEqual(report["status"], status, report)
                requests = [json.loads(line) for line in
                            (Path(report["run_dir"]) / "requests.jsonl").read_text().splitlines()]
                self.assertEqual([request["status"] for request in requests],
                                 [200, 429, 200] if mode == "correct" else [200, 429])

    def test_restart_detects_checkpoint_ahead_of_durable_output(self):
        for mode, status in (("correct", "pass"), ("checkpoint-ahead", "fail")):
            with self.subTest(mode=mode):
                report = run_case(builtin_fixture("restart-between-pages"), ReferenceAdapter(mode=mode), self.root)
                self.assertEqual(report["status"], status, report)
                self.assertEqual(len(report["events"]), 2)
                if mode == "checkpoint-ahead":
                    self.assertEqual(report["missing"], [("alpha", "1"), ("beta", "1")])

    def test_inclusive_cursor_keeps_new_records_with_equal_versions(self):
        for mode, status in (("correct", "pass"), ("exclusive-boundary", "fail")):
            with self.subTest(mode=mode):
                report = run_case(builtin_fixture("equal-cursor-boundary"), ReferenceAdapter(mode=mode), self.root)
                self.assertEqual(report["status"], status, report)
                if mode == "exclusive-boundary":
                    self.assertEqual([key for key, _ in report["missing"]], ["delta", "gamma"])

    def test_unsupported_recovery_never_runs_adapter_or_counts_as_pass(self):
        report = run_case(builtin_fixture("restart-between-pages"), CommandAdapter("raise SystemExit(99)"), self.root)
        self.assertEqual(report["status"], "unsupported")
        self.assertIsNone(report["worker_exit_code"])
        self.assertIsNotNone(ET.parse(Path(report["run_dir"]) / "junit.xml").find("testcase/skipped"))

    def test_finished_worker_descendants_are_terminated(self):
        # A child that outlives its parent must not keep writing after case cleanup.
        import time
        script = "import pathlib,time; p=pathlib.Path('heartbeat'); " + \
                 "exec('while True:\\n p.write_text(str(time.time()))\\n time.sleep(0.05)')"
        parent = ("import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', " +
                  repr(script) + "]); time.sleep(0.3)")
        report = run_case(builtin_fixture("all-pages"), CommandAdapter(parent), self.root)
        heartbeat = Path(report["run_dir"]) / "heartbeat"
        self.assertTrue(heartbeat.exists())
        before = heartbeat.read_text()
        time.sleep(0.2)
        self.assertEqual(heartbeat.read_text(), before)

    def test_legacy_fixture_can_be_replayed_and_upgraded(self):
        data = {"schema_version": 1, "name": "legacy", "records": [["a", "1"]], "pages": [["a"]]}
        path = self.root / "legacy.json"
        path.write_text(json.dumps(data))
        fixture = Fixture.load(path)
        self.assertEqual(fixture.as_dict()["schema_version"], 2)
        self.assertEqual(run_case(fixture, ReferenceAdapter(), self.root)["status"], "pass")


if __name__ == "__main__":
    unittest.main()
