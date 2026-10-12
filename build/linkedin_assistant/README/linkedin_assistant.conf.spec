# LinkedIn Assistant inbox settings. Override in local/linkedin_assistant.conf.
[settings]
member_id = <string>
# 1-64 letters, numbers, underscore or hyphen. One member per inbox. Default personal.
timezone = <string>
# IANA timezone used for timezone-free activity dates. Default UTC.
copy_grace_seconds = <integer>
# Grace period for incomplete ZIP copies. Default 300 seconds.
archive_retention_days = <integer>
# Delete processed/failed raw ZIPs older than this many days. 0 disables cleanup. Default 30.
