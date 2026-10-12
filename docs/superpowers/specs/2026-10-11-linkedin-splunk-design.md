# LinkedIn Assistant — Splunk app design

App display name: **LinkedIn Assistant**. Splunk app/package identifier: `linkedin_assistant`. The app uses exactly one Splunk index: `linkedin`.

Status: implemented as LinkedIn Assistant 1.0.0 for Splunk Enterprise only. The sections below preserve the design baseline; the packaged README and docs/validation.md describe actual delivery and verification limits.

Implementation refinements: single-instance Linux Enterprise 9.3+ defaults, a provisioned linkedin index and enabled watcher, fixed sensitive-data exclusions (no raw-data toggle), complete schema provenance in private local state with bounded indexed manifests, source-row hashes computed before privacy projection, and a long event-time retention limit to preserve imported historical activity. No live Splunk deployment was available for runtime/UI validation.

Primary acceptance criterion: after one-time installation and setup, dropping a LinkedIn export ZIP into the configured inbox automatically imports its supported data and populates dashboards. No per-export commands, CSV uploads, configuration edits or manual dashboard selection are required.

## Purpose and assumptions
Analyze a member's downloaded LinkedIn data: network growth, career and skills, job search activity, learning, and export completeness. The product is a Splunk Enterprise app with a watched filesystem ZIP inbox. The initial deployment is a single Enterprise instance; distributed Enterprise placement is documented separately. Splunk Cloud and HEC are outside scope. No LinkedIn API, scraping, or account credentials are required.

Assume one member per configured inbox. One-time setup assigns a member label and timezone to that inbox. Additional members require separate configured inboxes; the app never guesses ownership from contact details or mixes exports belonging to different members. The exact Enterprise release and host OS must be chosen and verified during implementation.

The development sample was supplied as an already extracted directory. Raw data and its local inventory are deliberately excluded from this repository; aggregate results are in docs/sample-validation-summary.json. Files and cell contents are untrusted input and never executable instructions.

## Sample findings
49 CSV files contain 9,993 nonempty data records; 0 records have a column-count mismatch under Python's CSV reader. This is a structural inspection, not full semantic validation. Connections.csv has its header at CSV record 4 and 4,526 connections. Job applications span six files (1,180 rows); saved jobs span four files (603 rows). Numeric filename suffixes represent parts of a dataset, not separate event types. Other useful datasets include 344 invitations, 805 learning records, 814 received endorsements, 829 given endorsements, 178 company follows, 97 skills, 20 positions, and 29 receipts.

Ad_Targeting.csv repeats Company Names and Job Titles headers. Learning.csv has an unnamed final column. Notes.csv has only a header. Dates include `10 Oct 2026`, `10/3/26, 2:14 PM`, `10/01/26 11:36 AM UTC`, year-only values, blanks and N/A. Some dates lack timezone information. There is no messaging-history dataset in this sample.

## Selected approach and alternatives
Recommended and selected: an app-bundled Python worker, scheduled by Splunk Enterprise, watches a ZIP inbox and writes validated normalized JSON into a monitored spool. This delivers the requested drop-a-ZIP workflow without an external scheduler or per-import command. Splunk scripted inputs support scheduled execution; the worker uses the runtime supported by the target Enterprise release.

Native ZIP/CSV monitoring alone would not supply the schema handling, lifecycle tracking and automatic snapshot selection required here. A custom modular input remains a possible future replacement for the worker, but is not needed for the initial workflow.

## User workflow
1. Administrator installs the app, provisions the `linkedin` index and grants the analyst role access. One-time setup chooses the inbox, member label and timezone, verifies writable runtime directories, and enables the worker and monitor inputs. The setup page displays the exact inbox path and a readiness check.
2. User drops a LinkedIn export `.zip` into the server-side inbox. A network share can expose that same folder when configured by the administrator. An upload form in Splunk Web is outside the first release; dropping a file means copying it into the configured filesystem directory.
3. The worker discovers it on the next 30-second poll, waits until the copy is complete, validates the archive, normalizes records and publishes the spool. No user-supplied timestamp or member identifier is required on each drop.
4. The app landing page shows waiting, processing, indexing, ready, ready-with-warnings, or failed status. It refreshes every 30 seconds; analytical dashboards refresh every 60 seconds and automatically choose the newest reconciled snapshot for the configured member. Users may pin an older snapshot explicitly.
5. Successful imports appear in the dashboards automatically. A failed or incomplete import does not replace the last ready snapshot. Warnings show excluded datasets and rejected rows; no errors require inspecting server logs for a basic explanation.

