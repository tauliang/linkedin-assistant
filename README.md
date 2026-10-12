# LinkedIn Assistant

A Splunk Enterprise app that imports LinkedIn data exports by watching a ZIP inbox and populates network, job-search, skills/career, learning and import-health dashboards. All app events use **index `linkedin`**.

## Install

Download `dist/linkedin_assistant-1.0.2.spl`, then in Splunk Web choose **Apps → Manage Apps → Install app from file** and restart Splunk. Target: **single-instance Splunk Enterprise 9.3+ on Linux**, bundled Python 3.9+.

Drop an export ZIP into:

```text
$SPLUNK_HOME/var/lib/linkedin_assistant/inbox/
```

The app creates that directory, imports stable ZIPs automatically, and selects the newest snapshot after indexed counts reconcile. Default member: `personal`. Default timezone: `UTC`. See [installation, privacy, settings and troubleshooting](build/linkedin_assistant/README.md).

**Upgrading from 1.0.0 or 1.0.1:** select the app upgrade option and restart Splunk. Version 1.0.2 fixes macro expansion and duplicate JSON extraction that prevented automatic readiness and snapshot selection. Existing indexed imports can reconcile without copying the ZIP again. Restore any locally overridden reconciliation report or macros to the packaged definitions.

## Repository

- `build/linkedin_assistant/` — complete app source and packaged installation guide.
- `tests/` — synthetic parser, lifecycle, configuration and packaging tests.
- `tools/` — deterministic package builder and dashboard generator.
- `dist/` — installable `.spl`, SHA-256 checksum and AppInspect report.
- `docs/` — design, implementation record and validation evidence.

No sample user's export or normalized personal records are included.

## Build and test

Python 3.9+ on Linux/macOS, with IANA timezone data:

```sh
python3 -m unittest discover -s tests -v
python3 tools/generate_dashboards.py
python3 tools/package.py
```

The installed app has no third-party Python dependencies. To verify a running isolated Splunk Enterprise test instance with the supplied sample already imported:

```sh
SPLUNK_TEST_PASSWORD=your_local_test_password python3 tools/verify_enterprise.py \
  --insecure-local-test --output validation-private/enterprise-results.json
```

See [validation report](docs/validation.md) for checks and limitations. Version 1.0.2 was tested in the official `splunk/splunk:10.4` image (Enterprise 10.4.4), including ZIP ingestion, scheduled readiness and populated browser dashboards. AppInspect is static validation; its historical reports apply to the indicated earlier packages. This independent app is not affiliated with or endorsed by LinkedIn.
