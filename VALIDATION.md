# Validation record

The original 0.0.2 validation used native Windows with Python 3.12.10, dlt 1.30.0,
DuckDB 1.5.5 and Hypothesis 6.168.1. That combined run passed **29 tests** in
91.703 seconds. The property checks
generate valid fixtures and malformed JSON; they do not replace real-process tests.

The [cross-platform run for the source startup fix](https://github.com/yeetstick/cursorcheck/actions/runs/36099992498)
passed 30 tests and the demo on Linux, Windows and macOS. The first CI run exposed
a path-alias assertion problem and a real macOS startup stall in HTTPServer's
reverse hostname lookup. The fixture now binds numeric loopback without DNS;
a regression test rejects any hostname lookup while starting and serving HTTP.

The 0.0.3 combined local suite passed **33 tests in 95.925 seconds**, including
dlt/DuckDB, Singer SDK 0.54.5, property checks and the DNS regression. The separate
historical Singer environments each passed their three version-aware tests.

The original 0.0.2 wheel was built offline and installed without optional
dependencies into an isolated virtual environment. From outside the source
checkout, with PYTHONPATH cleared, the installed `cursorcheck` command passed
`doctor` and all five reference scenarios. The portable report is in
`evidence/installed-wheel/`. Wheel SHA-256:
`28342500394d0bccdd6dc681116be44a8774ad44ab86e567a61f9fc61fa1ffe8`.

The 0.0.3 base wheel also passed `doctor` and all five reference scenarios after
installation outside the source checkout with PYTHONPATH cleared. Reports are in
`evidence/installed-wheel-003/`. Wheel SHA-256:
`82d7b9cf30eef2a33f67d61e8b7f625db3e8dd5b7c5d6943989f6af243b7bf9b`.

## Five-scenario framework suite

| Scenario | dlt/DuckDB outcome |
| --- | --- |
| all-pages | PASS, 4 durable records |
| empty-middle-page | PASS, 4 durable records |
| equal-cursor-boundary | PASS, 4 durable records after two invocations |
| retryable-page | PASS, 4 durable records after one 429 |
| restart-between-pages | PASS, 4 durable records after owned worker termination/restart |

The retained aggregate report is
`.cursorcheck/five-scenario-validation/suite-2143ae4e512547ae87cea202721581f5/suite.json`.
Portable report copies are in `evidence/current-dlt/`. Original SQLite/DuckDB
destinations remain in the local `.cursorcheck/` case directories.

The same runner and source contracts exercise the reference connector and dlt.
dlt owns its extraction, pagination, normalization, loading and state restoration.
The adapter supplies configuration and a read-only DuckDB snapshot. It contains
no replacement pagination/checkpoint algorithm.

## Defect and lifecycle checks

Each of the five reference defect modes produces the expected failure:
first-page-only, stop-at-empty-page, strict cursor comparison, 429-as-completion,
and checkpoint-ahead-of-durable-output. These are intentionally seeded defects.

Other tests verify explicit worker errors, deadlines, request caps, wrong record
versions, extra records, duplicate destination IDs, empty sources, unsupported
coverage, legacy replay, config validation, non-overwriting init, no-sync doctor,
suite exit codes and aggregate JUnit reports. A subprocess that outlives its
parent is terminated by worker-tree cleanup on Windows.

## Historical behavior

The dependent-resource pattern from [dlt #2586](https://github.com/dlt-hub/dlt/issues/2586)
was reproduced using synthetic data in both dlt 1.10.0/DuckDB 1.2.2 and
dlt 1.30.0/DuckDB 1.5.5. Both workers returned success with two of four records.
The explicit endpoint-paginator workaround loaded all four in both versions.
See [HISTORICAL.md](HISTORICAL.md) for the exact adaptation, commands and artifacts.
This is a historical failure class, not a newly discovered bug or a claim that
the newer release fixed it.

The [Singer SDK reproduction](SINGER.md) adds a second historical failure class:
successful truncation at an empty intermediate page. SDK 0.45.0 ignores the
continuation hook and loads 2/4 records; SDK 0.46.0 and 0.54.5 load 4/4 with the
hook enabled. The default paginator still loads only 2/4. These observations use
an independently written synthetic RESTStream and a minimal SQLite sink, not a
production Singer target. Each version passed its three regression tests.

## Limits of this evidence

The [PyAirbyte framework trial](examples/pyairbyte/README.md) uses PyAirbyte
0.71.0, Airbyte CDK 7.30.0 and DuckDB 1.4.3 in a separate environment. On native
Windows, ordinary pagination, empty-page continuation and retry each produced
four durable rows through PyAirbyte's DuckDBCache. No core or source contract
changes were required. Its purpose-built manifest is not an existing provider
connector, and restart/incremental recovery remain unsupported. Portable
evidence is in `evidence/pyairbyte/`. A deliberately disabled paginator returned
success with only two rows; CursorCheck reported the two missing IDs. Its report
is in `evidence/pyairbyte-negative/`. The dedicated integration test passed in
134.493 seconds, checking five scenario outcomes and the seeded negative control.

An [author-run trial of Widen's REST tap](examples/widen_rest_api/README.md) now
uses the same source contract with an unmodified external connector and a
disposable Singer-to-SQLite sink. Its 7 existing pytest tests passed; CursorCheck
detected known empty-page loss. A local connector patch passes the saved fixture
and 8 upstream tests (including a new direct regression). Ordinary pagination
and retry pass on both variants; recovery is unsupported. This is one external
code integration, not independent onboarding or maintainer adoption.

- All data is synthetic; the framework examples and external tap trial do not
  constitute independent users or adopters.
- Three independent project integrations and onboarding measurements are pending.
- Two historical failure classes have been reproduced; the dlt comparison uses
  a configuration workaround, and the Singer comparison uses an opt-in hook.
- Python 3.12 is checked on Linux, Windows and macOS in
  [GitHub Actions](https://github.com/yeetstick/cursorcheck/actions). Other Python
  versions remain unverified. No package has been published to PyPI.
- Restart checks one observable request boundary, not arbitrary transaction cuts.
- Configurable provider field mappings, next-link pagination and the full v0.1
  feature/acceptance list remain outside this pilot build.

The next gate is an independent connector trial using [PILOT.md](PILOT.md), with
a fair comparison against that project's existing test facilities. No external
maintainer messages have been sent.