Discovery is designed to take 30–60 seconds after a completed copy; indexing and dashboard refresh add latency. This is a design target to measure on the supplied sample, not a guaranteed end-to-end SLA.

## Architecture and delivery layout
`ZIP inbox -> scheduled app worker -> private staging + validation -> immutable JSON spool + manifest -> Splunk monitor inputs -> index `linkedin` -> automatic reconciliation -> latest-ready snapshot -> dashboards`

Deliver one installable `linkedin_assistant` app package for single-instance Enterprise. It contains:
- `bin/linkedin_zip_worker.py` and focused parser modules: ZIP discovery, safe extraction, normalization, atomic publication and durable state.
- `default/inputs.conf`: worker schedule and monitor templates enabled through one-time local setup; worker stdout contains only operational events, never analytic records.
- `default/props.conf`: event boundaries, timestamps and search-time JSON extraction.
- `default/data/ui/nav/default.xml`, Simple XML dashboards, macros, saved searches, and configuration-backed setup/health views.
- `default/savedsearches.conf`: scheduled all-time reconciliation that emits ready status only when expected unique event counts match actual counts per dataset.
- `README/`: custom configuration specification, installation and troubleshooting instructions, index and role templates, and distributed Enterprise placement guidance.
- Synthetic fixtures and parser tests. Sample personal data is excluded from the installable package.

Runtime data lives outside the app directory under a configured root, defaulting to `$SPLUNK_HOME/var/lib/linkedin_assistant/`. Subdirectories are `inbox/`, `processing/`, `spool/`, `archive/`, `failed/`, `quarantine/`, and `state/`. App upgrades preserve this root. The Splunk service account has access; analysts need inbox write access only if they deliver exports directly. The `linkedin` index must exist before ingestion is enabled.

For distributed Enterprise, run exactly one worker per inbox on a designated heavy forwarder or ingestion instance with local durable storage; deploy parsing configuration at the parsing tier, the `linkedin` index on indexers, and search objects/search-time extraction on search heads. Disable the worker on other nodes, including search-head cluster members. Ship appropriate components of the same release to each tier without enabling duplicate watchers. A universal forwarder is not the assumed host for the Python worker.

## ZIP lifecycle and recovery
The worker ignores temporary extensions and subdirectories. An atomic rename from `.part` to `.zip` is preferred for large copies. Ordinary `.zip` copies are also accepted: require unchanged size and modification time across two polling cycles, verify ZIP central directory and CRCs, then claim the file into `processing/` on the same filesystem. Stability alone is not proof of completion; an invalid archive is retried for a bounded five-minute copy-completion window before failure is reported. Processing holds a per-inbox lock so overlapping invocations cannot import the same file.

Each claimed archive gets a content hash, persistent state record and private extraction directory. Reject encrypted archives with an actionable unsupported-format error. Accept a single enclosing directory, map relative dataset paths, and reject ambiguous duplicate paths. Enforce path, symlink, file-count, compression ratio and expanded-byte limits. A fatal archive/schema error publishes no analytic spool. Row-level issues may yield a ready-with-warnings import only when every source row is accounted for.

After validation, publish immutable files with deterministic names by export and dataset. Write temporary files outside the monitored tree, then atomically rename them onto the same filesystem. A restart resumes from durable phase state and existing hashes rather than generating new IDs or blindly writing new spool copies. The monitor path includes only completed JSON files; ZIPs and raw extraction directories are never monitored.

The ZIP moves to `archive/` after successful spool publication; this is a processed archive, not proof of completed indexing. Fatal failures move to `failed/` with a structured reason. Keep pending spool files until reconciliation succeeds. Raw archives, extracted staging and quarantine are private local data, with an administrator-configured retention policy shown during setup; none is automatically indexed or packaged. Never delete a pending import's spool or claim exactly-once delivery. Import health distinguishes processing completion from indexing completion.

