"""Regression scenarios for persistent progress and graceful provider failures."""

from copy import deepcopy
from datetime import datetime, timezone
from email.utils import format_datetime
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from Scraper import config, gatorconnect_pipeline as pipeline, gatorconnect_scraper as collector
from Scraper.gatorconnect_state import GatorConnectState
from Scraper.geocode_resolver import GeocodeResolver
from Scraper.runtime_utils import ScraperError
from test_gatorconnect import NOW, PLACE, event, listing, post, response


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.environment = patch.dict(os.environ, {"GATORCONNECT_STATE_DIR": self.folder.name})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.clock = patch("Scraper.gatorconnect_pipeline.time.time", return_value=1000).start()
        self.addCleanup(patch.stopall)
        self.collected = {"posts": [post()], "errors": []}
        self.collect = patch.object(pipeline, "collect_gatorconnect", side_effect=lambda: deepcopy(self.collected)).start()
        self.extract = patch.object(pipeline, "extract_events", side_effect=lambda *a, **k: {"image_text": "", "events": [event()]}).start()
        self.resolver = MagicMock()
        self.resolver.resolve.side_effect = lambda e: {**e, "location_status": "resolved", "latitude": 29.65, "longitude": -82.34}
        patch.object(pipeline, "PlacesResolver", return_value=self.resolver).start()
        self.download = patch.object(pipeline, "download_image", return_value=(b"image-one", "image/png")).start()

    def test_repeat_skips_paid_processing_and_replay_restores_output(self):
        first = pipeline.scrape_gatorconnect()
        second = pipeline.scrape_gatorconnect()
        replay = pipeline.scrape_gatorconnect(include_unchanged=True)
        self.assertEqual(first["posts"][0]["change_type"], "new")
        self.assertEqual(second["posts"], [])
        self.assertEqual(second["unchanged_posts"], 1)
        self.assertEqual(replay["posts"][0]["change_type"], "unchanged")
        self.assertEqual(self.extract.call_count, 1)
        self.assertEqual(self.resolver.resolve.call_count, 1)

    def test_source_edit_reprocesses_same_id(self):
        pipeline.scrape_gatorconnect()
        self.collected["posts"][0]["source_details"]["description"] = "Updated workshop description."
        result = pipeline.scrape_gatorconnect()
        self.assertEqual(result["posts"][0]["change_type"], "updated")
        self.assertEqual(result["posts"][0]["source_event_id"], "1")
        self.assertEqual(self.extract.call_count, 2)

    def test_old_24_hour_cache_expiry_does_not_repeat_enrichment(self):
        pipeline.scrape_gatorconnect()
        self.clock.return_value += 86401
        result = pipeline.scrape_gatorconnect()
        self.assertEqual(result["unchanged_posts"], 1)
        self.assertEqual(self.extract.call_count, 1)

    def test_same_flyer_skips_download_until_recheck_and_reuses_extraction(self):
        self.collected["posts"][0]["image_urls"] = ["https://se-images.campuslabs.com/flyer.png"]
        pipeline.scrape_gatorconnect()
        pipeline.scrape_gatorconnect()
        self.assertEqual(self.download.call_count, 1)
        self.clock.return_value = 1000 + config.GATORCONNECT_IMAGE_RECHECK_SECONDS + 1
        result = pipeline.scrape_gatorconnect()
        self.assertEqual(self.download.call_count, 2)
        self.assertEqual(self.extract.call_count, 1)
        self.assertEqual(result["reused_extractions"], 1)
        self.assertEqual(result["posts"], [])

    def test_changed_bytes_at_same_url_trigger_extraction(self):
        self.collected["posts"][0]["image_urls"] = ["https://se-images.campuslabs.com/flyer.png"]
        pipeline.scrape_gatorconnect()
        self.clock.return_value = 1000 + config.GATORCONNECT_IMAGE_RECHECK_SECONDS + 1
        self.download.return_value = (b"image-two", "image/png")
        pipeline.scrape_gatorconnect()
        self.assertEqual(self.extract.call_count, 2)

    def test_location_retry_does_not_repeat_gemini(self):
        self.resolver.resolve.side_effect = lambda e: {**e, "location_status": "error", "location_warning": "Temporary failure."}
        first = pipeline.scrape_gatorconnect()
        self.assertEqual(len(first["posts"]), 1)
        immediate = pipeline.scrape_gatorconnect()
        self.assertEqual(immediate["deferred_posts"], 1)
        self.clock.return_value += config.GATORCONNECT_RETRY_SECONDS + 1
        self.resolver.resolve.side_effect = lambda e: {**e, "location_status": "resolved", "latitude": 29.65, "longitude": -82.34}
        result = pipeline.scrape_gatorconnect()
        self.assertEqual(self.extract.call_count, 1)
        self.assertEqual(result["reused_extractions"], 1)
        self.assertEqual(result["posts"][0]["change_type"], "updated")

    def test_gemini_failure_falls_back_then_recovers(self):
        self.extract.side_effect = ScraperError("gemini", "service_unavailable", "Temporary outage.")
        result = pipeline.scrape_gatorconnect()
        self.assertEqual(result["posts"][0]["events"][0]["title"], "Workshop")
        self.assertEqual(result["posts"][0]["events"][0]["Tags"], [])
        self.assertEqual(result["posts"][0]["enrichment_status"], "pending")
        with GatorConnectState() as store:
            self.assertIsNone(store.get("event:1")["extraction"])
        self.clock.return_value += config.GATORCONNECT_RETRY_SECONDS + 1
        self.extract.side_effect = lambda *a, **k: {"image_text": "", "events": [event()]}
        result = pipeline.scrape_gatorconnect()
        self.assertEqual(result["posts"][0]["enrichment_status"], "complete")
        self.assertEqual(self.extract.call_count, 2)

    def test_gemini_outage_stops_calls_for_subsequent_events(self):
        self.collected["posts"] = [post("1"), post("2")]
        self.extract.side_effect = ScraperError("gemini", "service_unavailable", "Temporary outage.")
        result = pipeline.scrape_gatorconnect()
        self.assertEqual(len(result["posts"]), 2)
        self.assertEqual(self.extract.call_count, 1)
        self.assertEqual(result["posts"][1]["enrichment_status"], "pending")

    def test_source_only_mode_makes_no_gemini_or_image_requests(self):
        self.collected["posts"][0]["image_urls"] = ["https://se-images.campuslabs.com/flyer.png"]
        with patch.object(config, "GATORCONNECT_USE_GEMINI", False):
            result = pipeline.scrape_gatorconnect()
        self.extract.assert_not_called()
        self.download.assert_not_called()
        self.assertEqual(result["posts"][0]["enrichment_status"], "disabled")
        self.assertEqual(result["posts"][0]["events"][0]["Tags"], [])

    def test_failed_download_remains_retryable(self):
        self.collected["posts"][0]["image_urls"] = ["https://se-images.campuslabs.com/flyer.png"]
        self.download.side_effect = ScraperError("download", "failed", "Flyer unavailable.")
        result = pipeline.scrape_gatorconnect()
        self.assertTrue(result["errors"])
        self.clock.return_value += config.GATORCONNECT_RETRY_SECONDS + 1
        self.download.side_effect = None
        pipeline.scrape_gatorconnect()
        self.assertEqual(self.download.call_count, 2)
        self.assertEqual(self.extract.call_count, 2)  # Text-only then full flyer.

    def test_different_source_ids_are_not_guessed_to_be_duplicates(self):
        self.collected["posts"] = [post("1"), post("2")]
        result = pipeline.scrape_gatorconnect()
        self.assertEqual(len(result["posts"]), 2)

    def test_state_failure_stops_before_collection(self):
        with patch.object(pipeline, "GatorConnectState") as state:
            state.return_value.__enter__.side_effect = ScraperError("storage", "state_unavailable", "Unavailable.")
            with self.assertRaises(ScraperError):
                pipeline.scrape_gatorconnect()
        self.collect.assert_not_called()
        self.extract.assert_not_called()


