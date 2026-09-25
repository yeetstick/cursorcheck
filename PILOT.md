# First independent pilot

Goal: determine whether a developer can wire an existing connector into the same
fixtures without rewriting its pagination or checkpoint logic.

## What to provide

- Repository URL or local checkout and supported Python version.
- Existing test command and the connector entry point.
- How to override its source URL and choose a disposable destination.
- How to read actual materialized ID/version pairs.
- Whether it restores state across fresh process invocations.

Production credentials and datasets are not needed. If a URL cannot be replaced
or output cannot be inspected, record the incompatibility instead of pretending
the tool supports that connector.

## Trial sequence

1. Run the connector's current tests and record the baseline.
2. Start a timer; write only the command wiring and destination reader.
3. Declare recovery capabilities truthfully and run `doctor`.
4. Run `all-pages` and `empty-middle-page`, then applicable recovery cases.
5. Keep a failing fixture and verify the connector fix against that same fixture.
6. Compare the work with expressing the case directly in the existing test suite.

## Record evidence

| Field | Result |
| --- | --- |
| Independent repository and maintainer | Pending |
| Baseline tests | Pending |
| Adapter setup minutes | Pending |
| Adapter lines (excluding existing connector code) | Pending |
| Supported and unsupported scenarios | Pending |
| Failure found and classification | Pending |
| Existing framework alternative and effort | Pending |
| Maintainer chose to retain check in CI | Pending |

Do not count the bundled reference/dlt examples or historical fixtures as three
independent adopters. The proposed standalone-product gate remains three
independently maintained project integrations, each under one hour, plus evidence
that developers prefer this experience to their existing tests.

No messages to external maintainers have been sent. A user-provided repository
can be evaluated locally before any public contribution or outreach is proposed.
