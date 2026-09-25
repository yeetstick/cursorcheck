import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from cursorcheck.core import builtin_fixture, run_case
from cursorcheck.dlt_adapter import DltAdapter


@unittest.skipUnless(importlib.util.find_spec("dlt") and importlib.util.find_spec("duckdb"),
                     "optional dlt/DuckDB dependencies not installed")
class DltIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.gettempdir()) / ("cursorcheck-dlt-test-" + uuid.uuid4().hex)
        self.root.mkdir()

    def tearDown(self):
        import shutil
        if self.root.name.startswith("cursorcheck-dlt-test-") and self.root.parent == Path(tempfile.gettempdir()):
            shutil.rmtree(self.root)

    def test_dlt_loads_all_pages_and_continues_after_empty_page(self):
        for name in ("all-pages", "empty-middle-page"):
            with self.subTest(scenario=name):
                report = run_case(builtin_fixture(name), DltAdapter(), self.root, timeout=30)
                self.assertEqual(report["status"], "pass", report)
                self.assertEqual(report["observed_count"], 4)
                requests = [json.loads(line) for line in
                            (Path(report["run_dir"]) / "requests.jsonl").read_text().splitlines()]
                self.assertEqual(len(requests), 2 if name == "all-pages" else 3)

    def test_single_page_misconfiguration_is_detected_from_duckdb(self):
        report = run_case(builtin_fixture("all-pages"), DltAdapter(single_page=True), self.root, timeout=30)
        self.assertEqual(report["status"], "fail", report)
        self.assertEqual(report["worker_exit_code"], 0)
        self.assertEqual(report["missing"], [("delta", "2"), ("gamma", "2")])

    def test_dlt_retry_restart_and_equal_cursor_scenarios(self):
        for name in ("retryable-page", "restart-between-pages", "equal-cursor-boundary"):
            with self.subTest(scenario=name):
                report = run_case(builtin_fixture(name), DltAdapter(), self.root, timeout=30)
                self.assertEqual(report["status"], "pass", report)
                self.assertEqual(report["observed_count"], 4)

    def test_reported_dependent_resource_pattern_and_explicit_workaround(self):
        for mode, status in (("child-client", "fail"), ("child-endpoint", "pass")):
            with self.subTest(mode=mode):
                report = run_case(builtin_fixture("all-pages"), DltAdapter(mode=mode), self.root, timeout=30)
                self.assertEqual(report["status"], status, report)
                self.assertEqual(report["worker_exit_code"], 0)
