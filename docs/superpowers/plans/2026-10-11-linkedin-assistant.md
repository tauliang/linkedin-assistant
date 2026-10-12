# LinkedIn Assistant Implementation Plan

Goal: ship an installable Splunk Enterprise .spl with a watched ZIP inbox and dashboards backed exclusively by index linkedin.
Architecture: standard-library Python worker publishes immutable JSON spool plus manifests. Splunk monitors dataset paths, reconciles indexed IDs with expected counts, and dashboards automatically use the latest ready snapshot. Default single-instance Enterprise 9.3+; one configured member per inbox.
Spec: ../specs/2026-10-11-linkedin-splunk-design.md
Execution: inline in this session, as authorized by the request to build and export.

Global constraints: LinkedIn Assistant; package linkedin_assistant; index linkedin only; no personal sample data in distributable; runtime outside app; no tokens or network services required.
Review focus: partial ZIP copies; duplicate/repacked archives; restart during publication; sensitive data in generic fields; empty and historical snapshots.

## Tasks
- [x] 1. Parser and archive safety. Files: bin/linkedin_lib/{archive,parser,schema}.py; tests/test_parser.py. Interface: parse_archive(path, member, claimed_time, timezone) returns records and per-dataset manifests. Write/run failing tests for CSV preamble, repeated headers, projection, precision, timezone, traversal, suffix parts and repack identity; implement; run unittest suite.
- [x] 2. Durable inbox worker. Files: bin/linkedin_lib/worker.py, bin/linkedin_zip_worker.py; tests/test_worker.py. Interface: run_once(config, now) returns status events. Write/run failing tests for two-poll stability, CRC grace window, restart/publication, duplicate and failure isolation; implement atomic local state, locks, spool and lifecycle; run suite.
- [x] 3. Enterprise configuration and dashboards. Files: default/*.conf, metadata/default.meta, default/data/ui/{nav,views}, README. Explicit index creation, scheduled input and per-dataset monitor mapping, JSON parsing, historical timestamps, reconciliation and auto-selected snapshots. Add static XML/conf/SPL contract tests; run them failing then implement and run suite.
- [x] 4. Package and verify. Files: tools/package.py, tests/test_package.py, dist/*.spl, validation report. Test archive allowlist and permissions; implement deterministic gzip tar export; run suite, actual sample import in isolated temporary runtime, package-content validation and AppInspect if available. Record runtime limitations.