## Ingest and parse contract
The user-facing ingestion contract accepts a ZIP dropped into the inbox. A directory reader is retained only for developer fixtures, including the supplied already-extracted sample. ZIP extraction rejects absolute paths, parent traversal, symlinks and excessive expanded size or entry count. Never overwrite arbitrary destination files. Handle UTF-8 BOM, CRLF, quoted delimiters, embedded newlines and Unicode with a real CSV parser. Recognize supported schemas by expected headers and filename mapping; skip Connections' known preamble only after locating its header. Unknown schemas and malformed records enter quarantine with file, CSV record number and reason; they are never silently discarded.

Normalize headers to snake_case. Repeated headers receive stable suffixes (`company_names`, `company_names_2`, `company_names_3`) and unnamed headers receive positional names. Retain original ordered headers in the manifest. Never use a dictionary reader that loses repeated fields. Remove filename part suffixes only for known datasets. Keep the original relative filename on every event.

Each canonical event contains schema_version, member_id, export_id, dataset, source_file, source_record, event_id, record_hash, export_time, event_time, time_basis, time_precision, timezone_assumption, and normalized fields. Member ID comes from the inbox configuration and is independent of an email address. Also retain archive_hash, import_time, snapshot_time and snapshot_time_basis. Preserve blanks versus unavailable values where meaningful. Nested question/answer values remain text unless a known format is validated; never evaluate cell contents. No attempt to infer protected characteristics or rank individuals.

Use a declared date-format registry per dataset. Explicit timezone offsets take precedence; for timezone-free timestamps require a configured timezone and record it. Preserve date-only, month-only and year-only precision. Do not interpret year-only career dates as precise activity timestamps. Keep original date values. Two-digit years use an explicit documented century mapping, never a platform-dependent parser pivot. Unparseable dates produce an issue and retain the row.

For genuine dated activity, event_time is the documented primary date (connected_on, sent_at, application_date, saved_date, endorsement_date, followed_on, etc.). For profile snapshots or dates without sufficient precision, use snapshot_time with time_basis=snapshot and keep the partial source dates separately. If trustworthy export metadata supplies an export timestamp, retain it and use snapshot_time_basis=export_metadata. Otherwise leave export_time unset, set snapshot_time to the durable first-claimed import timestamp, and use snapshot_time_basis=import_observed; dashboard labels must say “imported snapshot,” not “exported at.” Filesystem and ZIP entry modification times are not treated as export dates. No per-file timestamp prompt is required. Learning uses completion time then last-watched time when valid, and records which was selected.

## Repeat imports and snapshot semantics
An export_id identifies an immutable import manifest and is derived from the configured member and a digest of ordered relative dataset paths and uncompressed file bytes; it is independent of ZIP filename and ZIP container timestamps. A raw archive hash also enables a cheap exact-repeat check. Renaming or repacking the same export is a no-op with a visible duplicate-skipped status. Do not bypass duplicate suppression automatically; an administrator can retry failed processing using the same IDs. Record hashes use canonical values plus member and dataset, excluding source filename and part number. Repeated identical records within an export are reported with occurrence counts before canonicalization; the source rows remain accounted for in the manifest. Event IDs additionally include export_id so the same connection appearing in later snapshots remains traceable.

Keep each export as a snapshot. Default dashboards automatically select the newest ready or ready-with-warnings export_id by durable import sequence per member; event chronology is within that snapshot. Never aggregate multiple exports without an explicit deduplication or comparison rule. Do not infer record deletion merely because it is absent from an export. Stable person links can support comparisons where present; names alone are not reliable identity keys.

Local checkpoint state is updated atomically through claimed, validated and published phases. Spool publication does not mean indexing succeeded. A scheduled reconciliation search compares the immutable expected manifest with all-time indexed distinct event IDs per dataset, including the case of zero expected analytic events. Repeated status events have stable status identifiers and are collapsed by searches. A snapshot becomes selectable automatically only after all counts reconcile. After ten minutes without reconciliation, show an indexing-delay warning and retry automatically; do not hide the previous ready snapshot. Retries preserve IDs and dashboards deduplicate transport duplicates by event_id.

The reconciliation saved search writes completion events to `linkedin` with a dedicated operational sourcetype through an explicitly configured supported summary-index action. Its owner needs search and summary-write permission for `linkedin`. Reconciliation counts only the expected analytical sourcetypes; operational manifests and completion events are excluded so writing a status event cannot change analytical counts. Setup checks these permissions and that the saved search is enabled. The filesystem worker does not need a Splunk management token or HEC token.

