# LinkedIn Assistant

LinkedIn Assistant watches an inbox for LinkedIn export ZIP files, imports the data into Splunk Enterprise, and fills dashboards for network activity, job searches, skills and career history, learning, and import health. Every app event goes to index `linkedin`.

## Install

Download `dist/linkedin_assistant-1.0.2.spl`. In Splunk Web, choose **Apps → Manage Apps → Install app from file**, install the package, and restart Splunk. The app runs on a single Linux instance of Splunk Enterprise 9.3+ and uses its bundled Python 3.9+ runtime.

Drop an export ZIP into:

```text
$SPLUNK_HOME/var/lib/linkedin_assistant/inbox/
```

The app creates this directory on startup. Once a ZIP file is stable, the app imports it automatically. The dashboards select the newest snapshot after its indexed event count matches the import manifest. The default member is `personal`, and the default timezone is `UTC`. See [installation, privacy, settings and troubleshooting](build/linkedin_assistant/README.md).

When upgrading from 1.0.0 or 1.0.1, select the app upgrade option and restart Splunk. Version 1.0.2 fixes macro expansion and duplicate JSON extraction, which previously prevented automatic readiness and snapshot selection. Existing indexed imports will reconcile without another copy of the ZIP. If you changed the reconciliation report or macros locally, restore the definitions included in the package.

## Repository

- `build/linkedin_assistant/`: app source and installation guide.
- `tests/`: parser, lifecycle, configuration, and packaging tests built with synthetic data.
- `tools/`: deterministic package builder, dashboard generator, and Enterprise verification script.
- `dist/`: installable `.spl`, SHA-256 checksum, and historical AppInspect report.
- `docs/`: design notes, implementation records, and validation results.

The repository does not include a sample export or normalized personal records.

## Build and test

Building and testing require Python 3.9+ on Linux or macOS, with IANA timezone data available:

```sh
python3 -m unittest discover -s tests -v
python3 tools/generate_dashboards.py
python3 tools/package.py
```

The installed app has no third-party Python dependencies. To check an isolated Splunk Enterprise test instance after importing the supplied sample, run:

```sh
SPLUNK_TEST_PASSWORD=your_local_test_password python3 tools/verify_enterprise.py \
  --insecure-local-test --output validation-private/enterprise-results.json
```

The [validation report](docs/validation.md) lists the checks and their limits. Version 1.0.2 was tested with the official `splunk/splunk:10.4` image running Splunk Enterprise 10.4.4. The test covered ZIP ingestion, scheduled readiness, and populated dashboards in Splunk Web. The historical AppInspect reports apply only to the packages they name. This project is independent and is not affiliated with or endorsed by LinkedIn.
