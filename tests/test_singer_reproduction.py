"""Run unchanged against SDK 0.45.0, 0.46.0 and 0.54.5."""

import importlib.util
from importlib.metadata import version
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from cursorcheck.core import Fixture, builtin_fixture, run_case
from cursorcheck.singer_repro import SingerReproduction


@unittest.skipUnless(importlib.util.find_spec("singer_sdk"), "optional Singer SDK not installed")
class SingerReproductionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.gettempdir()) / ("cursorcheck-singer-test-" + uuid.uuid4().hex)
        self.root.mkdir()

    def tearDown(self):
        import shutil
        if self.root.name.startswith("cursorcheck-singer-test-") and self.root.parent == Path(tempfile.gettempdir()):
            shutil.rmtree(self.root)

    def test_empty_page_hook_distinguishes_pre_fix_and_fixed_sdk(self):
        sdk_version = version("singer-sdk")
        if sdk_version not in {"0.45.0", "0.46.0", "0.54.5"}:
            self.skipTest("historical expectations are pinned to validated releases")
        for enabled in (False, True):
            with self.subTest(continue_empty=enabled, sdk=sdk_version):
                report = run_case(builtin_fixture("empty-middle-page"),
                                  SingerReproduction(enabled), self.root, timeout=30)
                fixed = enabled and sdk_version != "0.45.0"
                self.assertEqual(report["status"], "pass" if fixed else "fail", report)
                self.assertEqual(report["worker_exit_code"], 0)
                self.assertEqual(report["observed_count"], 4 if fixed else 2)
                self.assertEqual(report["missing"], [] if fixed else [("delta", "2"), ("gamma", "2")])
                requests = [json.loads(line) for line in
                            (Path(report["run_dir"]) / "requests.jsonl").read_text().splitlines()]
                self.assertEqual([request["page"] for request in requests], [0, 1, 2] if fixed else [0, 1])

    def test_ordinary_pages_and_terminal_empty_page_complete(self):
        for fixture in (builtin_fixture("all-pages"), Fixture("empty", (), ((),))):
            with self.subTest(scenario=fixture.name):
                report = run_case(fixture, SingerReproduction(), self.root, timeout=30)
                self.assertEqual(report["status"], "pass", report)

    def test_recovery_is_explicitly_unsupported(self):
        for scenario in ("restart-between-pages", "equal-cursor-boundary"):
            with self.subTest(scenario=scenario):
                report = run_case(builtin_fixture(scenario), SingerReproduction(), self.root)
                self.assertEqual(report["status"], "unsupported")
                self.assertIsNone(report["worker_exit_code"])
