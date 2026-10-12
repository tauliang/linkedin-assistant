"""CSV normalization with source accounting and deterministic identities."""
import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .archive import read_archive
from .schema import (SCHEMAS, EXCLUDED, PRIMARY_DATES, ALIASES, allowed_fields,
                     normalized_headers, resolve_schema, dataset_name)

csv.field_size_limit(2 * 1024 * 1024)
MAX_EVENT_BYTES = 128 * 1024


def utcstamp(value):
    return value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_date(raw, tz_name):
    value = raw.strip()
    # LinkedIn event ranges use their start time. Rich-media dates embed a GMT timestamp.
    if re.match(r'^[A-Z][a-z]{2} \d{1,2}, \d{4} ',value) and ' - ' in value:
        value = value.split(' - ',1)[0]
    rich = re.fullmatch(r'You .+ on ([A-Z][a-z]+ \d{1,2}, \d{4}) at (\d{1,2}:\d{2} [AP]M) \(GMT\)',value)
    if rich: value = rich.group(1)+' '+rich.group(2)+' UTC'
    if not value or value.upper() in ('N/A', 'NULL', 'NONE'):
        return None
    if re.fullmatch(r'\d{4}', value):
        return (value, 'year')
    for fmt in ('%b %Y', '%B %Y', '%m/%Y', '%Y-%m'):
        try: return (datetime.strptime(value, fmt).strftime('%Y-%m'), 'month')
        except ValueError: pass
    # Expand short years explicitly: 00-68 => 2000-2068; 69-99 => 1969-1999.
    match = re.match(r'^(\d{1,2}/\d{1,2}/)(\d{2})(?=[,\s]|$)', value)
    if match:
        yy = int(match.group(2))
        value = match.group(1) + str(2000+yy if yy <= 68 else 1900+yy) + value[match.end():]
    try:
        parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value): precision = 'day'
        else: precision = 'second'
    except ValueError:
        parsed = None
        for fmt, precision in (
            ('%m/%d/%Y, %I:%M %p','minute'), ('%m/%d/%Y %I:%M %p UTC','minute'),
            ('%m/%d/%Y, %I:%M:%S %p','second'), ('%m/%d/%Y %I:%M %p','minute'),
            ('%m/%d/%Y %H:%M:%S','second'), ('%Y-%m-%d %H:%M:%S UTC','second'),
            ('%Y/%m/%d %H:%M:%S','second'), ('%Y/%m/%d %H:%M:%S UTC','second'),
            ('%a %b %d %H:%M:%S UTC %Y','second'), ('%Y-%m-%d %H:%M UTC','minute'),
            ('%b %d, %Y %I:%M %p','minute'), ('%B %d, %Y %I:%M %p UTC','minute'), ('%d %b %Y','day'),
            ('%B %d, %Y','day'), ('%m/%d/%Y','day'), ('%Y/%m/%d','day'),
            ('%Y-%m-%d %H:%M:%S','second'),
        ):
            try:
                parsed = datetime.strptime(value, fmt)
                if 'UTC' in fmt: parsed = parsed.replace(tzinfo=timezone.utc)
                break
            except ValueError: pass
        if parsed is None: return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc if tz_name == 'UTC' else ZoneInfo(tz_name))
    return (utcstamp(parsed), precision)


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def parse_archive(path, member, claimed_time, tz_name='UTC'):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', member):
        raise ValueError('Member ID must contain 1-64 letters, digits, hyphens or underscores')
    if tz_name != 'UTC': ZoneInfo(tz_name)  # Fail before publishing for an invalid configuration.
    entries, content_hash = read_archive(path)
    export_id = hashlib.sha256((member + ':' + content_hash).encode()).hexdigest()
    manifests = {}
    records = []
    issues = []
    seen = set()
    for filename, data in sorted(entries):
        key = resolve_schema(filename)
        dataset = dataset_name(key) if key else 'unknown_' + hashlib.sha256(filename.encode()).hexdigest()[:12]
        if dataset not in manifests:
            manifests[dataset] = dict(dataset=dataset, source_rows=0, expected_records=0,
                duplicate_rows=0, excluded_rows=0, quarantined_rows=0, date_issues=0,
                files=[], original_headers=[])
        manifest = manifests[dataset]
        manifest['files'].append(filename)
        try:
            rows = list(csv.reader(io.StringIO(data.decode('utf-8-sig'), newline=''), strict=True))
        except (UnicodeError, csv.Error):
            raise ValueError('CSV decoding or syntax error in ' + filename)
        if not rows: continue
        offset = 0
        if key == 'Connections.csv':
            candidates = [i for i, row in enumerate(rows[:20]) if 'First Name' in row and 'Connected On' in row]
            if not candidates: raise ValueError('Connections header not found')
            offset = candidates[0]
        headers = rows[offset]
        names = normalized_headers(headers)
        manifest['original_headers'].append({'source_file':filename, 'headers':headers})
        required = set(SCHEMAS[key]) - {''} if key else set()
        # Known schema evolution can add columns, but removing required columns is quarantined.
        schema_valid = bool(key) and (required.issubset(set(headers)) or key in EXCLUDED)
        allowed = allowed_fields(key, headers) if schema_valid and key not in EXCLUDED else set()
        for number, row in enumerate(rows[offset+1:], offset+2):
            if not any(cell.strip() for cell in row): continue
            manifest['source_rows'] += 1
            reason = None
            if key in EXCLUDED:
                manifest['excluded_rows'] += 1
                continue
            if not schema_valid: reason = 'unknown_schema'
            elif len(row) != len(headers): reason = 'column_count'
            if reason:
                manifest['quarantined_rows'] += 1
                issues.append(dict(source_file=filename, source_record=number, reason=reason))
                continue
            fields = {name:cell.strip() for name,cell in zip(names,row) if name in allowed}
            # Source columns cannot overwrite canonical metadata.
            reserved = {'event_time','event_kind','schema_version','member_id','export_id','event_id','dataset','record_hash','time_basis','time_precision','snapshot_time','import_time','source_record','source_file'}
            fields = {('source_'+k if k in reserved else k):v for k,v in fields.items()}
            for source, target in ALIASES.items():
                if source in fields: fields[target] = fields[source]
            # Hash the complete source row in memory so redaction cannot merge distinct rows.
            digest = hashlib.sha256(encode([member,dataset,list(zip(names,(cell.strip() for cell in row)))]).encode()).hexdigest()
            if digest in seen:
                manifest['duplicate_rows'] += 1
                continue
            when, precision, basis, selected = claimed_time, 'snapshot', 'snapshot', ''
            for column in PRIMARY_DATES.get(dataset, []):
                lookup = 'source_event_time' if column == 'event_time' else column
                raw = fields.get(lookup, '')
                date = parse_date(raw,tz_name)
                if date and date[1] not in ('month','year'):
                    when,precision = date
                    basis,selected = 'activity',column
                    break
                if raw and raw.upper() not in ('N/A','NULL','NONE') and not date:
                    manifest['date_issues'] += 1
            for column in ('started_on','finished_on','start_date','end_date','issued_on'):
                if fields.get(column):
                    parsed = parse_date(fields[column],tz_name)
                    fields[column+'_precision'] = parsed[1] if parsed else 'unparsed'
            event = dict(event_time=when, event_kind='record', schema_version=1,
                member_id=member, export_id=export_id, dataset=dataset,
                source_file=filename, source_record=number, record_hash=digest,
                event_id=hashlib.sha256((export_id+digest).encode()).hexdigest(),
                snapshot_time=claimed_time, snapshot_time_basis='import_observed',
                import_time=claimed_time, time_basis=basis, time_precision=precision,
                timezone_assumption=tz_name, selected_date_field=selected)
            event.update(fields)
            if len(encode(event).encode('utf-8')) > MAX_EVENT_BYTES:
                manifest['quarantined_rows'] += 1
                issues.append(dict(source_file=filename, source_record=number, reason='event_size_limit'))
                continue
            seen.add(digest)
            records.append(event)
            manifest['expected_records'] += 1
    return dict(export_id=export_id, member_id=member, records=records,
                manifests=list(manifests.values()), issues=issues, snapshot_time=claimed_time)
