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


def current_year():
    """Use the computer/server's current calendar year, never the post year."""
    return date.today().year


def written_date(text):
    """Remove weekday and ordinal decorations before deterministic date parsing."""
    text = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', text or '', flags=re.I)
    text = text.replace(',', '').strip()
    return re.sub(r'^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|'
                  r'Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)\.?\s+', '', text, flags=re.I)


def is_generic_promotion(event, source):
    """Catch activity catalogs without discarding genuine undated announcements.

    This narrow fallback handles the observed ACM promotion even if Gemini
    misclassifies it. A generic title alone, or missing dates alone, is not enough.
    Do not apply this Instagram heuristic to an approved GatorConnect page.
    """
    generic_titles = {'technical workshops', 'design team projects', 'resume reviews',
                      'interview prep', 'industry networking'}
    evidence = normalized(event.get('supporting_text') or '')
    return (normalized(event.get('title') or '') in generic_titles
            and not any(event.get(key) for key in ('date_text', 'date', 'time', 'location', 'address_text'))
            and bool(evidence) and evidence in source
            and bool(re.search(r'\b(?:host|organize|provide|offer)\b', evidence))
            and not re.search(r'\b(?:join|register|rsvp|next|first|upcoming|tba|tbd)\b', evidence))


def fill_missing_year(event, source, warnings):
    """Fill only a supported month/day when the source mentions no year.

    Never repair a conflicting explicit year or guess a month/day from 'fall'.
    February 29 in a non-leap year remains unresolved. Inference is marked so
    consumers can distinguish this policy from a date actually printed on a flyer.
    """
    event['date_year_inferred'] = False
    if event['date'] or not event['date_text'] or re.search(r'\b(?:19|20|21)\d{2}\b', source):
        return
    written = written_date(event['date_text'])
    for pattern in ('%B %d', '%b %d', '%m/%d'):
        try:
            parsed = datetime.strptime(f'{written} {current_year()}', pattern + ' %Y').date()
        except ValueError:
            continue
        event['date'] = parsed.isoformat()
        event['date_year_inferred'] = True
        warnings.append(f'date: year not stated; assumed current year {parsed.year}.')
        return


def validate_extraction(extracted, caption, *, source_type="instagram"):
    """Retain incomplete events, remove invalid values, and attach review warnings."""
    if (not isinstance(extracted, dict) or not isinstance(extracted.get('image_text'), str)
            or not isinstance(extracted.get('events'), list)
            or len(extracted['events']) > MAX_EVENTS):
        raise ScraperError('validation', 'invalid_structure', 'Gemini returned an invalid extraction structure.')
    if source_type == 'gatorconnect' and len(extracted['events']) > 1:
        # Reject before caching: one detail page must not turn recommendations
        # into extra events, and a failed extraction must be retryable later.
        raise ScraperError('validation', 'multiple_page_events',
                           'One GatorConnect detail page produced multiple events; review required.')
    source = normalized(caption + '\n' + extracted['image_text'])
    # Keep evidence sources separate. Joining the end of a caption to the start
    # of OCR must not accidentally pass as one verbatim supporting excerpt.
    evidence_sources = (normalized(caption), normalized(extracted['image_text']))
    validated = []
    for raw in extracted['events']:
        if not isinstance(raw, dict):
            raise ScraperError('validation', 'invalid_event', 'An event was not a JSON object.')
        # Gemini's classification is an additional guard, not proof of an event.
        # Old cached/structured source records can lack this new schema field.
        if raw.get('announcement_type') in ('general_promotion', 'recap'):
            continue
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
                # Validate explicit dates first; the current-year fallback runs
                # only after the printed month/day is checked against the source.
                written = written_date(event['date_text'])
                for pattern in ('%B %d %Y', '%b %d %Y', '%Y-%m-%d', '%m/%d/%Y'):
                    try:
                        printed = datetime.strptime(written, pattern).date()
                    except ValueError:
                        continue
                    if printed != parsed:
                        raise ValueError()
                    break
                # When Gemini used a clearly printed flyer-header year, still
                # check the month/day against the event's own date text. The
                # leap year 2000 lets Feb 29 parse; no year is filled into output.
                for pattern in ('%B %d', '%b %d', '%m/%d'):
                    try:
                        printed = datetime.strptime(written + ' 2000', pattern + ' %Y').date()
                    except ValueError:
                        continue
                    if (printed.month, printed.day) != (parsed.month, parsed.day):
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
        if not evidence or not any(normalized(evidence) in text for text in evidence_sources):
            warnings.append('supporting_text: exact excerpt could not be verified.')
        if source_type == 'instagram' and is_generic_promotion(event, source):
            continue
        fill_missing_year(event, source, warnings)
        for field in ('title', 'date', 'time', 'location'):
            if not event[field]:
                warnings.append(f'{field}: missing or uncertain.')
        if source_type == 'gatorconnect':
            # Expanded names are search candidates, not source-verified facts.
            # In contrast, a proposed address must occur in the source text.
            for field in ('venue', 'full_address'):
                value = raw.get(field)
                if value is not None and not isinstance(value, str):
                    warnings.append(f'{field}: expected text or null; value removed.')
                    value = None
                event[field] = value.strip() or None if isinstance(value, str) else None
            if event['full_address'] and normalized(event['full_address']) not in source:
                event['full_address'] = None
                warnings.append('full_address: not found in source; value removed.')
            if event['location_kind'] != 'physical' or not event['location']:
                event['venue'] = None
            elif event['venue'] and normalized(event['venue']) not in source:
                warnings.append('venue: model-expanded lookup candidate; requires location verification.')
        event['validation_status'] = 'needs_review' if warnings else 'checked'
        event['validation_warnings'] = warnings
        validated.append(event)
    return {'image_text': extracted['image_text'], 'events': validated}
