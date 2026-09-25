"""Assert the observed baseline and experimental-patch behavior."""

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from adapter import WidenAdapter
from cursorcheck.core import builtin_fixture, run_case


class WidenTrialTests(unittest.TestCase):
    def test_pinned_connector_behavior(self):
        expected_empty = os.environ.get("WIDEN_EXPECT_EMPTY", "fail")
        self.assertIn(expected_empty, ("pass", "fail"))
        root = Path(tempfile.gettempdir()) / ("cursorcheck-widen-test-" + uuid.uuid4().hex)
        root.mkdir()
        try:
            for scenario, status in (
                ("all-pages", "pass"), ("empty-middle-page", expected_empty),
                ("retryable-page", "pass"), ("restart-between-pages", "unsupported"),
                ("equal-cursor-boundary", "unsupported"),
            ):
                with self.subTest(scenario=scenario):
                    report = run_case(builtin_fixture(scenario), WidenAdapter(), root, timeout=30)
                    self.assertEqual(report["status"], status, report)
                    if status == "unsupported":
                        self.assertIsNone(report["worker_exit_code"])
                        continue
                    self.assertEqual(report["worker_exit_code"], 0)
                    self.assertEqual(report["observed_count"], 2 if status == "fail" else 4)
                    self.assertEqual(report["missing"], [("delta", "2"), ("gamma", "2")] if status == "fail" else [])
                    requests = [json.loads(line) for line in
                                (Path(report["run_dir"]) / "requests.jsonl").read_text().splitlines()]
                    if scenario == "retryable-page":
                        self.assertEqual([r["status"] for r in requests], [200, 429, 200])
                    elif scenario == "empty-middle-page":
                        self.assertEqual([r["page"] for r in requests], [0, 1] if status == "fail" else [0, 1, 2])
        finally:
            if root.name.startswith("cursorcheck-widen-test-") and root.parent == Path(tempfile.gettempdir()):
                shutil.rmtree(root)
