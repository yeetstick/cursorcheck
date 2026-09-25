# CursorCheck

Find records a REST connector silently drops across pagination, retries and
restarts. CursorCheck runs a real worker against a controlled local API, then
compares its durable output with an independent source oracle.

**Experimental version 0.0.3.** Passing covers the declared fixtures, not every
production API behavior. Package-name availability has not been checked and no
package has been published to PyPI. See [validation evidence](VALIDATION.md).

## Quick start

Python 3.12 or newer. Install this checkout in your own virtual environment:

```text
git clone https://github.com/yeetstick/cursorcheck.git
cd cursorcheck
python -m pip install .
cursorcheck demo
cursorcheck init
cursorcheck doctor --config cursorcheck.toml
cursorcheck run --config cursorcheck.toml
```

The base package has no third-party runtime dependencies. `demo` labels its
empty-page defect as intentional; exit 0 means the good example passed and the
defective example failed. `run` executes all five scenarios unless selected with
one or more `--scenario NAME` arguments. `init` never overwrites an existing file.

Without installing, PowerShell users can run
`$env:PYTHONPATH = (Resolve-Path src).Path` followed by `python -m cursorcheck demo`.
On POSIX use `export PYTHONPATH="$PWD/src"` instead.

## Scenarios

| Scenario | Controlled source behavior | What is checked |
| --- | --- | --- |
| all-pages | Known collection across multiple pages | All ID/version pairs arrive |
| empty-middle-page | Empty items array with a valid next token | Later pages still arrive |
| retryable-page | One selected page returns 429 and Retry-After, then succeeds | Recovery completeness; explicit errors stay errors |
| restart-between-pages | Next page request is held, worker tree killed, worker restarted | Saved state does not skip uncommitted output |
| equal-cursor-boundary | Second sync exposes new IDs at the previous inclusive cursor | Equal-version additions arrive |

Restart timing is tied to an observed request, not a sleep. The server survives
the interruption and the worker reuses its destination and checkpoint. This
does not locate an arbitrary point inside a framework's transaction.

## dlt with a real DuckDB destination

```text
python -m pip install ".[dlt]"
cursorcheck init --dlt --config dlt-check.toml
cursorcheck doctor --config dlt-check.toml
cursorcheck run --config dlt-check.toml
```

All five cases are tested with dlt 1.30.0 and DuckDB 1.5.5. The adapter configures
dlt's REST API source; dlt owns pagination, normalization and loading. CursorCheck
reads the resulting DuckDB table in read-only mode. The adapter does not
reimplement pagination or checkpointing. dlt telemetry is disabled and its state
and configuration providers stay inside the run directory.

Try a deliberately wrong single-page configuration:

```text
cursorcheck run --scenario all-pages --adapter cursorcheck.dlt_adapter:build_single_page_adapter
```

This should exit 1 with `delta/2` and `gamma/2` missing. It is a configuration
defect, not a newly discovered dlt bug. Historical reproduction commands and
version details are in [HISTORICAL.md](HISTORICAL.md).

A second [historical reproduction](SINGER.md) exercises Singer SDK's empty-page
continuation hook across versions 0.45.0, 0.46.0 and 0.54.5. It uses the same
fixture and a minimal SQLite sink; it is not a production Singer target adapter.

## Adapt your existing connector

Set `adapter = "my_adapter:build_adapter"` in the config. The config directory is
added to the worker import path. The factory returns an object with two methods:

```python
def command(self, run_dir: Path, source_url: str) -> list[str]:
    # Wire source_url and an owned disposable destination into your real worker.
    # Return argv, e.g. [sys.executable, "-m", "your_worker", ...].
    ...

def snapshot(self, run_dir: Path) -> list[tuple[str, str]]:
    # Read durable output after the worker exits: one string (id, version) per ID.
    ...
```

Only declare `restart_supported = True` when the worker can restart against the
same directory and actually restore persisted state. Declare
`incremental_supported = True` when a second invocation restores its cursor.
Cases needing an undeclared capability return `unsupported`, never `pass`.
`doctor` checks these declarations and optional dependencies; it does not run a
worker or prove the declarations correct. Importing an adapter executes trusted
project code.

Source contract: JSON `{"items": [{"id": "...", "version": "..."}], "next": TOKEN}`.
Send the opaque token in a `cursor` query parameter. `next: null` terminates the
collection; an empty items array alone does not. Optional `since` uses inclusive
lexicographic comparison of version strings. The equal-cursor fixture uses one
common ISO timestamp. No claim is made about arbitrary timestamp formats.

Do not move the connector's algorithm into the adapter. If this contract cannot
represent the connector's actual source, report the mismatch rather than
rewriting the connector to make the test pass. See [PILOT.md](PILOT.md).

The [Widen REST tap trial](examples/widen_rest_api/README.md) runs an existing
external connector through this interface, compares a direct pytest alternative,
and retains before/after evidence. It is an author-run compatibility trial, not
an independent adopter.

## Reports and replay

Each case saves `replay.json`, a bounded `requests.jsonl` transcript, `result.json`
and `junit.xml`. Bundled adapters save `adapter.json` with mode/version information
and retain their SQLite or DuckDB destination. Suites add `suite.json` and
`suite.xml`. Fixtures contain synthetic data; worker stdout/stderr are discarded.
No arbitrary worker command or environment dump is saved.

```text
cursorcheck replay PATH_TO_CASE/replay.json --adapter my_adapter:build_adapter
```

Replay executes the selected current adapter in a fresh directory. It does not
reuse prior observations. Schema-1 pagination fixtures remain readable;
new fixtures use schema 2 to record retry, interruption or visibility schedules.

Exit codes: **0** all required cases pass; **1** invariant failure;
**2** configuration/execution error; **3** required coverage unsupported.
Errors take precedence over failures, which take precedence over unsupported
coverage in a suite. JUnit encodes unsupported cases as skipped; retain the CLI
exit code in CI so missing coverage cannot produce a successful job.

## Resource limits and support

Fixtures: at most 1000 records, 100 pages and 1 MB serialized input. The default
CLI case deadline is 30 seconds and the request budget is 100. Configurable limits
are bounded to 300 seconds and 1000 requests. The source binds only to loopback
with a per-run random path. Adapters are trusted code, not a security sandbox;
their synchronous methods must return promptly and their writes are not subject
to filesystem quotas. Use only disposable test destinations.

Windows worker trees run inside a Job Object; POSIX workers run in an owned
session. Normal completion, errors and restart paths terminate descendants.
Windows behavior has been exercised locally. The POSIX implementation and the
prepared GitHub Actions matrix still require Linux/macOS execution. Code that
deliberately escapes the session is outside the POSIX ownership contract.

The runner retains case artifacts and never deletes a user destination. It does
not yet offer next-link pagination, configurable field mappings, append/multiset
semantics, provider emulation, multiple streams, source deletions, automatic
fixture shrinking, or a stable public interface. This is a pilot build, not the
full v0.1 acceptance milestone.

## Development

```text
python -m pip install ".[dlt,test]"
python -m unittest discover -s tests -v
```

Tests cover actual HTTP/process/destination behavior, seeded failures, legacy
fixture replay, configuration, CLI outcome propagation, child cleanup and
Hypothesis-generated serialization/invalid-input cases. Without optional extras,
the dlt and property tests are visibly skipped. CI installs both extras.

Licensed under [Apache-2.0](LICENSE).
