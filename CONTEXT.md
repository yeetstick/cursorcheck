# Development context

CursorCheck 0.0.2 is a local pilot build. The adjacent blueprint describes the
larger proposed project. Five scenarios are implemented, but external adoption,
independent onboarding and the entire v0.1 acceptance gate are not satisfied.

`run_case(fixture, adapter, output)` owns a source process, worker tree and fresh
artifact directory. Expected ID/version pairs are independent of the connector.
The source serves an explicit page schedule. Never derive ground truth from an
uninterrupted run of the same worker. Explicit worker failure is an execution
error, not silent loss. Unsupported recovery is never green.

The reference worker commits SQLite output/checkpoint together; opt-in seeded
modes violate specific invariants. The dlt adapter configures real framework
pagination and loading. Its dependent-resource modes reproduce a reported
configuration behavior without modifying framework algorithms.

Core runtime is standard-library Python. dlt/DuckDB and Hypothesis are optional
extras. No cloud services, telemetry, production credentials or downloads occur
when running the core tests. See README for trust and platform limits.

Windows Job Objects and POSIX process groups supervise worker descendants. A
Windows wrapper waits for job assignment before receiving the user command via
stdin. Never launch the command before assigning it to the job. Restart waits
for the fixture's blocked-request marker before termination and reuses state.

Documentation and code must distinguish seeded defects, historical behavior,
newly discovered bugs and independent user adoption. Do not claim full v0.1 or
production certification from the local fixtures.
