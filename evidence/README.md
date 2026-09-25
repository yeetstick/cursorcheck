# Portable evidence

These are publication copies of fixture, adapter/version, request and result
reports from selected successful validation runs and expected historical
failures. `current-dlt` contains the five-scenario passing suite. The four
`historical-*` directories contain the reported configuration pattern and its
workaround on two framework versions.

The `singer-*` directories compare the empty-page continuation hook across SDK
0.45.0, 0.46.0 and 0.54.5. These are synthetic SDK streams with a minimal SQLite
sink, not independent connector pilots. See [the reproduction notes](../SINGER.md).

Machine-specific `run_dir` values are normalized to relative case directories;
all test results and observations are preserved. Corresponding report files are
present beside each other here. Databases
and pipeline working directories are retained locally under `.cursorcheck/` but
omitted from the portable source archive. No production records are included.
