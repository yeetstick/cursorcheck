import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import ProxyHandler, build_opener
import uuid

from cursorcheck.core import builtin_fixture


class SourceStartupTests(unittest.TestCase):
    def test_loopback_source_starts_and_serves_without_hostname_lookup(self):
        root = Path(tempfile.gettempdir()) / ("cursorcheck-source-test-" + uuid.uuid4().hex)
        root.mkdir()
        (root / "replay.json").write_text(json.dumps(builtin_fixture("all-pages").as_dict()))
        script = """
import sys
from pathlib import Path
from unittest.mock import patch
from cursorcheck.source import serve
with patch('socket.getfqdn', side_effect=AssertionError('loopback must not resolve a hostname')):
    serve(Path(sys.argv[1]), 'test-source', 10)
"""
        process = None
        try:
            process = subprocess.Popen([sys.executable, "-c", script, str(root)],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            deadline = time.monotonic() + 5
            ready = root / "ready.json"
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            if not ready.exists():
                process.kill()
                _, stderr = process.communicate(timeout=5)
                self.fail("source did not become ready: " + stderr.decode(errors="replace"))
            port = json.loads(ready.read_text())["port"]
            opener = build_opener(ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{port}/test-source", timeout=2) as response:
                data = json.load(response)
            self.assertEqual([row["id"] for row in data["items"]], ["alpha", "beta"])
            self.assertIsNotNone(data["next"])
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)
            import shutil
            if root.name.startswith("cursorcheck-source-test-") and root.parent == Path(tempfile.gettempdir()):
                shutil.rmtree(root)
