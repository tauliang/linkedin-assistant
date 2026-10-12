# LinkedIn Assistant 1.0.3

Drop a LinkedIn download ZIP into an inbox; the app imports supported data into **index `linkedin`** and automatically populates eight Splunk Enterprise dashboards. This independent app is not affiliated with or endorsed by LinkedIn.

## Upgrade from 1.0.0 through 1.0.2

Install `linkedin_assistant-1.0.3.spl` through **Apps → Manage Apps → Install app from file**, select the option to upgrade the existing app, and restart Splunk. Keep the runtime directories and existing `linkedin` index. No ZIP reimport or index deletion is needed. Allow the next reconciliation job and dashboard refresh a few minutes to select the already indexed snapshot.

Version 1.0.3 identifies Tau Liang as the app author and enables Splunk's package update check. It includes the reconciliation, snapshot selection, and time-axis corrections from 1.0.2. If you previously saved diagnostic changes over the reconciliation report or macros, restore the full packaged definitions; local/user overrides take precedence over app defaults.

## Install (single Enterprise instance)

Target: **Splunk Enterprise 9.3+ on Linux**, using its bundled Python 3.9+ runtime. No pip install, LinkedIn credentials, internet access or HEC token is required on the Splunk server. The first release does not support Splunk Cloud or Windows.

1. As a Splunk administrator, open **Apps → Manage Apps → Install app from file** and select `linkedin_assistant-1.0.3.spl`.
2. Restart Splunk when prompted. The package defines the `linkedin` index and enables the 30-second ZIP worker and file monitors. If an index named `linkedin` already exists, review its effective configuration with btool before use; local/system configuration takes precedence.
3. Open **LinkedIn Assistant → Setup & inbox**. The heartbeat should show an inbox at:

   `$SPLUNK_HOME/var/lib/linkedin_assistant/inbox/`

   For `/opt/splunk`, that is `/opt/splunk/var/lib/linkedin_assistant/inbox/`. The Splunk service account creates and owns the runtime directories. Grant a file-delivery account write access to the inbox only, if necessary; do not make the whole runtime tree world-writable.
4. Copy an actual LinkedIn export ZIP into that directory. For large transfers, copy it with a `.part` suffix and rename to `.zip` after completion. The worker also accepts ordinary `.zip` copies after two stable polls. The filename must end in lowercase `.zip`.
5. Watch **Import health**, then open the analysis dashboards. Discovery generally takes 30–60 seconds after copying; indexing, the one-minute reconciliation job, and dashboard refresh add time. The latest complete snapshot is selected automatically. Failed imports leave the previous ready snapshot selected.

There is no browser upload form in 1.0. A configured network share can expose the same inbox. The package contains no demonstration personal data.

## Member and timezone (optional one-time settings)

Default member is `personal`; default timezone for timestamps without an explicit zone is `UTC`. If the member exported dates in another timezone, create `$SPLUNK_HOME/etc/apps/linkedin_assistant/local/linkedin_assistant.conf` before the first import:

```ini
[settings]
member_id = personal
timezone = America/New_York
copy_grace_seconds = 300
archive_retention_days = 30
```

Use an IANA timezone available on the Linux host. One member per inbox is supported in this release. Do not change member identity or timezone to reinterpret already imported exports; repeat imports intentionally retain their original event IDs and interpretation. A multi-member deployment needs separate ingestion instances/runtime roots and explicit monitor placement, rather than changing settings between ZIP drops.

The snapshot is labeled `import_observed`: ZIP metadata is not a trustworthy export date. Per-record activity dates are used where present, and year/month career dates retain their original precision. Timezone-free ambiguous DST times use the first occurrence (fold 0); nonexistent local times are currently interpreted using the configured zone's offset and are not separately flagged.

## Dashboards

- **Overview:** snapshot totals, available datasets and import inventory.
- **Network:** monthly/cumulative connections, companies, roles and contacts.
- **Invitations:** direction and activity; no unsupported acceptance-rate claim.
- **Job search:** applications, saved jobs and observed URL overlap; no invented interview/offer funnel.
- **Skills & career:** endorsements, declared skills, positions, education and certifications.
- **Learning:** completions, saved content, types and undated items.
- **Import health:** worker heartbeat, lifecycle, per-dataset reconciliation, duplicates and rejected rows.
- **Setup & inbox:** exact folder, runtime heartbeat and ready snapshots.

All searches use `linkedin`. Operational events use separate `linkedin:worker`, `linkedin:import`, `linkedin:manifest` and `linkedin:ready` sourcetypes. Analysts need explicit search access to `linkedin`. The scheduled reconciliation search's owner must be allowed to search this index and run `collect` (typically an admin). It is app-shared and installed as a scheduled search; review ownership/permissions under Settings → Searches, reports, and alerts if imports remain in indexing. The job writes ready events only after expected dataset counts and unique event IDs reconcile. Run `LinkedIn Assistant - reconcile imports` manually once to diagnose SPL or role issues. Do not disable it while expecting automatic snapshot selection.

## Privacy and archive safety

The app excludes contact emails, phone numbers, birth dates, addresses, narratives, messages, screening answers, identity assets and verification data before indexing. Only recognized schemas/fields are admitted; unnamed columns are retained in local schema provenance but their values are excluded from indexing. Names, profile URLs, companies, roles, skills and other approved analytical attributes remain personal data. The first release's exclusion policy is fixed; it has no toggle to index raw identity or screening data. Review `bin/linkedin_lib/schema.py` before extending that policy: everyone who can search `linkedin` can retrieve included data.

