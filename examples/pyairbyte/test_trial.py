"""Real HTTP extraction and DuckDB materialization, including a negative control."""

import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
import uuid

from adapter import PyAirbyteAdapter
from cursorcheck.core import builtin_fixture, run_case


class PyAirbyteTrialTests(unittest.TestCase):
    def test_framework_and_destination(self):
        root = Path(tempfile.gettempdir()) / ("cursorcheck-airbyte-test-" + uuid.uuid4().hex)
        root.mkdir()
        try:
            for scenario in ("all-pages", "empty-middle-page", "retryable-page",
                             "restart-between-pages", "equal-cursor-boundary"):
                with self.subTest(scenario=scenario):
                    report = run_case(builtin_fixture(scenario), PyAirbyteAdapter(), root, timeout=90)
                    if scenario in ("restart-between-pages", "equal-cursor-boundary"):
                        self.assertEqual(report["status"], "unsupported", report)
                        self.assertIsNone(report["worker_exit_code"])
                        continue
                    self.assertEqual(report["status"], "pass", report)
                    self.assertEqual(report["worker_exit_code"], 0)
                    self.assertEqual(report["observed_count"], 4)
                    requests = [json.loads(line) for line in
                                (Path(report["run_dir"]) / "requests.jsonl").read_text().splitlines()]
                    expected_statuses = [200, 429, 200] if scenario == "retryable-page" else [200] * len(requests)
                    self.assertEqual([r["status"] for r in requests], expected_statuses)
                    self.assertEqual([r["page"] for r in requests],
                                     [0, 1, 2] if scenario == "empty-middle-page" else
                                     [0, 1, 1] if scenario == "retryable-page" else [0, 1])
            report = run_case(builtin_fixture("all-pages"), PyAirbyteAdapter(single_page=True), root, timeout=90)
            self.assertEqual(report["status"], "fail", report)
            self.assertEqual(report["worker_exit_code"], 0)
            self.assertEqual(report["missing"], [("delta", "2"), ("gamma", "2")])
        finally:
            if root.name.startswith("cursorcheck-airbyte-test-") and root.parent == Path(tempfile.gettempdir()):
                def remove_readonly(function, path, error):
                    if not isinstance(error, PermissionError):
                        raise error
                    os.chmod(path, stat.S_IWRITE)
                    function(path)
                shutil.rmtree(root, onexc=remove_readonly)
