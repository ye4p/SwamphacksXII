"""Adapt extraction records to the frontend Event interface without changing APIs.

The collector keeps its rich internal records for retries and diagnostics. Only
this final export boundary flattens posts and enforces non-null frontend fields.
No database writes or extra Gemini/Places calls are made by this module.
"""

import math
import re
import unicodedata
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if __package__:
    from . import config
    from .database import fetch_event_ids
else:
    import config
    from database import fetch_event_ids


def positive_id(value):
    """Reject booleans and integers outside JavaScript's exact integer range."""
    return type(value) is int and 0 < value <= 2**53 - 1


def check_output_settings():
    """Fail before paid processing when the export timezone cannot be loaded."""
    try:
        ZoneInfo(config.OUTPUT_TIMEZONE)
        ZoneInfo('America/New_York')
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('Check OUTPUT_TIMEZONE and install timezone data: python -m pip install tzdata') from None


def organization_identity(post, organization_id=None):
    """Identify the organization for the database lookup, not as a foreign key.

    GatorConnect's organization_id belongs to GatorConnect, not our database.
    Never silently treat it as a foreign key in the application's database.
    """
    source = post.get('source_type') or 'instagram'
    key = (post.get('organization_url') if source == 'gatorconnect'
           else post.get('organization_handle'))
    key = str(key or '').strip().rstrip('/').casefold()
    if organization_id is not None:
        if not positive_id(organization_id):
            raise ValueError('Organization ID must be a positive JavaScript-safe integer.')
        return f'database:{organization_id}'
    if not key:
        raise ValueError('No organization identity; saved images require --organization-id.')
    return f'{source}:{key}'


def event_timestamp(event):
    """Combine the event date and explicit start time into a UTC ISO timestamp.

    A range supplies its start time only. Missing AM/PM is not guessed from the
    range's end. UF times default to America/New_York, with DST round-trip checks
    to reject clocks that either never occurred or occurred twice.
    """
    raw_date, raw_time = event.get('date'), event.get('time')
    if not isinstance(raw_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw_date):
        raise ValueError('A complete event date is required.')
    day = date.fromisoformat(raw_date)
    if not isinstance(raw_time, str) or not raw_time.strip():
        raise ValueError('An event start time is required.')
    text = raw_time.strip().upper().replace('A.M.', 'AM').replace('P.M.', 'PM')
    suffix = re.search(r'\s+(UTC|GMT|ET|EST|EDT)$', text)
    zone_label = suffix.group(1) if suffix else None
    if suffix:
        text = text[:suffix.start()].strip()
    if re.search(r'[A-Z]', re.sub(r'AM|PM|\bTO\b', '', text)):
        raise ValueError('Unsupported timezone or start-time text.')
    start = re.split(r'\s*(?:[\-\u2013\u2014]|\bTO\b)\s*', text, maxsplit=1)[0]
    twelve = re.fullmatch(r'(\d{1,2})(?::(\d{2}))?\s*(AM|PM)', start)
    military = re.fullmatch(r'(\d{1,2}):(\d{2})', start)
    if twelve:
        hour, minute = int(twelve[1]), int(twelve[2] or 0)
        if not 1 <= hour <= 12 or minute > 59:
            raise ValueError('Invalid start time.')
        hour = hour % 12 + (12 if twelve[3] == 'PM' else 0)
    elif military and (int(military[1]) == 0 or 13 <= int(military[1]) <= 23):
        # 05:00 without AM/PM is ambiguous in social posts; 17:00 is not.
        hour, minute = int(military[1]), int(military[2])
    else:
        raise ValueError('Start time is ambiguous or uses an unsupported timezone/format.')
    clock = datetime(day.year, day.month, day.day, hour, minute)
    if zone_label in ('UTC', 'GMT'):
        return clock.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
    try:
        zone = ZoneInfo('America/New_York' if zone_label in ('ET', 'EST', 'EDT') else config.OUTPUT_TIMEZONE)
    except ZoneInfoNotFoundError:
        raise ValueError('Timezone data unavailable; install tzdata for timezone conversion.') from None
    instants = set()
    for fold in (0, 1):
        local = clock.replace(tzinfo=zone, fold=fold)
        utc = local.astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) != clock:
            continue  # Spring-forward gap: this local clock time did not occur.
        if zone_label in ('EST', 'EDT') and local.tzname() != zone_label:
            continue
        instants.add(utc)
    if len(instants) != 1:
        raise ValueError('Start time has a conflicting timezone or ambiguous/nonexistent daylight-saving time.')
    return instants.pop().isoformat().replace('+00:00', 'Z')


