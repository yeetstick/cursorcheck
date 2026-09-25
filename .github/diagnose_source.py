"""Temporary CI startup probe; remove after diagnosing macOS readiness."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from cursorcheck.core import builtin_fixture

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder).resolve()
    (root / "replay.json").write_text(json.dumps(builtin_fixture("all-pages").as_dict()))
    script = (
        "import faulthandler; faulthandler.dump_traceback_later(3); "
        "print('[DEBUG-source-startup] interpreter ready', flush=True); "
        "from cursorcheck.source import serve; from pathlib import Path; import sys; "
        "print('[DEBUG-source-startup] module imported', flush=True); "
        "serve(Path(sys.argv[1]), 'diagnostic', 10)"
    )
    child = subprocess.Popen([sys.executable, "-c", script, str(root)])
    try:
        deadline = time.monotonic() + 5
        while not (root / "ready.json").exists() and time.monotonic() < deadline and child.poll() is None:
            time.sleep(0.01)
        print('[DEBUG-source-startup] files:', [p.name for p in root.iterdir()], flush=True)
        assert (root / "ready.json").exists(), 'source did not become ready within five seconds'
    finally:
        child.terminate()
        child.wait(timeout=5)
