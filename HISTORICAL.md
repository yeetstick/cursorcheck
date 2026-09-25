# Historical dlt reproduction

Source: [dlt issue #2586](https://github.com/dlt-hub/dlt/issues/2586), reported for
dlt 1.10.0. It describes a dependent resource whose resolved parameter at the end
of the URL causes a client-level paginator to be superseded by single-entity
endpoint inference. The reported workaround supplies the paginator explicitly
on the resource endpoint.

This independently written reproducer uses four synthetic records and an opaque
cursor response instead of the original MBTA data and JSON links. It preserves
the dependent-resource URL shape and paginator placement. It does not contact
MBTA, require credentials or copy the original dataset.

| Environment | Client-level paginator | Explicit endpoint paginator |
| --- | --- | --- |
| Python 3.12.10, dlt 1.10.0, DuckDB 1.2.2 | worker exit 0, 2/4 records; FAIL | 4/4 records; PASS |
| Python 3.12.10, dlt 1.30.0, DuckDB 1.5.5 | worker exit 0, 2/4 records; FAIL | 4/4 records; PASS |

In both failing runs, `delta/2` and `gamma/2` are absent from the real DuckDB
destination. These are reproduced historical behaviors, not newly discovered
bugs, and the passing comparison is a configuration workaround rather than a
claim that a newer framework release fixed the issue.

```text
cursorcheck run --scenario all-pages --adapter cursorcheck.dlt_adapter:build_inherited_child_adapter
cursorcheck run --scenario all-pages --adapter cursorcheck.dlt_adapter:build_explicit_child_adapter
```

The first command should exit 1 and the second 0. The special adapters declare
incremental/restart scenarios unsupported; they exist to isolate this source
configuration shape.

For the historical environment, install `dlt[duckdb]==1.10.0`, `duckdb==1.2.2` and
`setuptools==80.9.0` in a separate environment. The setuptools pin supplies
`pkg_resources`, required by this old dlt release. Do not install CursorCheck's
current `dlt` extra into that environment; install the base package only.

Retained evidence directories under `.cursorcheck/`:

- `historical-110/suite-03fbaa6511774ca693d4b40fce32a465/`: historical failing case.
- `historical-110/suite-357aa3f8caa348e58f1e6312840208b6/`: historical workaround.
- `historical-current/suite-65e5959f6dc84dbe90457ed0f9fb7bd9/`: current failing case.
- `historical-current/suite-a586655305534fab89b93960d0dcc631/`: current workaround.

Each contains reports, request transcript, replay fixture, adapter/dependency
metadata and the durable destination. Earlier failed setup attempts are retained
separately as errors and are not evidence of silent loss.
