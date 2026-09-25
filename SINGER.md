# Historical Singer SDK empty-page reproduction

[Meltano SDK issue #2980](https://github.com/meltano/sdk/issues/2980) requested
support for APIs whose empty intermediate pages still have successors.
[PR #2989](https://github.com/meltano/sdk/pull/2989), released in
[0.46.0](https://github.com/meltano/sdk/releases/tag/v0.46.0), added the opt-in
`continue_if_empty(response)` paginator hook. The default still stops on an empty
page. Updating the SDK alone does not change a tap's termination policy.

The independently written `cursorcheck.singer_repro` uses the same
`empty-middle-page` fixture as the reference and dlt adapters. It configures the
SDK's JSONPath paginator and RESTStream; the SDK owns the request loop. A tiny
SQLite sink commits each emitted record. CursorCheck reads the database after
the worker exits, rather than deriving expected output from a second SDK run.

This adapts the reported failure class to our opaque-cursor source contract. It
does not reproduce an original provider's full API or claim a new upstream bug.

## Observed results

Native Windows, Python 3.12.10; four records split across two nonempty pages with
an empty page between them:

| SDK | Configuration | Worker exit | Durable records | Verdict |
| --- | --- | --- | --- | --- |
| 0.45.0 | Continuation hook supplied, ignored by old SDK | 0 | 2/4 | FAIL |
| 0.46.0 | Default paginator | 0 | 2/4 | FAIL |
| 0.46.0 | Continuation hook enabled | 0 | 4/4 | PASS |
| 0.54.5 | Default paginator | 0 | 2/4 | FAIL |
| 0.54.5 | Continuation hook enabled | 0 | 4/4 | PASS |

The same hook implementation is used across all versions. Failing runs omit
`delta/2` and `gamma/2`; the transcript ends at the empty page with `has_next: true`.
Ordinary pagination succeeds on all three versions. The regression suite also
checks that a genuinely terminal empty page completes and that recovery is
reported as unsupported. Portable artifacts are in `evidence/singer-*`.

## Run the comparison

In a virtual environment, from the repository root:

```text
python -m pip install ".[singer-repro]"
cursorcheck run --scenario empty-middle-page --adapter cursorcheck.singer_repro:build_default_adapter
cursorcheck run --scenario empty-middle-page --adapter cursorcheck.singer_repro:build_adapter
```

The first command intentionally exits 1; the second exits 0. To reproduce the
older behavior, use a separate environment with the base package and the desired
SDK version, without the current `singer-repro` extra:

```text
python -m pip install . "singer-sdk==0.45.0"
cursorcheck run --scenario empty-middle-page --adapter cursorcheck.singer_repro:build_adapter
```

That command intentionally exits 1. Replacing 0.45.0 with 0.46.0 makes it pass.
Run the version-aware regression tests in each environment:

```text
python -m unittest discover -s tests -p test_singer_reproduction.py -v
```

## What this does and does not establish

This is a second historical failure class exercised by the existing scenario
contract, alongside the dlt dependent-resource reproduction. It is a synthetic
SDK stream with a custom SQLite sink, **not an independent connector pilot,
production Singer target validation, or maintained general Singer adapter**.
Restart and incremental-state capabilities are explicitly unsupported.

The upstream PR already has direct regression tests for this behavior. For one
Singer tap, extending those tests may be simpler than adding CursorCheck.
CursorCheck's potential benefit is reusing a real HTTP fixture, independent
oracle and saved reports across frameworks. That benefit still needs an
independent developer trial; this reproduction is not adoption evidence.
