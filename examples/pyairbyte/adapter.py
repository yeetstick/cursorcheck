"""Synthetic declarative source using PyAirbyte's real DuckDB cache."""

from importlib.metadata import version
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit


class PyAirbyteAdapter:
    required_modules = ("airbyte", "duckdb")
    restart_supported = False
    incremental_supported = False

    def __init__(self, single_page: bool = False):
        self.single_page = single_page

    def command(self, run_dir: Path, source_url: str) -> list[str]:
        (run_dir / "adapter.json").write_text(json.dumps({
            "airbyte": version("airbyte"), "airbyte-cdk": version("airbyte-cdk"),
            "duckdb": version("duckdb"), "destination": "PyAirbyte DuckDBCache",
            "synthetic_manifest": True, "production_connector": False,
            "seeded_single_page": self.single_page,
            "manifest_sha256_lf": hashlib.sha256(Path(__file__).with_name("manifest.json")
                                                  .read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        }, indent=2), encoding="utf-8")
        return [sys.executable, str(Path(__file__).resolve()), source_url, str(int(self.single_page))]

    def snapshot(self, run_dir: Path) -> list[tuple[str, str]]:
        import duckdb

        with duckdb.connect(str(run_dir / "destination.duckdb"), read_only=True) as db:
            exists = db.execute("SELECT count(*) FROM information_schema.tables "
                                "WHERE table_schema = 'case_data' AND table_name = 'records'").fetchone()[0]
            if not exists:
                return []
            return db.execute('SELECT id, version FROM case_data.records ORDER BY id').fetchall()


def build_adapter() -> PyAirbyteAdapter:
    return PyAirbyteAdapter()


def build_single_page_adapter() -> PyAirbyteAdapter:
    return PyAirbyteAdapter(single_page=True)


def load(source_url: str, single_page: bool) -> None:
    directory = Path.cwd()
    # These settings must precede imports, which initialize PyAirbyte configuration.
    os.environ.update({
        "DO_NOT_TRACK": "1", "AIRBYTE_OFFLINE_MODE": "1", "AIRBYTE_LOCAL_REGISTRY": "0",
        "AIRBYTE_PROJECT_DIR": str(directory), "AIRBYTE_INSTALL_DIR": str(directory / "install"),
        "AIRBYTE_CACHE_ROOT": str(directory / "cache"),
        "AIRBYTE_LOGGING_ROOT": str(directory / "logs"),
        "AIRBYTE_TEMP_DIR": str(directory / "temp"),
        "NO_PROXY": "*", "OTEL_SDK_DISABLED": "true",
    })
    (directory / "temp").mkdir(exist_ok=True)
    # The CDK also uses stdlib temporary directories, independently of PyAirbyte.
    tempfile.tempdir = str(directory / "temp")

    # Fail the trial if Python attempts any non-loopback connection. This is a
    # diagnostic assertion for this example, not a sandbox for untrusted code.
    def check_connection(event, args):
        if event == "socket.connect" and args[1][0] != "127.0.0.1":
            raise RuntimeError("PyAirbyte trial attempted a non-loopback connection")

    sys.addaudithook(check_connection)
    import airbyte as ab

    manifest = json.loads(Path(__file__).with_name("manifest.json").read_text(encoding="utf-8"))
    if single_page:
        # Deliberate configuration defect to validate the destination oracle.
        manifest["streams"][0]["retriever"]["paginator"] = {"type": "NoPagination"}
    endpoint = urlsplit(source_url)
    source = ab.get_source("source-cursorcheck",
                           config={"url": f"{endpoint.scheme}://{endpoint.netloc}/", "path": endpoint.path.lstrip("/")},
                           source_manifest=manifest, streams=["records"], install_if_missing=False)
    cache = ab.DuckDBCache(db_path=str(directory / "destination.duckdb"), schema_name="case_data")
    source.read(cache=cache, write_strategy="replace", force_full_refresh=True)


if __name__ == "__main__":
    load(sys.argv[1], bool(int(sys.argv[2])))
