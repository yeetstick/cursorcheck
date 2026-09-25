# Validation record — 0.0.2

Verified locally on native Windows with Python 3.12.10, dlt 1.30.0, DuckDB 1.5.5
and Hypothesis 6.168.1. The final combined unittest run passed **29 tests** in
91.703 seconds, including both optional dependency groups. The property checks
generate valid fixtures and malformed JSON; they do not replace real-process tests.

The 0.0.2 wheel was built offline from this source and installed without optional
dependencies into an isolated virtual environment. From outside the source
checkout, with PYTHONPATH cleared, the installed `cursorcheck` command passed
`doctor` and all five reference scenarios. The portable report is in
`evidence/installed-wheel/`. Wheel SHA-256:
`28342500394d0bccdd6dc681116be44a8774ad44ab86e567a61f9fc61fa1ffe8`.

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
This is one historical failure class, not a newly discovered bug or a claim that
the newer release fixed it.

## Limits of this evidence

- These are bundled synthetic integrations, not independent users or adopters.
- Three independent project integrations and onboarding measurements are pending.
- Only one historical failure class has been reproduced so far.
- Linux/macOS execution was unverified in this local validation. See the
  [GitHub Actions runs](https://github.com/yeetstick/cursorcheck/actions) for
  subsequent matrix results. No package has been published to PyPI.
- Restart checks one observable request boundary, not arbitrary transaction cuts.
- Configurable provider field mappings, next-link pagination and the full v0.1
  feature/acceptance list remain outside this pilot build.

The next gate is an independent connector trial using [PILOT.md](PILOT.md), with
a fair comparison against that project's existing test facilities. No external
maintainer messages have been sent.