class PersistentProviderTests(unittest.TestCase):
    def test_successful_location_reused_across_runs_and_expires(self):
        session = MagicMock()
        session.get.return_value = response([PLACE])
        with TemporaryDirectory() as folder, patch("Scraper.geocode_resolver.time.time", return_value=1000) as clock:
            for _ in range(2):
                with GatorConnectState(folder) as store:
                    result = GeocodeResolver(session=session, api_key="test", store=store).resolve(event())
                    self.assertEqual(result["location_status"], "resolved")
            self.assertEqual(session.get.call_count, 1)
            clock.return_value += config.GATORCONNECT_LOCATION_TTL_SECONDS + 1
            with GatorConnectState(folder) as store:
                GeocodeResolver(session=session, api_key="test", store=store).resolve(event())
            self.assertEqual(session.get.call_count, 2)

    def test_long_cooldown_blocks_other_events_and_new_runs(self):
        session = MagicMock()
        session.get.return_value = response([], 429, {"Retry-After": "3600"})
        with TemporaryDirectory() as folder, patch("Scraper.geocode_resolver.time.time", return_value=1000) as clock, \
                patch("Scraper.geocode_resolver.time.sleep") as sleep:
            with GatorConnectState(folder) as store:
                resolver = GeocodeResolver(session=session, api_key="test", store=store)
                resolver.resolve(event())
                result = resolver.resolve(event(venue="Other Hall"))
                self.assertEqual(result["location_error_code"], "provider_cooldown")
            with GatorConnectState(folder) as store:
                GeocodeResolver(session=session, api_key="test", store=store).resolve(event())
            self.assertEqual(session.get.call_count, 1)
            self.assertTrue(all(call.args[0] <= 30 for call in sleep.call_args_list))
            clock.return_value = 4601
            session.get.return_value = response([PLACE])
            with GatorConnectState(folder) as store:
                result = GeocodeResolver(session=session, api_key="test", store=store).resolve(event())
            self.assertEqual(result["location_status"], "resolved")
            self.assertEqual(session.get.call_count, 2)

    def test_http_date_retry_after(self):
        session = MagicMock()
        deadline = format_datetime(datetime.fromtimestamp(4600, timezone.utc), usegmt=True)
        session.get.return_value = response([], 503, {"Retry-After": deadline})
        with patch("Scraper.geocode_resolver.time.time", return_value=1000):
            resolver = GeocodeResolver(session=session, api_key="test")
            resolver.resolve(event())
            resolver.resolve(event(venue="Other Hall"))
        self.assertEqual(session.get.call_count, 1)

    def test_bad_location_results_not_persisted(self):
        session = MagicMock()
        session.get.return_value = response([{**PLACE, "lat": "NaN"}])
        with TemporaryDirectory() as folder:
            for _ in range(2):
                with GatorConnectState(folder) as store:
                    result = GeocodeResolver(session=session, api_key="test", store=store).resolve(event())
                    self.assertEqual(result["location_status"], "error")
            self.assertEqual(session.get.call_count, 2)

    def test_overlapping_runs_are_rejected_and_lock_releases(self):
        with TemporaryDirectory() as folder:
            with GatorConnectState(folder):
                with self.assertRaises(ScraperError) as caught:
                    with GatorConnectState(folder):
                        self.fail("Second run acquired the same lock.")
                self.assertEqual(caught.exception.code, "already_running")
            with GatorConnectState(folder) as state:
                state.put("test", {"ok": True})
                self.assertTrue(state.get("test")["ok"])


