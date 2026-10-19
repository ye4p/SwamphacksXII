import unittest
from unittest.mock import Mock

from Scraper.gatorconnect_feed import collect_events, parse_event, geocode_events


def record(identity='1', **changes):
    return dict(id=identity, name='A &amp; B', description='<p>Hello</p>',
                startsOn='2026-10-18T20:00:00Z', visibility='Public',
                status='Approved', **changes)


def session_for(*pages):
    session = Mock()
    session.get.side_effect = [Mock(json=Mock(return_value=p)) for p in pages]
    return session


class FeedTests(unittest.TestCase):
    def test_server_capped_pages_and_duplicate_boundary(self):
        session = session_for(
            {'@odata.count': 3, 'value': [record()]},
            {'@odata.count': 3, 'value': [record(), record('2')]},
            {'@odata.count': 3, 'value': [record('3')]})
        self.assertEqual(len(collect_events(session=session, pause=0)), 3)
        self.assertEqual([c.kwargs['params']['skip'] for c in session.get.call_args_list], [0, 1, 3])

    def test_stalled_and_changed_listing_fail(self):
        for second in ({'@odata.count': 2, 'value': [record()]},
                       {'@odata.count': 3, 'value': [record('2')]}):
            session = session_for({'@odata.count': 2, 'value': [record()]}, second)
            with self.assertRaises(ValueError):
                collect_events(session=session, pause=0)

    def test_empty_feed(self):
        self.assertEqual(collect_events(session=session_for({'@odata.count': 0, 'value': []})), [])

    def test_html_time_coordinates_and_tags(self):
        event = parse_event(record(longitude=-82.3, latitude=29.6, benefitNames=['Free Food']))
        self.assertEqual(event['title'], 'A & B')
        self.assertEqual(event['description'], 'Hello')
        self.assertEqual(event['timestamp'], '2026-10-18T20:00:00+00:00')
        self.assertEqual(event['payload']['tags'], ['food included'])
        self.assertIsNone(parse_event(record(latitude=29.6))['latitude'])
        self.assertIsNone(parse_event(record(latitude=999, longitude=0))['longitude'])

    def test_restricted_events_are_not_imported(self):
        private = record('2')
        private['visibility'] = 'Authenticated'
        session = session_for({'@odata.count': 2, 'value': [record(), private]})
        self.assertEqual(len(collect_events(session=session)), 1)

    def test_bad_date_rejected(self):
        row = record()
        row['startsOn'] = '2026-10-18T20:00:00'
        with self.assertRaises(ValueError):
            parse_event(row)


class DatabaseImportTests(unittest.IsolatedAsyncioTestCase):
    async def test_insert_then_update_use_source_identity_and_database_ids(self):
        from unittest.mock import AsyncMock, MagicMock
        from backend.core.tigerdata import TigerData
        conn = MagicMock()
        conn.execute = AsyncMock()
        conn.executemany = AsyncMock()
        conn.fetch = AsyncMock(side_effect=[
            [{'id': 7, 'name': 'Club'}], [],
            [{'id': 7, 'name': 'Club'}], [{'id': 42, 'payload': {'source': 'gatorconnect', 'source_event_id': '1'}}]])
        conn.transaction.return_value.__aenter__ = AsyncMock()
        conn.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
        db = TigerData(dsn='unused')
        db.pool = MagicMock()
        db.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        db.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        event = parse_event(record(organizationName='Club', latitude=29.6, longitude=-82.3))
        self.assertEqual(await db.import_gatorconnect_events([event]), 1)
        self.assertEqual(await db.import_gatorconnect_events([event]), 1)
        statements = conn.executemany.call_args_list
        self.assertIn('INSERT INTO events', statements[1].args[0])
        self.assertIn('UPDATE events', statements[5].args[0])
        self.assertEqual(statements[5].args[1][0][-1], 42)
        self.assertEqual(statements[1].args[1][0][5:7], (-82.3, 29.6))

    async def test_invalid_coordinates_rejected_before_database_access(self):
        from backend.core.tigerdata import TigerData
        db = TigerData(dsn='unused')
        for lon, lat in [(None, 29), (-82, None), (True, 29), (float('nan'), 29), (0, 91)]:
            event = parse_event(record())
            event.update(longitude=lon, latitude=lat)
            with self.assertRaises(ValueError):
                await db.import_gatorconnect_events([event])
            with self.assertRaises(ValueError):
                await db.add_event('2026-10-18T12:00:00Z', 'Test', '', '', lon, lat)


class GeocodingTests(unittest.TestCase):
    def test_geocodes_repeated_venues_once_and_skips_unresolved(self):
        events = [parse_event(record(str(i), location=venue))
                  for i, venue in enumerate(['Little Hall', 'Little Hall', 'TBD'])]
        resolver = Mock()
        resolver.resolve.side_effect = [
            {'location_status': 'resolved', 'latitude': 29.6, 'longitude': -82.3,
             'address': 'Verified address', 'location_provider': 'google_places'},
            {'location_status': 'missing'}]
        result = geocode_events(events, resolver=resolver, progress=False)
        self.assertEqual(len(result['events']), 2)
        self.assertEqual(len(result['skipped']), 1)
        self.assertEqual(resolver.resolve.call_count, 2)
        self.assertEqual(result['events'][0]['payload']['source_venue'], 'Little Hall')
        self.assertIsNone(events[0]['latitude'])  # Input remains unchanged.

    def test_rejects_ambiguous_or_invalid_provider_coordinates(self):
        for status, lat, lon in [('ambiguous', 29, -82), ('resolved', None, -82),
                                  ('resolved', float('inf'), -82), ('resolved', 29, True)]:
            resolver = Mock()
            resolver.resolve.return_value = dict(location_status=status, latitude=lat, longitude=lon)
            result = geocode_events([parse_event(record(location='Somewhere'))],
                                    resolver=resolver, progress=False)
            self.assertEqual(result['events'], [])
            self.assertEqual(len(result['skipped']), 1)

    def test_valid_source_coordinates_need_no_lookup(self):
        resolver = Mock()
        result = geocode_events([parse_event(record(latitude=29.6, longitude=-82.3))],
                                resolver=resolver, progress=False)
        self.assertEqual(len(result['events']), 1)
        resolver.resolve.assert_not_called()


if __name__ == '__main__':
    unittest.main()