Stored and DEFLATE ZIP entries are supported. ZIPs are read without extracting paths onto disk. Absolute/traversal paths, symlinks, encryption, duplicate archive paths and oversized entries are rejected. Limits: 128 MiB compressed ZIP, 256 MiB total expanded content, 64 MiB per entry, 2,000 entries, compression ratio 1,000:1 for entries over 1 MiB, 2 MiB per CSV field, and 128 KiB per serialized indexed record. Malformed CSV syntax fails the archive; unknown schemas, row width mismatches and oversized normalized records are accounted for in manifests and a metadata-only quarantine report. No cell contents are executed or used as shell commands.

Raw ZIPs move to `archive/` after durable publication and `failed/` on fatal errors. Those raw ZIPs may contain sensitive data; access is limited to the Splunk service account. Archived/failed ZIPs are removed after 30 days by default (0 disables cleanup). Filesystem timestamp is used for raw archive cleanup. Quarantine files contain source locations and reasons, not row bodies. Full ordered headers and file lists are retained in private local state; bounded file-count/sample metadata is indexed to avoid oversized manifest events. Processing completion does not mean indexing is complete.

## State, storage and repeats

All runtime state is outside the installed app, under `$SPLUNK_HOME/var/lib/linkedin_assistant/`, and survives app upgrades. Back it up with Splunk operational state. Content-derived IDs ignore ZIP filename, entry ordering, container timestamps and one outer directory; identical/repacked CSV bytes are skipped. Semantically similar exports with changed CSV bytes remain separate snapshots. Source duplicates within a snapshot are counted; dashboards deduplicate event IDs. Delivery is recoverable, not claimed to be exactly once.

The spool is immutable and retains published JSON for restart safety; 1.0 does not automatically purge spool, quarantine or checkpoint state. Monitor disk usage and plan retention with the administrator. Do not rename/move monitored spool files: `crcSalt=<SOURCE>` is used only for immutable files with deterministic paths, so different small datasets are identified correctly; moving a monitored file can reingest it. Repeated transport IDs are removed in analytical searches.

The index has a **100-year event-time age limit** and inherits the Enterprise index-size default. Set an explicit size budget (for example `maxTotalDataSizeMB = 5120` for 5 GiB) in the administrator-owned local indexes.conf before a larger deployment. The long age limit preserves historical activity imported today, which otherwise can freeze immediately under a short event-time retention setting. The effective size cap still rolls off older buckets when reached; configure retention/size to your policies in local indexes.conf. Do not use the sample design's earlier 365-day suggestion for long historical exports without understanding that impact. Reconciliation deliberately stops selecting a new snapshot if expected indexed records are missing. Existing ready snapshots can become incomplete after index retention/deletion; Import health exposes count differences. Use Splunk's normal backup/deletion processes for indexed data.

## Troubleshooting

- No heartbeat: verify the scripted input is enabled, bundled Python is 3.9+, and the Splunk account can create the runtime directory. Inspect `_internal` splunkd logs for script errors; worker output reports exception types without raw personal data.
- Waiting: file is still changing or is not a complete ZIP. Corrupt/incomplete archives have a five-minute grace period.
- Failed: Import health shows the reason. Correct the export and drop a new ZIP. Failed exports can be retried after fixing configuration; published successful exports are deliberately skipped.
- Indexing delayed: verify monitor inputs, available disk, `linkedin` access, scheduled-search ownership, `collect` permission, and that the reconciliation job runs. Dashboard time ranges intentionally include historical and future-dated events.
- Empty dashboard: select the configured member; ensure a ready snapshot exists. Missing datasets yield empty panels rather than invented data.
- After an app upgrade: restart Splunk; retain runtime state and local overrides.

Useful commands on the Splunk host (as its service account):

```sh
$SPLUNK_HOME/bin/splunk btool inputs list --app=linkedin_assistant --debug
$SPLUNK_HOME/bin/splunk btool props list --app=linkedin_assistant --debug
$SPLUNK_HOME/bin/splunk btool indexes list linkedin --debug
$SPLUNK_HOME/bin/splunk btool savedsearches list --app=linkedin_assistant --debug
```

## Distributed Enterprise

The defaults target one Enterprise instance. Before distributed deployment, split placement: index definition on indexers, parsing props and a single worker/monitor set on the designated heavy forwarder or ingestion Enterprise instance, dashboards/macros/savedsearches and search-time props on search heads. Disable the worker and monitors on all other nodes. Use a deployment server/cluster manager/deployer according to topology; do not install enabled ingestion copies on each search-head member. A universal forwarder is not the Python worker host. Custom runtime paths require corresponding monitor changes and are outside the default package setup.

## Validation status

The source ships with synthetic unit/integration tests and deterministic packaging. See the repository validation report for exact results. AppInspect is a static validator, not proof of runtime behavior. Version 1.0.2 was exercised in the official splunk/splunk:10.4 container (Enterprise 10.4.4): 9,608 indexed records, 39 reconciled datasets, one automatically scheduled ready event, all 44 panel searches across eight dashboards, and visibly populated Overview and Job search dashboards. The verifier also executes the real latest-snapshot token searches. Earlier releases had only static validation.
