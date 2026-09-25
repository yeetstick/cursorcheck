from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET

from cursorcheck.cli import main
from cursorcheck.config import Settings, template


class ConfigCliTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.gettempdir()) / ("cursorcheck-config-test-" + uuid.uuid4().hex)
        self.root.mkdir()

    def tearDown(self):
        import shutil
        if self.root.parent == Path(tempfile.gettempdir()) and self.root.name.startswith("cursorcheck-config-test-"):
            shutil.rmtree(self.root)

    def call(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(list(args))
        return code, output.getvalue()

    def test_init_never_overwrites_and_paths_are_config_relative(self):
        config = self.root / "cursorcheck.toml"
        self.assertEqual(self.call("init", "--config", str(config))[0], 0)
        original = config.read_text()
        self.assertEqual(self.call("init", "--config", str(config), "--dlt")[0], 2)
        self.assertEqual(config.read_text(), original)
        # Windows TEMP may use an 8.3 alias; macOS /var may resolve via /private.
        self.assertEqual(Settings.load(config).output, (self.root / ".cursorcheck/runs").resolve())

    def test_doctor_has_no_execution_artifacts(self):
        config = self.root / "cursorcheck.toml"
        config.write_text(template())
        code, text = self.call("doctor", "--config", str(config))
        self.assertEqual(code, 0)
        self.assertEqual(text.count(": SUPPORTED"), 5)
        self.assertFalse((self.root / ".cursorcheck").exists())

    def test_bad_limits_and_unknown_config_keys_are_rejected(self):
        for content in (template() + 'typo = 2\n', template().replace('max_requests = 100', 'max_requests = true'),
                        template().replace('case_timeout_seconds = 30', 'case_timeout_seconds = nan')):
            config = self.root / "bad.toml"
            config.write_text(content)
            self.assertEqual(self.call("doctor", "--config", str(config))[0], 2)

    def test_suite_writes_aggregate_reports_and_propagates_failure(self):
        code, _ = self.call("run", "--scenario", "all-pages", "--scenario", "retryable-page",
                            "--adapter", "cursorcheck.reference:build_retry_defect", "--output", str(self.root))
        self.assertEqual(code, 1)
        suite = next(self.root.glob("suite-*"))
        data = json.loads((suite / "suite.json").read_text())
        self.assertEqual([case["status"] for case in data["cases"]], ["pass", "fail"])
        self.assertEqual(len(ET.parse(suite / "suite.xml").findall("testsuite")), 2)

    def test_duplicate_scenarios_are_rejected(self):
        code, _ = self.call("run", "--scenario", "all-pages", "--scenario", "all-pages", "--output", str(self.root))
        self.assertEqual(code, 2)
        self.assertEqual(list(self.root.iterdir()), [])