class PartialCollectionTests(unittest.TestCase):
    def test_discovery_budget_returns_partial_records_with_warning(self):
        page = MagicMock()
        page.get_by_role.return_value.count.return_value = 1
        page.get_by_role.return_value.first.is_visible.return_value = True
        data = response({"value": [listing(n) for n in range(1, 6)]})
        data.url = collector.BASE_URL + "/api/discovery/event/search?organizationIds%5B0%5D=1"
        data.status = 200
        def navigate(*args):
            page.on.call_args.args[1](data)
        warnings = []
        with patch.object(collector, "navigate", side_effect=navigate), patch.object(config, "GATORCONNECT_MAX_PAGES", 1):
            rows = collector.collect_listing(page, collector.BASE_URL + "/organization/a", warnings=warnings)
        self.assertEqual(len(rows), 5)
        self.assertEqual(warnings[0]["code"], "discovery_limit")
        self.assertTrue(warnings[0]["partial_results"])

    def test_shared_events_do_not_hide_second_clubs_distinct_event(self):
        with patch("playwright.sync_api.sync_playwright"), \
                patch.object(collector, "collect_listing", side_effect=[[listing(n) for n in range(1, 6)], [listing(n) for n in range(1, 7)]]), \
                patch.object(collector, "read_detail", side_effect=lambda p,r,u: post(str(r["id"]))):
            result = collector.collect_gatorconnect([collector.BASE_URL + "/organization/a",
                                                    collector.BASE_URL + "/organization/b"], now=NOW)
        self.assertEqual([p["source_event_id"] for p in result["posts"]], ["1", "2", "3", "4", "5", "6"])


if __name__ == "__main__":
    unittest.main()
