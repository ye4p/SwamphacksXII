"""Server integration checks without network requests, paid calls, or real DB writes."""

from copy import deepcopy
from io import StringIO
import os
from contextlib import redirect_stdout
import unittest
from unittest.mock import Mock, patch

from Scraper.main import run_scraper
from Scraper import server_runner as runner, config
from Scraper.event_output import format_event
from test_event_output import event


ORGS = [{'id': 7, 'name': 'ACM', 'handle': '@UF.ACM', 'conURL': ''},
        {'id': 8, 'name': 'Other', 'handle': 'other.club', 'conURL': None}]


def collected(*items):
    return {'posts': list(items), 'errors': []}


def post(handle='uf.acm', *events):
    return {'organization_handle': handle, 'post_url': 'https://www.instagram.com/p/' + handle,
            'events': list(events or [event()])}


def existing(**changes):
    result = {'id': 1, **format_event(event(), post(), organization_id=7, defer_id=True)}
    result.update(changes)
    return result


class ServerRunnerTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(runner, 'scrape_events', return_value=collected(post()))
        self.scrape = patcher.start()
        self.addCleanup(patcher.stop)
        dummy = patch('Scraper.event_output.fetch_event_ids', side_effect=AssertionError('Dummy DB must not run'))
        dummy.start()
        self.addCleanup(dummy.stop)

    def test_importable_wrapper_returns_schema_and_real_ids_without_stdout(self):
        allocate = Mock(return_value=42)
        original = deepcopy(ORGS)
        before_config = list(config.CLUB_HANDLES)
        output = StringIO()
        with redirect_stdout(output):
            result = run_scraper('instagram', ORGS, [], allocate)
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(result[0]['organization_id'], 7)
        self.assertEqual(result[0]['id'], 42)
        self.assertEqual(set(result[0]), set(existing()))
        allocate.assert_called_once_with()
        self.scrape.assert_called_once_with(['uf.acm', 'other.club'], progress=False, use_database=False)
        self.assertEqual(ORGS, original)
        self.assertEqual(config.CLUB_HANDLES, before_config)

    def test_same_club_same_instant_different_title_uses_no_id(self):
        allocate = Mock()
        saved = existing(title='Earlier title', timestamp='2026-10-21T17:00:00-04:00')
        self.assertEqual(run_scraper('instagram', ORGS, [saved], allocate), [])
        allocate.assert_not_called()

    def test_cross_club_unicode_title_and_exact_time_match(self):
        allocate = Mock()
        saved = existing(organization_id=99, title=' ＷＯＲＫＳＨＯＰ  ')
        self.assertEqual(run_scraper('instagram', ORGS, [saved], allocate), [])
        allocate.assert_not_called()

    def test_same_club_different_start_times_and_dates_are_new(self):
        self.scrape.return_value = collected(post('uf.acm', event(time='6 PM'), event(date='2026-10-22')))
        allocate = Mock(side_effect=[42, 43])
        result = run_scraper('instagram', ORGS, [existing()], allocate)
        self.assertEqual([item['id'] for item in result], [42, 43])

    def test_different_clubs_different_titles_same_time_are_distinct(self):
        self.scrape.return_value = collected(post('uf.acm'), post('other.club', event(title='Social')))
        self.assertEqual(len(run_scraper('instagram', ORGS, [], Mock(side_effect=[42, 43]))), 2)

    def test_cross_club_and_within_run_duplicates_allocate_once(self):
        self.scrape.return_value = collected(post('uf.acm'), post('other.club'),
                                             post('other.club', event(title='Changed title')))
        allocate = Mock(return_value=42)
        self.assertEqual(len(run_scraper('instagram', ORGS, [], allocate)), 1)
        allocate.assert_called_once()

    def test_next_periodic_run_uses_saved_results_without_allocating(self):
        first = run_scraper('instagram', ORGS, [], Mock(return_value=42))
        allocate = Mock()
        self.assertEqual(run_scraper('instagram', ORGS, first, allocate), [])
        allocate.assert_not_called()

    def test_missing_links_skip_without_falling_back_to_config(self):
        for organizations in ([], [{'id': 7, 'handle': None}], [{'id': 7, 'handle': '  '}]):
            self.assertEqual(run_scraper('instagram', organizations, [], Mock()), [])
        self.scrape.assert_not_called()

    def test_bad_input_fails_before_collection(self):
        for source, organizations, saved in [('bad', ORGS, []),
                 ('instagram', [{'id': True, 'handle': 'uf.acm'}], []),
                 ('instagram', [{'id': 7, 'handle': 'uf.acm'}, {'id': 8, 'handle': 'uf.acm'}], []),
                 ('instagram', ORGS, [existing(timestamp='2026-10-21T17:00:00')])]:
            with self.subTest(source=source, organizations=organizations), self.assertRaises(ValueError):
                run_scraper(source, organizations, saved, Mock())
        self.scrape.assert_not_called()

    def test_incomplete_and_non_event_records_do_not_allocate(self):
        self.scrape.return_value = collected(post('uf.acm', event(latitude=None)))
        allocate = Mock()
        with self.assertLogs(runner.LOGGER, level='WARNING'):
            self.assertEqual(run_scraper('instagram', ORGS, [], allocate), [])
        self.scrape.return_value = collected()
        self.assertEqual(run_scraper('instagram', ORGS, [], allocate), [])
        allocate.assert_not_called()

    @patch.object(runner, 'scrape_gatorconnect')
    def test_gatorconnect_custom_urls_cached_results_and_database_org_id(self, scrape):
        url = 'https://gatorconnect.ufl.edu/organization/asme'
        item = {**post(), 'source_type': 'gatorconnect', 'organization_url': url,
                'organization_id': 99999, 'source_event_id': '123',
                'source_details': {'starts_on': '2026-10-21T17:00:00-04:00'}}
        scrape.return_value = collected(item)
        result = run_scraper('gator connect', [{'id': 17, 'handle': None, 'conURL': url + '/'}],
                             [], Mock(return_value=42))
        self.assertEqual(result[0]['organization_id'], 17)
        scrape.assert_called_once_with(organization_urls=[url], include_unchanged=True, progress=False)
        self.scrape.assert_not_called()

    def test_orgs_batched_without_global_config_changes(self):
        organizations = [{'id': n + 1, 'handle': f'club{n}'} for n in range(config.MAX_CLUBS + 1)]
        self.scrape.return_value = collected()
        run_scraper('instagram', organizations, [], Mock())
        self.assertEqual([len(call.args[0]) for call in self.scrape.call_args_list], [config.MAX_CLUBS, 1])

    def test_callback_failure_preserves_already_allocated_events_and_never_retries(self):
        self.scrape.return_value = collected(post('uf.acm', event(), event(time='6 PM')))
        allocate = Mock(side_effect=[42, RuntimeError('password')])
        with self.assertRaises(runner.ScraperRunError) as failure:
            run_scraper('instagram', ORGS, [], allocate)
        self.assertEqual([item['id'] for item in failure.exception.events], [42])
        self.assertNotIn('password', str(failure.exception))
        self.assertEqual(allocate.call_count, 2)

    def test_callback_invalid_or_existing_id_rejected(self):
        for value in (True, None, 0, 1, 2**53):
            with self.subTest(value=value), self.assertRaises(runner.ScraperRunError):
                run_scraper('instagram', ORGS, [existing(organization_id=99, title='Different')],
                            Mock(return_value=value))

    def test_partial_service_failure_exposes_valid_events_and_issues(self):
        self.scrape.return_value = {**collected(post()), 'errors': [{'stage': 'collection', 'code': 'timeout'}]}
        with self.assertRaises(runner.ScraperRunError) as failure:
            run_scraper('instagram', ORGS, [], Mock(return_value=42))
        self.assertEqual(failure.exception.events[0]['id'], 42)
        self.assertEqual(failure.exception.issues[0]['code'], 'timeout')

    def test_active_run_lock_prevents_overlapping_callbacks(self):
        runner.RUN_LOCK.acquire()
        try:
            with self.assertRaises(RuntimeError):
                run_scraper('instagram', ORGS, [], Mock())
        finally:
            runner.RUN_LOCK.release()
        self.scrape.assert_not_called()

    def test_async_id_callback_rejected_before_collection(self):
        async def allocate():
            return 42
        with self.assertRaises(ValueError):
            run_scraper('instagram', ORGS, [], allocate)
        self.scrape.assert_not_called()

    def test_repeated_callback_id_stops_without_retry(self):
        self.scrape.return_value = collected(post('uf.acm', event(), event(time='6 PM')))
        allocate = Mock(return_value=42)
        with self.assertRaises(runner.ScraperRunError) as failure:
            run_scraper('instagram', ORGS, [], allocate)
        self.assertEqual(len(failure.exception.events), 1)
        self.assertEqual(allocate.call_count, 2)

    @patch.dict(os.environ, {'GEMINI_API_KEY': 'mock-key', 'OCR_SPACE_API_KEY': 'mock-ocr'})
    def test_instagram_pipeline_forwards_handles_and_bypasses_legacy_database(self):
        from Scraper import pipeline
        with patch.object(pipeline, 'collect_posts', return_value=collected(post())) as collect, \
                patch.object(pipeline, 'process_post', side_effect=lambda item: item), \
                patch.object(pipeline, 'fetch_events', side_effect=AssertionError('Legacy DB must not run')):
            output = StringIO()
            with redirect_stdout(output):
                result = pipeline.scrape_events(['selected.club'], progress=False, use_database=False)
        collect.assert_called_once_with(['selected.club'], progress=False)
        self.assertEqual(len(result['posts']), 1)
        self.assertEqual(output.getvalue(), '')

    def test_gatorconnect_pipeline_forwards_organization_urls(self):
        from Scraper import gatorconnect_pipeline as pipeline
        url = 'https://gatorconnect.ufl.edu/organization/asme'
        with patch.object(pipeline, 'GatorConnectState'), \
                patch.object(pipeline, 'PlacesResolver'), \
                patch.object(pipeline, 'collect_gatorconnect', return_value=collected()) as collect:
            result = pipeline.scrape_gatorconnect(organization_urls=[url], progress=False, include_unchanged=True)
        collect.assert_called_once_with([url], progress=False)
        self.assertEqual(result['posts'], [])


if __name__ == '__main__':
    unittest.main()