## Indexing and access
Use the single index `linkedin` for all app events: approved analytical records, import manifests, validation summaries and completion status. Every input, dashboard search, macro, saved search and summary-write action must explicitly target `linkedin`; no additional app index is required or created. Distinguish datasets and operational events with sourcetypes and event-kind fields. Suggested initial index retention is 365 days for all indexed app data, configurable by the administrator; separate per-dataset retention is not assumed within this index.

Default analytics projection excludes emails, phone numbers, birth dates, addresses, message bodies, screening answers, identity asset text and verification document details before serialization. Retain only needed profile URLs under an explicit field policy. Sensitive datasets are excluded by default. Enabling them requires an administrator to accept that every role with search access to `linkedin` can potentially retrieve them; dashboard permissions and sourcetype filters do not provide separate index-level isolation. Redacting a dashboard does not remove indexed data: exclusion happens before ingest. Import manifests record exclusions and counts. Raw export copies stay local and outside installable packages and source control.

Use sourcetypes `linkedin:connection`, `linkedin:invitation`, `linkedin:job_application`, `linkedin:saved_job`, `linkedin:learning`, `linkedin:endorsement`, `linkedin:profile`, and a documented mapping for remaining supported datasets; ops events use `linkedin:import`.

For the selected monitor transport, each JSON event is one physical line with escaped cell newlines, event_time first in a fixed UTC format, and bounded event size. Props set SHOULD_LINEMERGE=false, a newline LINE_BREAKER, a tested TIME_PREFIX/TIME_FORMAT/MAX_TIMESTAMP_LOOKAHEAD, and KV_MODE=json at search time. Do not also enable INDEXED_EXTRACTIONS=JSON. Configure acceptable historical timestamp limits deliberately and test old records. Oversized records go to quarantine rather than being silently truncated. Monitor stanzas are generated per supported dataset path with explicit sourcetype assignments and `index = linkedin`; the spool root must never use a catch-all input that sends every dataset to one sourcetype. The worker publishes only completed immutable spool files; never monitor temporary outputs. Use source identity and importer checkpoints deliberately rather than using crcSalt to force reingestion.

## Dashboards
Every analytical view opens with the configured member and “Latest ready snapshot” selected; selectors remain available for optional investigation. Latest-ready selection is resolved dynamically from reconciled status events, including while the page stays open. Analytical searches default to all available history within that snapshot; an optional time filter narrows activity panels only. The landing page shows the inbox path, latest import status and actionable errors. Every view clearly shows the selected snapshot and snapshot time basis, and distinguishes activity dates from snapshot dates. Inventory and profile panels do not disappear under an activity time filter.

| Dashboard | Useful panels | Limits |
|---|---|---|
| Export overview | inbox path; import progress and errors; datasets and row counts; snapshot timestamp and basis; earliest/latest dated activity; excluded datasets; rejected rows; missing dates | Counts distinguish source rows, canonical records and indexed events. |
| Network | connections added by month; cumulative connections as of the selected snapshot; top companies/titles; missing company/title; searchable contacts | Current exported company/title is not historical employment at connection time. |
| Invitations | incoming/outgoing by month; direction totals; exported message-presence indicator if enabled | No acceptance-rate claim: invitations lack a reliable outcome field. |
| Job search | applications over time; top companies/titles; saved jobs over time; applications matching a saved job URL | This is export activity, not an interview or offer funnel. Saved-to-applied matching is observational, not conversion attribution. |
| Skills and career | received/given endorsements; most endorsed skills; declared skills without endorsements; positions, education and certifications | Endorsements do not measure proficiency; partial dates remain partial. |
| Learning | viewed/completed/saved counts by content type; completions over time; missing-date totals | No invented hours or completion percentages without a valid denominator. |
| Import health | expected versus indexed unique events; schema changes; quarantine reasons; duplicate counts; source-file drilldown | Validation search covers all event time, including historical activity. |

Optional administrator-enabled sensitive-data view: receipts by currency and month, with no cross-currency sum without an explicit FX source. Advertising attributes can be inspected as exported targeting labels, not inferred facts about the member.

## Example searches
These are design examples against the proposed normalized schema, not validated searches against a running Splunk instance. Production macros will safely quote and validate selector tokens.

