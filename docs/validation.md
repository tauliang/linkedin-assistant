# LinkedIn Assistant validation

## 1.0.2 real Splunk Enterprise validation — 2026-10-11

Tested the official `splunk/splunk:10.4` Linux/amd64 image, which resolved to **Enterprise 10.4.4, build f0f12fcdcaa1**. Image manifest digest: `sha256:4f18abfb106b29dc6af68868fb2e5c5ae68aa8e9ac6bfb28b7bec12ede2079aa`. Splunk Web and management ports were bound only to localhost in an isolated Docker/Colima test environment. This was a real splunkd and browser test, not an SPL emulator.

### Reproduced failures and fixes

1. Installed the unchanged 1.0.1 package and dropped the supplied sample ZIP into the inbox. The watcher automatically indexed **9,608 records and 39 manifests**, but the scheduler wrote no readiness event and Overview showed zeros.
2. The actual scheduled job expanded to `search search index=linkedin ...`. The extra `search` became a literal raw-event filter: the job scanned **72 events** and returned **zero reconciliation rows**, reproducing the screenshot. A regression using Web/scheduler dispatch failed with `Expected exactly one reconciled import; got 0`. Removing the leading command from both macros returned one reconciled import with actual=expected=9,608 and 39 datasets. The next normal scheduler run wrote readiness automatically; no manual collect was used.
3. The previous explicit `spath` workaround duplicated fields already extracted by `KV_MODE=json`. The latest-snapshot query returned a multivalue export ID, and Web joined the two IDs into one invalid token. The real-engine comparison showed `mvcount(export_id)=2` with `spath`, versus **1** without it. Removing redundant extraction restored automatic snapshot selection.
4. The static Personal choice duplicated the dynamic Member choice. A single grouped dynamic choice search now returns Personal once, without a conflict or empty-search warning.

### Acceptance evidence

A second clean container installed from the 1.0.2 package automatically imported the ZIP and published readiness. The requested current-time axis correction was then loaded into that clean instance and all engine checks were repeated. Analytical macros and chart dispatch now end at `now`; reconciliation retains its wider window. The old window produced a future bucket in 2036, while all seven corrected time charts end in the current month with no future bucket. Browser verification also covered the corrected Network chart axes.

- **34 local tests passed**, including regression checks for macro dispatch, single JSON extraction and unique Member choices.
- The read-only `tools/verify_enterprise.py` exercises installed XML, the actual latest-snapshot token-producing searches, Member choices, and all **44 panel searches across eight dashboards** against Splunk REST. It models the implicit leading search command used by Web/scheduler. It rejects a multivalue snapshot token and unexpected empty panels. The sample legitimately has no application/saved-job overlap and no imports awaiting reconciliation.
- **Automatic ready events: 1**, actual_records=9,608. Repeated scheduled executions suppressed duplicates.
- Browser verification: Overview displayed **4,508 connections, 1,180 applications, 814 received endorsements, 14 completed learning items**, dataset bars and import inventory. Job search displayed populated monthly application/saved-job charts and company/role breakdowns. Both used the automatic latest snapshot without manually setting an export ID.
- Aggregate-only engine results are in `docs/enterprise-10.4.4-results.json`. Browser screenshots remain local under `validation-private/`; personal export files and record-level results are not committed.
- Historical AppInspect reports below apply to earlier packages. No fresh AppInspect result is claimed for 1.0.2; the current evidence includes real engine and UI execution.

### Repeat the real-engine check

Install the release into an isolated Enterprise 10.4 instance and drop the same sample ZIP into the app inbox. Set `SPLUNK_TEST_PASSWORD` in your environment, then run:

```sh
python3 tools/verify_enterprise.py --url https://127.0.0.1:18089 \
  --insecure-local-test --output validation-private/enterprise-results.json
```

The verifier never imports data, writes ready events or modifies configuration. TLS bypass is allowed only for the isolated localhost test. Expected counts are specific to the supplied sample. Analytical totals and tables also include records only through the present; future-dated records remain indexed and included in reconciliation. The sample has no future-dated records. This does not claim validation of other Enterprise releases, distributed topology, or customized local/user overrides. Existing deployments can upgrade without reimport; overrides must not retain the broken macros or diagnostic reconciliation search.

## Historical 1.0.1 static validation — 2026-10-11

**Superseded:** the proposed extraction workaround did not fix the user’s dashboards and duplicated fields in Splunk 10.4. See the real runtime findings above.

Target-host evidence showed the original `li_reconcile` macro returning no rows, while a search with explicit `spath` followed by JSON-field filtering returned 39 matched datasets. Actual and expected totals both equal 9,608; identifiers were present. This establishes that the indexed import is complete and the original search path fails. It does not establish the underlying reason automatic JSON extraction differs on that installation.

The correction adds explicit JSON extraction before application-field predicates in both macros, the saved search's nested readiness lookup, and all dashboard search boundaries. Indexed metadata and time limits stay before extraction. Record deduplication, expected-dataset checks, privacy projection and ingestion behavior are unchanged.

