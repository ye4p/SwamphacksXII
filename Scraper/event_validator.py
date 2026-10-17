"""Validate model output independently; flag uncertainty instead of inventing facts."""

import re
from datetime import date, datetime

if __package__:
    from .config import EVENT_TAGS, MAX_EVENTS
    from .runtime_utils import ScraperError
else:
    from config import EVENT_TAGS, MAX_EVENTS
    from runtime_utils import ScraperError

TEXT_FIELDS = ('title', 'date_text', 'date', 'time', 'location', 'address_text',
               'city_text', 'description', 'supporting_text')


def normalized(text):
    return ' '.join(text.casefold().split())


def validate_extraction(extracted, caption):
    """Retain incomplete events, remove invalid values, and attach review warnings."""
    if (not isinstance(extracted, dict) or not isinstance(extracted.get('image_text'), str)
            or not isinstance(extracted.get('events'), list)
            or len(extracted['events']) > MAX_EVENTS):
        raise ScraperError('validation', 'invalid_structure', 'Gemini returned an invalid extraction structure.')
    source = normalized(caption + '\n' + extracted['image_text'])
    validated = []
    for raw in extracted['events']:
        if not isinstance(raw, dict):
            raise ScraperError('validation', 'invalid_event', 'An event was not a JSON object.')
        event, warnings = {}, []
        for field in TEXT_FIELDS:
            value = raw.get(field)
            if value is not None and not isinstance(value, str):
                warnings.append(f'{field}: expected text or null; value removed.')
                value = None
            event[field] = value.strip() or None if isinstance(value, str) else value
        # Do not allow arbitrary fields from the model into the final output.
        kind = raw.get('location_kind')
        if kind not in ('physical', 'online', 'missing', 'ambiguous'):
            kind = 'missing'
            warnings.append('location_kind: unknown value; lookup disabled.')
        event['location_kind'] = kind
        tags = raw.get('Tags')
        if not isinstance(tags, list):
            tags = []
            warnings.append('Tags: expected a list; using an empty list.')
        if any(not isinstance(tag, str) or tag not in EVENT_TAGS for tag in tags):
            warnings.append('Tags: unsupported labels removed.')
        event['Tags'] = list(dict.fromkeys(tag for tag in tags if isinstance(tag, str) and tag in EVENT_TAGS))

        if event['date']:
            try:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', event['date']):
                    raise ValueError()
                parsed = date.fromisoformat(event['date'])
                if not re.search(rf'\b{parsed.year}\b', source):
                    raise ValueError()
                # Check common written dates against the normalized date. Missing
                # years stay missing; parsing here never fills them in.
                written = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', event['date_text'] or '', flags=re.I)
                written = written.replace(',', '')
                for pattern in ('%B %d %Y', '%b %d %Y', '%Y-%m-%d', '%m/%d/%Y'):
                    try:
                        printed = datetime.strptime(written, pattern).date()
                    except ValueError:
                        continue
                    if printed != parsed:
                        raise ValueError()
                    break
            except ValueError:
                event['date'] = None
                warnings.append('date: invalid, inconsistent, or year absent from source; value removed.')
        # Support clock times and ranges without guessing missing AM/PM or zones.
        if event['time']:
            clocks = re.findall(r'(?<!\d)(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', event['time'], re.I)
            if (not clocks or any(int(hour) > (12 if suffix else 23)
                    or (suffix and int(hour) == 0) or (minute and int(minute) > 59)
                    for hour, minute, suffix in clocks)):
                event['time'] = None
                warnings.append('time: invalid or unsupported time format; value removed.')

        # Venue/address must actually occur in caption/OCR before a paid lookup.
        # OCR is itself model output, so these checks are consistency checks,
        # not independent proof that the flyer or event is authentic.
        for field in ('date_text', 'time', 'location', 'address_text', 'city_text'):
            if event[field] and normalized(event[field]) not in source:
                warnings.append(f'{field}: text not found in caption/OCR; value removed.')
                event[field] = None
        if kind == 'physical' and not (event['location'] or event['address_text']):
            event['location_kind'] = 'missing'
        evidence = event['supporting_text']
        if not evidence or normalized(evidence) not in source:
            warnings.append('supporting_text: exact excerpt could not be verified.')
        for field in ('title', 'date', 'time', 'location'):
            if not event[field]:
                warnings.append(f'{field}: missing or uncertain.')
        event['validation_status'] = 'needs_review' if warnings else 'checked'
        event['validation_warnings'] = warnings
        validated.append(event)
    return {'image_text': extracted['image_text'], 'events': validated}
