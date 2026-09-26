# PyAirbyte framework trial

This example exercises a **synthetic declarative source** with PyAirbyte's real
DuckDB cache. Airbyte CDK owns HTTP requests, cursor pagination and retries;
PyAirbyte owns extraction and materialization. CursorCheck reads the final table
through a separate read-only DuckDB connection after the worker exits.

It is a framework integration, not an existing provider connector or an
independent adopter. No Airbyte Cloud account, credentials, Docker daemon or
remote API is used. The core CursorCheck package has no Airbyte dependency.

## Observed results

The native Windows trial used Python 3.12.10, PyAirbyte 0.71.0, Airbyte CDK
7.30.0 and DuckDB 1.4.3. The three supported scenarios each materialized four
records and exited successfully:

| Scenario | Source response trace | Durable records |
| --- | --- | --- |
| All pages | Two successful pages | 4/4 |
| Empty middle page | Three successful pages, including an empty middle page | 4/4 |
| Retryable page | 200, 429, 200 | 4/4 |

Restart and incremental recovery are explicitly unsupported. The portable
reports, fixtures, transcripts and dependency metadata are in
[`evidence/pyairbyte`](../../evidence/pyairbyte/). These observations establish
compatibility with this manifest and cache; they do not establish adoption or
discover a new framework bug.

The deliberately disabled paginator exited successfully with only two durable
rows. CursorCheck reported `FAIL` and identified `delta/2` and `gamma/2` as missing;
see [`evidence/pyairbyte-negative`](../../evidence/pyairbyte-negative/). The local
integration test passed in 134.493 seconds, asserting all five scenario outcomes,
request ordering, and this negative control.

## Run in a separate environment

PyAirbyte 0.71.0 pins DuckDB 1.4.3; CursorCheck's dlt extra pins 1.5.5. Install this
example separately instead of combining the two environments. From the repo root:

```text
python -m venv .venv-airbyte
# Activate that environment using your shell's normal command.
python -m pip install . -r examples/pyairbyte/requirements.txt
cursorcheck run --config examples/pyairbyte/cursorcheck.toml
python -m unittest discover -s examples/pyairbyte -p test_trial.py -v
```

The five-scenario CLI suite deliberately exits **3** when all supported cases
pass: restart and equal-cursor incremental recovery are unsupported. The
manifest uses full-refresh replacement, so neither recovery guarantee has been
established. The unittest also runs a deliberate `NoPagination` configuration
and requires CursorCheck to report missing records with a successful worker exit.
That negative control is a seeded configuration defect, not an Airbyte bug.

The adapter sets offline mode, disables registry access and telemetry before
importing PyAirbyte, and keeps its cache, logs and temporary files in the case
directory. A Python socket audit assertion rejects non-loopback connections in
this example. This assertion is a diagnostic, not a security sandbox. Installing
the optional dependencies still requires network access.

## Source-contract limitations

The inspected [PokeAPI connector manifest](https://github.com/airbytehq/airbyte/blob/master/airbyte-integrations/connectors/source-pokeapi/manifest.yaml)
has a fixed provider URL and extracts one object with a different schema. It
cannot use CursorCheck's source contract unchanged. Replacing its requester,
record selector and schema would create a new connector configuration, so this
example instead labels its purpose-built manifest explicitly.

This trial does not justify adding provider emulation or claiming that arbitrary
Airbyte connectors are supported. A specific existing connector and its source
contract are still needed for that evaluation. PyAirbyte's own
[integration tests](https://github.com/airbytehq/PyAirbyte/blob/v0.71.0/tests/integration_tests/test_all_cache_types.py)
already assert materialized cache records; this example does not establish that
maintainers prefer CursorCheck to those tests.

On the local Windows host, Python's restricted execution environment prevented
the CDK from creating usable private temporary directories; the trial required
execution outside that sandbox. PyAirbyte also leaves read-only temporary files
and emits cleanup warnings on Windows even after a successful sync. Artifacts
remain inside each disposable case. The example's tests handle read-only files
when removing their own temporary test directories.
