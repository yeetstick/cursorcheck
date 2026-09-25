"""Optional integration: dlt owns extraction, pagination and DuckDB loading."""

from pathlib import Path
import sys


class DltAdapter:
    required_modules = ("dlt", "duckdb")
    restart_supported = True
    incremental_supported = True
    def __init__(self, single_page: bool = False, *, mode: str | None = None):
        self.mode = mode or ("single_page" if single_page else "cursor")
        if self.mode.startswith("child-"):
            self.restart_supported = self.incremental_supported = False

    def command(self, run_dir: Path, source_url: str) -> list[str]:
        return [sys.executable, "-m", "cursorcheck.dlt_adapter", source_url,
                self.mode]

    def snapshot(self, run_dir: Path) -> list[tuple[str, str]]:
        import duckdb

        with duckdb.connect(str(run_dir / "destination.duckdb"), read_only=True) as db:
            exists = db.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'case_data' AND table_name = 'records'"
            ).fetchone()[0]
            if not exists:
                return []  # dlt may create no table for a genuinely empty extraction.
            return db.execute('SELECT id, version FROM case_data.records ORDER BY id').fetchall()


def build_adapter() -> DltAdapter:
    return DltAdapter()


def build_single_page_adapter() -> DltAdapter:
    """Deliberate misconfiguration, not a claimed bug in dlt."""
    return DltAdapter(single_page=True)


def build_inherited_child_adapter() -> DltAdapter:
    """Historical #2586 shape: a resolved value at the end of the URL."""
    return DltAdapter(mode="child-client")


def build_explicit_child_adapter() -> DltAdapter:
    """The documented workaround: put the paginator on the child endpoint."""
    return DltAdapter(mode="child-endpoint")


def load(source_url: str, mode: str) -> None:
    import json
    from importlib.metadata import version
    import os
    from urllib.parse import urlsplit

    directory = Path.cwd()
    (directory / "adapter.json").write_text(json.dumps({
        "dlt": version("dlt"), "duckdb": version("duckdb"),
        "pagination": mode, "destination": "DuckDB", "synthetic_configuration": True,
    }, indent=2), encoding="utf-8")
    # Set before importing dlt; keep state/config local and disable telemetry.
    os.environ["DLT_DATA_DIR"] = str(directory / "dlt-data")
    os.environ["DLT_PROJECT_DIR"] = str(directory)
    os.environ["RUNTIME__DLTHUB_TELEMETRY"] = "false"
    os.environ["RUNTIME__LOG_LEVEL"] = "ERROR"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"

    import dlt
    from dlt.common.configuration.container import Container
    from dlt.common.configuration.specs.pluggable_run_context import PluggableRunContext
    from dlt.common.runtime.run_context import RunContext
    from dlt.sources.rest_api import rest_api_resources
    from requests import Session
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    class OwnedRunContext(RunContext):
        @property
        def global_dir(self):
            return str(directory / "dlt-data")

        @property
        def data_dir(self):
            return str(directory / "dlt-data")

    # DLT_DATA_DIR alone still lets dlt probe/read the user's global config.
    # Keep its configuration providers in the owned directory as well.
    Container()[PluggableRunContext] = PluggableRunContext(OwnedRunContext(str(directory)))
    session = Session()
    session.trust_env = False
    session.mount("http://", HTTPAdapter(max_retries=Retry(
        total=2, status_forcelist=[429], allowed_methods=["GET"], respect_retry_after_header=True)))
    endpoint = urlsplit(source_url)
    paginator = "single_page" if mode == "single_page" else {
        "type": "cursor", "cursor_path": "next", "cursor_param": "cursor"}
    config = {
        "client": {"base_url": f"{endpoint.scheme}://{endpoint.netloc}/",
                   "session": session, "paginator": paginator},
        "resources": [{"name": "records", "primary_key": "id", "write_disposition": "merge",
                       "columns": {"id": {"data_type": "text"}, "version": {"data_type": "text"}},
                       "endpoint": {"path": endpoint.path.lstrip("/"), "data_selector": "items",
                                    "params": {"since": {"type": "incremental", "cursor_path": "version"}}}}],
    }
    if mode.startswith("child-"):
        config["resources"][0]["endpoint"] = {
            "path": endpoint.path.lstrip("/") + "?since={boundary}",
            "data_selector": "items",
            "params": {"boundary": {"type": "resolve", "resource": "bounds", "field": "boundary"}},
        }
        def bounds():
            yield [{"boundary": "0"}]
        config["resources"].append(dlt.resource(bounds, name="bounds")())
        if mode == "child-endpoint":
            config["resources"][0]["endpoint"]["paginator"] = paginator
    resources = rest_api_resources(config)
    pipeline = dlt.pipeline(
        pipeline_name="cursorcheck_case", pipelines_dir=str(directory / "pipelines"),
        destination=dlt.destinations.duckdb(str(directory / "destination.duckdb")),
        dataset_name="case_data")
    info = pipeline.run(resources)
    info.raise_on_failed_jobs()
    session.close()


if __name__ == "__main__":
    load(sys.argv[1], sys.argv[2])
