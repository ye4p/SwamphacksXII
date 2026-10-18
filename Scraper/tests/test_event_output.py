"""Verify the frontend contract using local records and mocked database lookups."""

from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
import unittest
from unittest.mock import patch

from Scraper import event_output, main


def event(**changes):
    record = {'title': 'Workshop', 'date': '2026-10-21', 'time': '5:00 PM',
              'description': None, 'address': '1885 Stadium Rd, Gainesville, FL',
              'latitude': 29.647, 'longitude': -82.347, 'location': 'Weimer Hall 1064',
              'Tags': ['professional'], 'validation_warnings': ['date: year inferred.']}
    record.update(changes)
    return record


def post(*events):
    return {'organization_handle': 'uf.acm', 'post_url': 'https://www.instagram.com/p/example/',
            'events': list(events)}


class EventOutputTests(unittest.TestCase):
    @patch('Scraper.event_output.fetch_event_ids', return_value={'id': 42, 'organization_id': 7})
    def test_exact_schema_and_database_ids(self, lookup):
        result = event_output.format_event(event(), post())
        self.assertEqual(set(result), {'id', 'organization_id', 'timestamp', 'title',
                                      'description', 'address', 'longitude', 'latitude', 'payload'})
        self.assertEqual(result['id'], 42)
        self.assertEqual(result['organization_id'], 7)
        self.assertEqual(result['timestamp'], '2026-10-21T21:00:00Z')
        self.assertEqual(result['description'], '')
        self.assertEqual(set(result['payload']), {'notes', 'tags'})
        self.assertEqual(result['payload']['tags'], ['professional'])
        self.assertIn('Weimer Hall 1064', result['payload']['notes'])
        self.assertIn('year inferred', result['payload']['notes'])
        self.assertEqual(lookup.call_args.args[0], 'instagram:uf.acm')

    def test_winter_summer_and_range_start(self):
        for day, clock, expected in [('2026-01-21', '5:00 PM', '22:00:00Z'),
                                     ('2026-10-21', '5:00 PM - 6:00 PM', '21:00:00Z'),
                                     ('2026-10-21', '17:00', '21:00:00Z'),
                                     ('2026-10-21', '5:00 PM UTC', '17:00:00Z')]:
            with self.subTest(day=day, clock=clock):
                self.assertTrue(event_output.event_timestamp(event(date=day, time=clock)).endswith(expected))

    def test_missing_invalid_ambiguous_times_and_dst_rejected(self):
        for day, clock in [('2026-10-21', None), ('2026-10-21', '5-6 PM'),
                           ('2026-10-21', '5:00'), ('2026-10-21', '5 PM - 6 PM PST'),
                           ('2026-10-21', '25:00'), ('2026-02-30', '5 PM'),
                           ('2026-03-08', '2:30 AM'), ('2026-11-01', '1:30 AM')]:
            with self.subTest(day=day, clock=clock), self.assertRaises(ValueError):
                event_output.event_timestamp(event(date=day, time=clock))

    def test_dst_fold_disambiguated_by_explicit_zone(self):
        self.assertEqual(event_output.event_timestamp(event(date='2026-11-01', time='1:30 AM EST')),
                         '2026-11-01T06:30:00Z')

    def test_gatorconnect_source_offset_preserved(self):
        source = {'source_type': 'gatorconnect', 'organization_url': 'https://gatorconnect.ufl.edu/organization/asme',
                  'post_url': 'https://gatorconnect.ufl.edu/event/12',
                  'source_details': {'starts_on': '2026-10-21T17:00:00-07:00'}}
        result = event_output.format_event(event(), source)
        self.assertEqual(result['timestamp'], '2026-10-22T00:00:00Z')

    def test_incomplete_event_rejected_without_fabricating_coordinates(self):
        output, diagnostics = event_output.format_result({'posts': [post(event(latitude=None), event(title='Valid'))]})
        self.assertEqual(len(output), 1)
        self.assertEqual(len(diagnostics['rejected_events']), 1)
        self.assertIsNone(diagnostics['rejected_events'][0]['event']['latitude'])

    def test_nonfinite_coordinates_and_missing_address_rejected(self):
        for changes in ({'longitude': float('nan')}, {'latitude': True}, {'latitude': 91}, {'address': None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                event_output.format_event(event(**changes), post())

    def test_dummy_database_is_deterministic_and_carousel_ids_differ(self):
        first = event_output.format_event(event(), post())
        self.assertEqual(first, event_output.format_event(event(), post()))
        second = event_output.format_event(event(title='Second event'), post())
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(first['organization_id'], second['organization_id'])

    @patch('Scraper.event_output.fetch_event_ids', return_value=None)
    def test_database_missing_row_does_not_generate_replacement_id(self, lookup):
        output, diagnostics = event_output.format_result({'posts': [post(event())]})
        self.assertEqual(output, [])
        self.assertIn('Database lookup', diagnostics['rejected_events'][0]['message'])

    @patch('Scraper.event_output.fetch_event_ids', side_effect=RuntimeError('secret-password'))
    def test_database_errors_do_not_expose_credentials(self, lookup):
        output, diagnostics = event_output.format_result({'posts': [post(event())]})
        self.assertEqual(output, [])
        self.assertNotIn('secret-password', json.dumps(diagnostics))

    def test_saved_image_organization_id(self):
        result = event_output.format_event(event(), {'post_url': 'C:/flyer.jpg'}, organization_id=12)
        self.assertEqual(result['organization_id'], 12)

    @patch('Scraper.event_output.fetch_event_ids', return_value={'id': 42, 'organization_id': 7})
    def test_conflicting_database_id_does_not_silently_discard_event(self, lookup):
        output, diagnostics = event_output.format_result({'posts': [post(event(), event(title='Different'))]})
        self.assertEqual(len(output), 1)
        self.assertEqual(len(diagnostics['rejected_events']), 1)

    @patch('Scraper.main.scrape_events')
    def test_cli_stdout_is_event_array_and_diagnostics_are_stderr(self, scrape):
        scrape.return_value = {'posts': [post(event())], 'errors': [], 'processed_posts': 1}
        stdout, stderr = StringIO(), StringIO()
        with patch('sys.argv', ['main.py']), redirect_stdout(stdout), redirect_stderr(stderr):
            main.main()
        self.assertIsInstance(json.loads(stdout.getvalue()), list)
        self.assertEqual(json.loads(stderr.getvalue())['exported_events'], 1)

    @patch('Scraper.main.scrape_events')
    def test_cli_raw_output_keeps_debug_envelope(self, scrape):
        scrape.return_value = {'posts': [], 'errors': [], 'processed_posts': 0}
        stdout = StringIO()
        with patch('sys.argv', ['main.py', '--raw-output']), redirect_stdout(stdout):
            main.main()
        self.assertEqual(json.loads(stdout.getvalue()), scrape.return_value)

    @patch('Scraper.main.check_output_settings', side_effect=ValueError('Install tzdata'))
    @patch('Scraper.main.scrape_events')
    def test_missing_timezone_stops_before_paid_processing(self, scrape, settings):
        stdout, stderr = StringIO(), StringIO()
        with patch('sys.argv', ['main.py']), redirect_stdout(stdout), redirect_stderr(stderr), \
                self.assertRaises(SystemExit) as stopped:
            main.main()
        self.assertEqual(stopped.exception.code, 1)
        self.assertEqual(json.loads(stdout.getvalue()), [])
        scrape.assert_not_called()


if __name__ == '__main__':
    unittest.main()