- **31 local tests passed.** The new search-boundary regression failed against 1.0.0 and passed after correction. It checks emitted macro, scheduled-search and dashboard queries, including nested searches. This is configuration validation, not an SPL engine emulator.
- Independent review found no critical or important patch defects. All eight generated XML views differ only in query text; token quoting and member/export isolation remain intact.
- **AppInspect 4.3.1 precert:** 128 success, 117 not applicable, 1 skipped, 6 warnings, **0 errors/failures/future failures**. Report: `dist/appinspect-report-1.0.1.json`. The trusted-library metadata refresh was unavailable during this local run; installed check definitions were used. The same six advisories are explained below.
- Distribution: `dist/linkedin_assistant-1.0.1.spl`. No supplied CSVs, search-result export or indexed personal records are packaged or committed.

The patched search has not yet run on the target host. Acceptance: install as an upgrade and restart; `li_reconcile` should report 39 datasets with actual=expected=9,608. The scheduled report should write one ready event, dashboards should select that snapshot automatically, and subsequent runs should suppress another ready event. Existing indexed records require no reimport. Preserve local settings/runtime state; a previously saved diagnostic override of the reconciliation report must be restored to its packaged search.

## 1.0.0 build validation

Validated on 2026-10-11. Distribution: `dist/linkedin_assistant-1.0.0.spl`.

## Automated checks

- **30 synthetic tests passed**: parser/schema rules, quoted multiline CSV, preambles, repeated headers, unnamed-field privacy, complete source-row deduplication, date formats and timezone handling, ZIP traversal/symlink rejection, copy stability, CRC/decompression failure isolation, locking, duplicate imports, partial-publication restart, bounded metadata, explicit index/sourcetype routing, XML token quoting and deterministic package structure.
- Python 3.13.7 executed the suite. Bundled scripts also passed Python 3.9 AST syntax validation. GitHub Actions is configured to run the suite on Python 3.9 and 3.13; a CI run is not claimed until GitHub reports it.
- Full supplied sample processed through the real inbox worker in a disposable local runtime. **9,993 source rows = 9,608 analytical records + 367 deliberately excluded rows + 18 source duplicates.** Zero quarantined rows; zero unparsed activity dates; 39 dataset manifests. All event IDs were unique, all indexed JSON events stayed within 128 KiB, and accounting totals reconciled.
- Checked 123 excluded contact/identity source values: zero occurrences in normalized analytics. All normalized field names passed the narrative/contact exclusion check. Synthetic narrative values are also covered. This validates the fixed field projection, not a general content-classification or anonymization guarantee.
- Deterministic tar/gzip packaging tests confirmed a single `linkedin_assistant/` root, standard permissions, and exclusion of local/runtime data, sample exports, symlinks and Python caches.
- **Splunk AppInspect 4.3.1, precert mode:** 128 success, 117 not applicable, 1 skipped, **0 errors, 0 failures, 0 future failures, 6 warnings**. Full machine-readable report: `dist/appinspect-report.json`.

## AppInspect advisories

1. Cloud Victoria does not synchronize inputs.conf to indexers — this app targets Enterprise.
2. Legacy Python 2/3 cross-compatibility advisory — this app requires Python 3.9+; scripted input explicitly selects Python 3.9 for Enterprise 9.3 and declares Python 3.9/3.13 support for newer releases.
3. Scripted input present — intentional local watcher; no credentials or network access.
4. Every-minute reconciliation search — intentional for automatic dashboard population; monitor scheduler load as export volume grows.
5. Custom config not configured for search-head-cluster replication — defaults target a single instance; distributed placement is documented and requires administrator setup.
6. Cloud sc_admin role advisory — Enterprise admin role is used; Cloud is not supported.

## Independent review

A separate reviewer inspected the source, configuration, SPL and tests. Important findings were corrected: narrative-field exclusions, corrupt-DEFLATE and directory-entry isolation, bounded indexed manifest metadata with complete local provenance, and explicit Python 3.9 selection on existing Enterprise installations. Regression tests passed after fixes. Readiness requires every expected dataset as well as matching record counts. No further confirmed SPL syntax defect was reported.

## Historical 1.0.0 runtime boundary

No running Splunk Enterprise instance was available in this build environment. Therefore these results do **not** verify actual btool effective configuration, scheduled collect execution, timestamp extraction inside splunkd, or rendered dashboards on the target release. The package is prepared for installation; perform the following host smoke test before production use:

1. Install and restart Enterprise. Check effective inputs/props/indexes/savedsearches configuration using the packaged README commands.
2. Confirm the Setup & inbox heartbeat, copy a non-sensitive test ZIP and observe processing → indexing → ready without per-import commands.
3. Confirm expected unique records reconcile, latest snapshot selection changes automatically, historical charts are correct, and an invalid second ZIP leaves the previous ready snapshot visible.
4. Confirm the intended analyst role can search only permitted indexes and the reconciliation owner can run collect into linkedin.

## Build choices

Initial defaults target Linux Enterprise 9.3+ on one instance, fixed sensitive-field exclusions, UTC unless configured, and no browser upload form. The index age limit is long to preserve historical event timestamps; administrators must set a size budget/retention policy for their deployment. Full raw ZIPs expire after 30 days by default; spool/state cleanup is an explicit administrator operation. These choices and their limitations are documented in the packaged installation guide.
