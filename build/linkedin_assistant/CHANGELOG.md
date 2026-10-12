# Changelog

## 1.0.2
- End analytical searches and time-chart axes at the current time instead of ten years in the future.
- Fix macro expansion in Splunk Web and scheduled searches: remove the leading search command that became a literal raw-event filter.
- Remove redundant spath extraction alongside KV_MODE=json, preventing duplicated export IDs from breaking automatic snapshot selection.
- Populate Member choices from one grouped search to avoid duplicate values.
- Verify real ingestion, scheduled readiness, snapshot tokens and all eight dashboards in Splunk Enterprise 10.4.4.

## 1.0.1
- Extract JSON explicitly before filtering application fields in reconciliation, record searches, dashboard selectors and health panels. This avoids incomplete imports being inferred from automatic field-discovery failures.
- Existing indexed imports reconcile after upgrade; no ZIP reimport is required.

## 1.0.0
- ZIP inbox with safe bounded reading, stable-copy detection, durable checkpoints and duplicate handling.
- Per-dataset JSON ingestion into the single linkedin index.
- Eight dashboards and automatic latest-ready snapshot selection after reconciliation.
- Fixed sensitive-field exclusions; no credentials or external services required.
