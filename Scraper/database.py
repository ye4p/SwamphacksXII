"""Dummy database access for existing events."""

import hashlib


def fetch_event_ids(organization_key, event_key):
    """DUMMY: stand in for fetching existing event/organization IDs from the DB.

    Replace this body with your parameterized database query. It must return
    {'id': <event row ID>, 'organization_id': <organization row ID>}, or None
    when no matching rows exist. The formatter calls it before building a row.

    These deterministic mock numbers make local runs usable without a database;
    they are NOT real database IDs and must not be used for production inserts.
    Real lookup should use stored source associations, not guess a foreign key
    from a GatorConnect organization number or an Instagram username.
    """
    def mock_id(value):
        # Stay in the positive PostgreSQL integer / JavaScript-safe range.
        return int(hashlib.sha256(value.encode('utf-8')).hexdigest()[:8], 16) % (2**31 - 1) + 1

    organization_id = (int(organization_key.split(':', 1)[1]) if organization_key.startswith('database:')
                       else mock_id('organization:' + organization_key))
    return {'id': mock_id('event:' + organization_key + ':' + event_key),
            'organization_id': organization_id}


def fetch_events(start_date):
    """Return event dictionaries from start_date onward (dummy data)."""
    return []