Connections by current company in one snapshot:
```spl
index=linkedin sourcetype=linkedin:connection member_id="$member_id$" export_id="$export_id$"
| dedup event_id
| stats count AS connections BY company
| sort - connections
| head 20
```

Monthly connection additions:
```spl
index=linkedin sourcetype=linkedin:connection member_id="$member_id$" export_id="$export_id$" time_basis=activity
| dedup event_id
| timechart span=1mon count AS connections_added
```

Cumulative network must search the full selected snapshot history before accumulating; apply a display-time filter after accumulation so the visible start is not incorrectly zeroed.

Applications by month:
```spl
index=linkedin sourcetype=linkedin:job_application member_id="$member_id$" export_id="$export_id$" time_basis=activity
| dedup event_id
| timechart span=1mon count AS applications
```

Reconciliation uses an all-time search and compares manifest expected counts with `dc(event_id)` grouped by member_id, export_id and dataset. Transport duplicates are reported separately from source-row duplicates.

## Validation and acceptance
1. Inventory source rows using correct header offsets; preserve all repeated/unnamed columns. All 9,993 source rows must reconcile to emitted, deliberately excluded, duplicate-accounted, or quarantined counts.
2. Synthetic tests cover preambles, BOM, embedded newlines, duplicate headers, suffix parts, malformed CSV, ZIP traversal, oversized inputs, timezone-free dates, year-only dates, invalid dates and repeated imports.
3. Prove default serialized analytics events contain none of the excluded sensitive fields or values using explicit fixtures.
4. Validate the packaged Enterprise app configuration with Splunk btool and AppInspect; confirm deployed timestamp extraction and JSON field extraction with representative files.
5. Confirm historical dates survive ingestion, event boundaries hold for multiline text, and indexed unique IDs reconcile with the manifest. Test restart and retry behavior.
6. Verify all inputs, searches and summary actions use only `linkedin`, and operational events never inflate analytical counts. Open each dashboard in the chosen Enterprise release and test snapshot isolation, empty datasets, selector escaping, access restrictions and historical time ranges.
7. End-to-end acceptance: after one-time setup, drop a valid ZIP and verify the expected supported data appears in all applicable dashboards without commands, prompts, configuration edits or selecting the new snapshot. Measure discovery, publication, indexing and refresh latency separately.
8. Exercise slow copies, `.part` rename, corrupt/encrypted archives, ZIPs with a root folder, repeated/renamed/repacked ZIPs, restart in every processing phase and index unavailability. Verify one logical import, visible outcomes and automatic recovery with unchanged event IDs.
9. Drop a second export and confirm the app retains the previous snapshot while processing, then automatically switches after reconciliation. A failed second export must leave the prior dashboards usable. Verify scheduled-search permissions, all-time reconciliation, zero-event imports and fresh-install empty states.

No Splunk runtime has been discovered or used in this design phase. Deployment compatibility, SPL and dashboards require implementation and runtime validation before being described as working.

## Delivery scope and review
The first implementation includes the ZIP inbox worker, safe extraction, normalized JSON spool, Enterprise ingestion configuration, durable repeat-import handling, indexing reconciliation and the overview/network/invitations/jobs/skills-career/learning/import-health dashboards. Sensitive datasets remain opt-in and share the `linkedin` index access policy. Splunk Cloud, HEC, external schedulers and a browser upload form are outside this release.

Review this revised ZIP-drop workflow before implementation planning. The remaining deployment detail is the Enterprise version/OS and whether the initial installation is single-instance or distributed; the design defaults to single-instance and requires no per-export interaction.

## References
- Splunk props.conf reference: https://help.splunk.com/en/splunk-enterprise/administer/admin-manual/9.4/configuration-file-reference/9.4.5-configuration-file-reference/props.conf
- Structured extraction guidance: https://help.splunk.com/en/splunk-enterprise/get-started/get-data-in/9.1/configure-indexed-field-extraction/extract-fields-from-files-with-structured-data
- Splunk inputs.conf reference: https://help.splunk.com/en/splunk-enterprise/administer/admin-manual/9.4/configuration-file-reference/9.4.0-configuration-file-reference/inputs.conf
- Splunk scripted input scheduling: https://help.splunk.com/en/splunk-enterprise/developing-views-and-apps-for-splunk-web/9.0/build-scripted-inputs/setting-up-a-scripted-input
