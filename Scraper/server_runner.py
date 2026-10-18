"""Server orchestration: caller-owned organizations, deduplication, and ID allocation."""

import inspect
import logging
import re
import threading
import unicodedata
from datetime import datetime, timezone

if __package__:
    from . import config
    from .event_output import check_output_settings, format_event, positive_id
    from .pipeline import scrape_events
    from .gatorconnect_pipeline import scrape_gatorconnect
    from .gatorconnect_scraper import organization_url
    from .runtime_utils import error_record
else:
    import config
    from event_output import check_output_settings, format_event, positive_id
    from pipeline import scrape_events
    from gatorconnect_pipeline import scrape_gatorconnect
    from gatorconnect_scraper import organization_url
    from runtime_utils import error_record


LOGGER = logging.getLogger(__name__)
RUN_LOCK = threading.Lock()


class ScraperRunError(RuntimeError):
    """A failed/partial run with safe diagnostics and any allocated valid events.

    Persist .events before retrying and include them in the next existing_events
    snapshot. Callback failures cannot roll back IDs already issued externally.
    """

    def __init__(self, message, events, issues):
        super().__init__(message)
        self.events = events
        self.issues = issues


def normalize_title(value):
    """Normalize Unicode, case, and whitespace; deliberately avoid fuzzy matching."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Every event needs a nonempty title for duplicate detection.')
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def duplicate_keys(event):
    """Return organization/time and title/time keys using the same UTC instant."""
    if not isinstance(event, dict) or not positive_id(event.get('organization_id')):
        raise ValueError('Every existing event needs a valid organization_id.')
    instant = event.get('timestamp')
    if isinstance(instant, str):
        instant = datetime.fromisoformat(instant.replace('Z', '+00:00'))

    print("datetime 2")
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('Event timestamps must include a timezone offset or Z.')
    print("datetime 3")
    instant = instant.astimezone(timezone.utc)
    return (event['organization_id'], instant), (normalize_title(event.get('title')), instant)


def select_organizations(source, organizations):
    """Skip missing source links, validate mappings, and preserve caller DB IDs."""
    if not isinstance(organizations, list):
        raise ValueError('organizations must be a list of dictionaries.')
    selected = {}
    for organization in organizations:
        if not isinstance(organization, dict) or not positive_id(organization.get('id')):
            raise ValueError('Each organization needs a positive integer id.')
        value = organization.get('handle' if source == 'instagram' else 'conURL')
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if not isinstance(value, str):
            raise ValueError('Organization handles and conURL values must be text or None.')
        if source == 'instagram':
            key = value.strip().removeprefix('@').casefold()
            if not re.fullmatch(r'[a-z0-9_.]{1,30}', key):
                raise ValueError('Invalid Instagram handle in organizations.')
        else:
            key = organization_url(value.strip().rstrip('/')).casefold()
        if key in selected and selected[key] != organization['id']:
            raise ValueError('The same source organization is assigned to different database IDs.')
        selected[key] = organization['id']
    return selected


def run(source, organizations, existing_events, create_event_id):
    """Validate inputs, collect selected sources, then allocate IDs only to new rows.

    There is no global config replacement, dummy DB lookup, stdout JSON, or
    sys.exit here. The supplied snapshot is authoritative. Cached GatorConnect
    records must be included because a previous CLI run is not proof of a DB save.
    """
    print("running")
    if not isinstance(source, str):
        raise ValueError('source must be instagram or gatorconnect.')
    source = re.sub(r'[\s_-]', '', source.casefold())
    if source not in ('instagram', 'gatorconnect'):
        raise ValueError('source must be instagram or gatorconnect.')
    if not callable(create_event_id) or inspect.iscoroutinefunction(create_event_id):
        raise ValueError('create_event_id must be a synchronous zero-argument callable.')
    if not isinstance(existing_events, list):
        raise ValueError('existing_events must be an Event[] list.')
    print("got through checks")
    selected = select_organizations(source, organizations)
    club_times, title_times, used_ids = set(), set(), set()
    print("1")
    for event in existing_events:
        print("looking at event: ", event)
        club_key, title_key = duplicate_keys(event)
        print("got dipplicates down")
        if not positive_id(event.get('id')):
            raise ValueError('Every existing event needs a valid id.')
        club_times.add(club_key)
        title_times.add(title_key)
        used_ids.add(event['id'])
    print("2")
    if not selected:
        return []  # Never fall back to config organizations when input is empty.
    check_output_settings()
    if not RUN_LOCK.acquire(blocking=False):
        raise RuntimeError('A server scraper run is already active in this process.')
    try:
        return collect_and_allocate(source, selected, club_times, title_times, used_ids, create_event_id)
    finally:
        RUN_LOCK.release()


def collect_and_allocate(source, selected, club_times, title_times, used_ids, create_event_id):
    """Keep all duplicate checks and schema validation ahead of the ID callback."""
    candidates, issues = [], []
    keys = list(selected)
    # Respect the collectors' per-call organization cap without modifying config.
    for offset in range(0, len(keys), config.MAX_CLUBS):
        batch = keys[offset:offset + config.MAX_CLUBS]
        try:
            if source == 'instagram':
                result = scrape_events(batch, progress=False, use_database=False)
            else:
                result = scrape_gatorconnect(organization_urls=batch, include_unchanged=True, progress=False)
        except Exception as error:
            issues.append(error_record(error, 'pipeline'))
            continue
        issues.extend(result.get('errors', []))
        issues.extend(warning for warning in result.get('warnings', []) if warning.get('partial_results'))
        if result.get('deferred_posts'):
            LOGGER.warning('%s event revisions remain deferred for a later run.', result['deferred_posts'])
        for post in result.get('posts', []):
            raw_key = post.get('organization_handle' if source == 'instagram' else 'organization_url')
            key = str(raw_key or '').strip().rstrip('/').casefold()
            if key not in selected:
                issues.append({'stage': 'output', 'message': 'Collector returned an unrequested organization.'})
                continue
            for extracted in post.get('events', []):
                try:
                    candidate = format_event(extracted, post, organization_id=selected[key], defer_id=True)
                    club_key, title_key = duplicate_keys(candidate)
                except (ValueError, TypeError, OverflowError) as error:
                    LOGGER.warning('Skipped incomplete event from %s: %s', post.get('post_url'), error)
                    continue
                duplicate = club_key in club_times or title_key in title_times
                # Remember both associations even for a cross-club repost: later
                # posts by that club at the same instant must also be suppressed.
                club_times.add(club_key)
                title_times.add(title_key)
                if duplicate:
                    continue
                candidates.append(candidate)

    events = []
    for candidate in candidates:
        try:
            event_id = create_event_id()
        except Exception:
            # Do not retry the callback: it might have allocated before failing.
            raise ScraperRunError('Event ID callback failed; no automatic retry.', events,
                                  issues + [{'stage': 'id_allocation', 'message': 'Callback failed.'}]) from None
        if inspect.iscoroutine(event_id):
            event_id.close()  # Do not leave an unawaited coroutine warning behind.
        print(f"\n\n\nUSING EVENTID: {event_id} | used ids: {used_ids}\n\n\n\n")
        if not positive_id(event_id) or event_id in used_ids:
            raise ScraperRunError('Event ID callback returned an invalid or already-used ID.', events,
                                  issues + [{'stage': 'id_allocation', 'message': 'Invalid or reused ID.'}])
        used_ids.add(event_id)
        events.append({'id': event_id, **candidate})
    if issues:
        print(issues)
        raise ScraperRunError('Scraper run was incomplete; inspect issues and persist any events.', events, issues)
    return events
