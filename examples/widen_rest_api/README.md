# Widen REST tap: external compatibility trial

This trial runs an existing connector from
[Widen/tap-rest-api-msdk](https://github.com/Widen/tap-rest-api-msdk/tree/071b54032beecba75f6100b90281c1d88a47dfde)
at revision `071b54032beecba75f6100b90281c1d88a47dfde` (package 1.4.2).
CursorCheck's author performed the trial; the upstream maintainers did not
participate. This is **one external-code integration, not independent onboarding,
endorsement or adoption**. The repository was not archived; its last push at
inspection was April 22, 2025. It is a compatibility candidate, not evidence of
current maintainer interest.

## What actually runs

`adapter.py` supplies the tap's existing configuration settings, invokes its
unmodified `TapRestApiMsdk.sync_all()` in a subprocess, and loads emitted Singer
RECORD messages into a disposable SQLite table. The tap and its SDK own request
construction, pagination, retries and record processing. The adapter contains no
replacement pagination loop. No CursorCheck source/profile change was needed.

The SQLite bridge is a **test sink**, not an independently maintained Singer
target. It does not acknowledge or restore STATE messages. Restart and
incremental scenarios are therefore unsupported. This tests the real tap's
extraction completeness as observed in the test sink; it does not validate a
production target or recovery chain. The source and records are synthetic.

## Observations, September 25, 2026

Local environment: Windows, Python 3.12.10, CursorCheck 0.0.3. The original tap
uses Singer SDK 0.40.0. Seven collected upstream pytest tests passed in 0.39s.
This was the pytest suite, not the full upstream tox/lint/type-check matrix.

| Scenario | Unmodified tap / SDK 0.40.0 | Local patch / SDK 0.46.0 |
| --- | --- | --- |
| all-pages | PASS, 4/4 | PASS, 4/4 |
| empty-middle-page | FAIL, 2/4; worker exit 0 | PASS, 4/4 |
| retryable-page | PASS, 4/4 after 429 | PASS, 4/4 after 429 |
| restart-between-pages | UNSUPPORTED | UNSUPPORTED |
| equal-cursor-boundary | UNSUPPORTED | UNSUPPORTED |

The failing transcript ends on an empty response with `has_next: true`.
`delta/2` and `gamma/2` are missing from both emitted Singer records and SQLite.
Replaying that saved fixture against the patched connector passes. Evidence:
[original](../../evidence/widen-upstream/), [patched](../../evidence/widen-patched/),
[same-fixture replay](../../evidence/widen-patched-replay/).

This is an external manifestation of the already documented Singer empty-page
limitation, **not a third independent failure class or a claimed new SDK bug**.
See [the SDK history](../../SINGER.md).

## Reproduce the original trial

Use a separate Python 3.12 virtual environment; the tap's old SDK constraint
conflicts with CursorCheck's current `singer-repro` extra. From CursorCheck's root:

```text
python -m pip install . -r examples/widen_rest_api/requirements.txt
cursorcheck doctor --config examples/widen_rest_api/cursorcheck.toml
cursorcheck run --config examples/widen_rest_api/cursorcheck.toml
python -m unittest discover -s examples/widen_rest_api -p test_trial.py -v
```

`doctor` exits 3 for unsupported recovery; `run` exits 1 for the known empty-page
loss. The unittest expects that specific original behavior, including exact
missing IDs and request order; green CI here means the reproduction is intact,
not that the upstream connector passes every scenario.

The setuptools pin provides `pkg_resources` for the older SDK's filesystem
dependency. Without it the baseline could not import. One initial adapter attempt
also incorrectly set `auth_method` to an empty string; omitting it uses the tap's
no-auth default. Those setup errors are not counted as silent data loss.

## Experimental local patch

`experimental-empty-page.patch` changes the external connector, not the adapter:

- Upgrade its SDK constraint to 0.46.x and minimum Python to 3.9.
- Use the SDK's continuation hook for JSONPath token pagination.
- Add the direct empty-page regression and update the inferred schema's declared
  dialect expectation for the new SDK. Explicit-schema tests remain unchanged.

The original seven tests plus the new regression passed (8 tests, 0.36s). This is
an experiment, **not an upstream-ready contribution**: it changes default
empty-page policy and minimum versions; the Poetry lockfile has not been
regenerated. Maintainer review must decide whether continuation should be opt-in
and assess the SDK migration. No upstream issue, PR or message was sent.

To test it in a second environment, clone and checkout the pinned revision, apply
the patch with `git apply`, then install that checkout and CursorCheck's base
package with pip. Repeat the run command: pagination and retry pass, while recovery
remains unsupported (suite exit 3). Set `WIDEN_EXPECT_EMPTY=pass` when running
`test_trial.py` against the patched installation. The CI workflow contains exact
checkout, patch, installation and test steps for both variants.

## Fair comparison with existing tests

`compare_with_pytest.py` is a standalone **29-line** regression using the upstream
project's existing `requests-mock` style. It fails on the original connector and
passes with the patch. It observes the tap's emitted record iterator and mocks
HTTP; it does not check a process or sink. Run it explicitly with pytest; it is
intentionally not named `test_*.py` in this repository because the original tap
is expected to fail it.

The CursorCheck adapter is **91 physical lines**, including config, metadata,
subprocess wiring and sink. Its reusable configuration is another 8 lines; the
trial assertions are 44 lines. Adapter work began at 16:16:17 UTC; the first
usable suite result was recorded at 16:17:26 UTC (69 seconds). This excludes prior
source inspection, dependency installation and baseline testing, and was done
by the tool's author with prior SDK knowledge. It is not a new-user setup time.

For this one pagination case, extending the existing pytest suite is simpler.
CursorCheck adds an actual local HTTP source, full tap invocation, a materialized
test sink, consistent reports and replay. Whether those extras justify another
dependency remains unproven. This trial supports technical compatibility but
does **not** satisfy the three-project/independent-developer adoption gate.