def format_event(event, post, *, organization_id=None, defer_id=False):
    """Build exactly the requested fields, or explain why export is impossible."""
    organization_key = organization_identity(post, organization_id)
    # Server mode validates all fields without touching the dummy DB or spending
    # an ID. Only after deduplication does the caller request a real event ID.
    if defer_id and not positive_id(organization_id):
        raise ValueError('Deferred-ID formatting requires a valid organization ID.')
    # Preserve an explicit GatorConnect source timestamp/offset rather than
    # reinterpreting an out-of-town event as Gainesville time.
    source_start = (post.get('source_details') or {}).get('starts_on')
    if post.get('source_type') == 'gatorconnect' and source_start:
        start = datetime.fromisoformat(source_start.replace('Z', '+00:00'))
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError('GatorConnect source timestamp has no timezone.')
        timestamp = start.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    else:
        timestamp = event_timestamp(event)
    title, address = event.get('title'), event.get('address')
    if not isinstance(title, str) or not title.strip():
        raise ValueError('An event title is required.')
    if not isinstance(address, str) or not address.strip():
        raise ValueError('A resolved address is required.')
    for field, limit in (('latitude', 90), ('longitude', 180)):
        number = event.get(field)
        if type(number) not in (int, float) or not math.isfinite(number) or not -limit <= number <= limit:
            raise ValueError(f'A valid numeric {field} is required.')
    identity = post.get('post_url') or post.get('source_event_id')
    if not identity:
        raise ValueError('A source identity is required to generate a stable event ID.')
    # Source + title + timestamp distinguishes events in a carousel. Replace the
    # dummy lookup with stored source/event associations when connecting the DB.
    normalized_title = ' '.join(unicodedata.normalize('NFKC', title).casefold().split())
    identifiers = {'organization_id': organization_id}
    if not defer_id:
        try:
            identifiers = fetch_event_ids(organization_key, f'{identity}:{normalized_title}:{timestamp}')
        except Exception:
            # Driver exceptions can contain credentials or SQL. Do not print them.
            raise ValueError('Database ID lookup failed; event not exported.') from None
        if not isinstance(identifiers, dict) or not all(positive_id(identifiers.get(key))
                                                      for key in ('id', 'organization_id')):
            raise ValueError('Database lookup did not return valid event and organization IDs.')
    notes = [f'Source: {identity}', f'Venue: {event.get("location") or address}']
    notes.extend(w for w in event.get('validation_warnings', []) if isinstance(w, str))
    if event.get('location_warning'):
        notes.append(str(event['location_warning']))
    tags = event.get('Tags') or []
    return {
        **({'id': identifiers['id']} if not defer_id else {}),
        'organization_id': identifiers['organization_id'], 'timestamp': timestamp,
        'title': title.strip(), 'description': event.get('description') if isinstance(event.get('description'), str) else '',
        'address': address.strip(), 'longitude': event['longitude'], 'latitude': event['latitude'],
        'payload': {'notes': '\n'.join(dict.fromkeys(notes)),
                    'tags': list(dict.fromkeys(tag for tag in tags if isinstance(tag, str)))},
    }


def format_result(result, *, local_source=None, organization_id=None):
    """Return Event[] plus diagnostics; never put rejected partial rows in Event[]."""
    posts = result.get('posts', [])
    if 'events' in result:
        posts = [dict(local_source or {}, events=result['events'])]
    events, rejected, seen = [], [], {}
    for post in posts:
        for event in post.get('events', []):
            try:
                formatted = format_event(event, post, organization_id=organization_id)
                previous = seen.get(formatted['id'])
                if previous is not None and previous != formatted:
                    raise ValueError('Database returned the same event ID for conflicting records.')
                if previous is None:
                    events.append(formatted)
                    seen[formatted['id']] = formatted
            except (ValueError, TypeError, OverflowError) as error:
                # Keep source facts available on stderr for review/retry. Missing
                # coordinates never become fake 0,0 points just to satisfy types.
                rejected.append({'stage': 'output', 'message': str(error),
                                 'post_url': post.get('post_url'), 'event': event})
    diagnostics = {key: value for key, value in result.items() if key not in ('posts', 'events', 'image_text')}
    diagnostics['rejected_events'] = rejected
    diagnostics['exported_events'] = len(events)
    return events, diagnostics
