"""Explicit supported export schemas and privacy projection."""
import json
import re
from pathlib import Path

SCHEMAS = json.loads(Path(__file__).with_name('schemas.json').read_text(encoding='utf-8'))
EXCLUDED = {
    'Email Addresses.csv', 'PhoneNumbers.csv', 'Private_identity_asset.csv',
    'Verifications/Verifications.csv', 'Job Applicant Saved Screening Question Responses.csv',
    'Jobs/Job Applicant Saved Answers.csv', 'Jobs/Job Seeker Preferences.csv',
    'Profile Summary.csv', 'Notes.csv', 'SavedJobAlerts.csv',
    'Services Marketplace/Engagements.csv', 'Services Marketplace/Opprtunities.csv',
}
NAMES = {
    'Connections.csv': 'connection', 'Invitations.csv': 'invitation',
    'Jobs/Job Applications.csv': 'job_application', 'Jobs/Saved Jobs.csv': 'saved_job',
    'Learning.csv': 'learning', 'Endorsement_Given_Info.csv': 'endorsement_given',
    'Endorsement_Received_Info.csv': 'endorsement_received', 'Company Follows.csv': 'company_follow',
    'Positions.csv': 'position', 'Skills.csv': 'skill', 'Profile.csv': 'profile',
}
# Only known header fields survive. Narrative fields and contact/identity data
# are excluded even inside otherwise supported datasets.
BLOCKED = re.compile(r'(^text$|^activities$|^column_\d+$|email|phone|birth|address|zip_code|postal|registration_ip|invoice|license|summary|description|notes?|message|question|answer|raw_text|twitter|instant_messenger|buyer_groups|member_age|member_gender|profile_locations|websites)', re.I)
PRIMARY_DATES = {
    'connection': ['connected_on'], 'invitation': ['sent_at'],
    'job_application': ['application_date'], 'saved_job': ['saved_date'],
    'learning': ['content_completed_at_if_completed', 'content_last_watched_date_if_viewed'],
    'endorsement_given': ['endorsement_date'], 'endorsement_received': ['endorsement_date'],
    'company_follow': ['followed_on'], 'events': ['event_time'],
    'recommendations_given': ['creation_date'], 'recommendations_received': ['creation_date'],
    'rich_media': ['date_time'], 'registration': ['registered_at'],
    'receipts_v2': ['transaction_made_at'],
}
ALIASES = {'company_name':'company', 'position':'job_title', 'skill_name':'skill',
           'content_title':'content_title', 'job_url':'job_url'}


def snake(text):
    return re.sub(r'[^a-z0-9]+', '_', text.strip().lower()).strip('_')


def normalized_headers(headers):
    used = set()
    output = []
    for index, value in enumerate(headers, 1):
        base = snake(value) or 'column_' + str(index)
        name = base
        suffix = 2
        while name in used:
            name = base + '_' + str(suffix)
            suffix += 1
        used.add(name)
        output.append(name)
    return output


def resolve_schema(path):
    key = re.sub(r'_\d+(?=\.csv$)', '', path)
    return key if key in SCHEMAS else None


def dataset_name(key):
    return NAMES.get(key, snake(Path(key).stem))


def allowed_fields(key, headers):
    known = set(normalized_headers(SCHEMAS[key]))
    return {name for name in normalized_headers(headers) if name in known and not BLOCKED.search(name)}
