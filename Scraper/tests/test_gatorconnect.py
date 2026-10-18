"""Offline regression checks. No Gemini, Google Maps, or geocoding charges.

Run: python -m unittest discover -s Scraper/tests -v
Optional browser fixtures require Playwright and an installed Chromium browser.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from Scraper import config, gemini_extractor, gatorconnect_pipeline as pipeline
from Scraper import gatorconnect_scraper as collector
from Scraper.event_validator import validate_extraction
from Scraper.extraction_cache import cache_key
from Scraper.geocode_resolver import GeocodeResolver, location_query
from Scraper.image_utils import media_target
from Scraper.runtime_utils import ScraperError


NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


def listing(identity, day=18):
    return {"id": str(identity), "name": "Workshop", "visibility": "Public",
            "status": "Approved", "startsOn": f"2026-10-{day:02d}T18:00:00-04:00",
            "organizationId": 1, "organizationName": "Fixture Club"}


def post(identity="1"):
    return {"source_type": "gatorconnect", "source_event_id": identity,
            "post_url": collector.BASE_URL + "/event/" + identity,
            "organization_name": "Fixture Club", "image_urls": [],
            "source_details": {"title": "Workshop", "description": "Learn to code.",
                "starts_on": "2026-10-18T18:00:00-04:00", "ends_on": "2026-10-18T19:00:00-04:00",
                "location": "Little Hall 101", "address_text": None, "city_text": "Gainesville, FL",
                "full_address": None, "online_location": None}}


def event(**changes):
    result = {"title": "Workshop", "date": "2026-10-18", "date_text": "2026-10-18",
              "time": "06:00 PM - 07:00 PM", "location": "Little Hall 101", "venue": "Little Hall",
              "address_text": None, "full_address": None, "city_text": "Gainesville, FL",
              "location_kind": "physical", "description": "Learn to code.",
              "supporting_text": "Workshop", "Tags": ["professional"],
              "validation_warnings": [], "validation_status": "checked"}
    result.update(changes)
    return result


def response(payload, status=200, headers=None):
    result = MagicMock()
    result.__enter__.return_value = result
    result.status_code = status
    result.headers = headers or {}
    result.json.return_value = payload
    return result


PLACE = {"lat": "29.6488", "lon": "-82.3406",
         "display_name": "Little Hall, 1400 Stadium Road, Gainesville, Florida, 32611, United States",
         "licence": "OpenStreetMap contributors"}


class CollectionTests(unittest.TestCase):
    def test_sort_deduplicate_and_limit(self):
        rows = [listing(n, 18 + n) for n in range(8, 0, -1)]
        rows += [listing(1, 19), listing(90, 16), {**listing(91), "visibility": "Private"}]
        chosen = collector.select_events(rows, NOW, 30, 5)
        self.assertEqual([r["id"] for r in chosen], ["1", "2", "3", "4", "5"])

    def test_undated_candidate_retained_after_known_dates(self):
        rows = [dict(listing(2), startsOn=None), listing(1)]
        self.assertEqual([r["id"] for r in collector.select_events(rows, NOW, 30, 5)], ["1", "2"])
        self.assertIsNone(collector.parse_start("2026-10-18T18:00:00"))

    def test_outside_date_window_is_excluded(self):
        rows = [listing(1), dict(listing(2), startsOn="2026-11-20T18:00:00-05:00")]
        self.assertEqual([r["id"] for r in collector.select_events(rows, NOW, 30, 5)], ["1"])

    def test_organization_allowlist(self):
        for url in ("http://gatorconnect.ufl.edu/organization/club", "https://evil.test/organization/club",
                    "https://gatorconnect.ufl.edu/organization/club?redirect=evil"):
            with self.subTest(url=url), self.assertRaises(ScraperError):
                collector.organization_url(url)

    def test_five_per_organization_before_detail_or_paid_work(self):
        with patch("playwright.sync_api.sync_playwright") as playwright, \
                patch.object(collector, "collect_listing") as listing_mock, \
                patch.object(collector, "read_detail", side_effect=lambda p, r, u: post(str(r["id"]))) as detail:
            listing_mock.side_effect = [[listing(n) for n in range(1, 9)], [listing(n) for n in range(21, 29)]]
            result = collector.collect_gatorconnect([collector.BASE_URL + "/organization/a",
                                                    collector.BASE_URL + "/organization/b"], now=NOW)
            self.assertEqual(len(result["posts"]), 10)
            self.assertEqual(detail.call_count, 10)
            self.assertFalse(result["errors"])

    def test_restricted_detail_is_rejected(self):
        page = MagicMock()
        page.url = collector.BASE_URL + "/event/1"
        page.goto.return_value.status = 200
        page.evaluate.return_value = {"id": 1, "visibility": "Private"}
        with self.assertRaises(ScraperError):
            collector.read_detail(page, listing(1), collector.BASE_URL + "/organization/a")

    def test_structured_detail_ignores_contacts_and_placeholder_flyer(self):
        page = MagicMock()
        page.url = collector.BASE_URL + "/event/1"
        page.goto.return_value.status = 200
        page.evaluate.return_value = {
            "id": 1, "visibility": "Public", "state": {"status": "Approved"},
            "name": "Workshop", "description": "<p>Learn &amp; build.</p>",
            "startsOn": "2026-10-18T18:00:00-04:00", "imagePath": None,
            "imageUrl": "https://se-images.campuslabs.com/default.png",
            "address": {"name": "Little Hall", "address": "1400 Stadium Rd",
                        "latitude": 1, "longitude": 2},
        }
        result = collector.read_detail(page, listing(1), collector.BASE_URL + "/organization/a")
        self.assertEqual(result["image_urls"], [])
        self.assertEqual(result["source_details"]["address_text"], "1400 Stadium Rd")
        self.assertNotIn("latitude", result["source_details"])
        self.assertEqual(result["source_details"]["description"], "Learn & build.")


class PipelineTests(unittest.TestCase):
    def test_explicit_source_wins_conflicts(self):
        item = post()
        fields = pipeline.source_fields(item)
        raw = {"image_text": "", "events": [event(date="2026-10-19", location="Wrong Hall", venue="Wrong Hall")]}
        result = pipeline.preserve_source(raw, fields, pipeline.source_caption(item, fields))["events"][0]
        self.assertEqual(result["date"], "2026-10-18")
        self.assertEqual(result["location"], "Little Hall 101")
        self.assertIsNone(result["venue"])
        self.assertTrue(any("disagreed" in w for w in result["validation_warnings"]))

    def test_invented_street_address_removed(self):
        result = validate_extraction({"image_text": "Workshop at LIT", "events": [event(
            location="LIT", full_address="123 Imaginary Road")]}, "", source_type="gatorconnect")
        self.assertIsNone(result["events"][0]["full_address"])
        self.assertEqual(result["events"][0]["venue"], "Little Hall")

    def test_text_only_and_non_event_make_no_geocoding_calls(self):
        resolver = MagicMock()
        with patch.object(pipeline, "extract_events", return_value={"image_text": "", "events": []}) as extract:
            processed, errors = pipeline.process_gatorconnect_post(post(), resolver)
        self.assertEqual(extract.call_args.args[0], [])
        self.assertEqual(extract.call_args.kwargs, {"source_type": "gatorconnect", "enrich": False})
        self.assertEqual(processed["events"], [])
        resolver.resolve.assert_not_called()

    def test_optional_flyer_failure_retains_text(self):
        item = post()
        item["image_urls"] = ["https://se-images.campuslabs.com/clink/images/flyer.png"]
        resolver = MagicMock()
        resolver.resolve.side_effect = lambda item: item
        with patch.object(pipeline, "download_image", side_effect=ScraperError("download", "failed", "Failed.")), \
                patch.object(pipeline, "extract_events", return_value={"image_text": "", "events": [event()]}):
            processed, errors = pipeline.process_gatorconnect_post(item, resolver)
        self.assertEqual(len(processed["events"]), 1)
        self.assertEqual(len(errors), 1)

    def test_one_failed_event_does_not_discard_next(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test"}), \
                patch.object(pipeline, "collect_gatorconnect", return_value={"posts": [post("1"), post("2")], "errors": []}), \
                patch.object(pipeline, "GeocodeResolver"), \
                patch.object(pipeline, "process_gatorconnect_post", side_effect=[ValueError(), ({**post("2"), "events": [event()]}, [])]):
            result = pipeline.scrape_gatorconnect()
        self.assertEqual(result["processed_posts"], 1)
        self.assertEqual(len(result["posts"]), 1)
        self.assertEqual(len(result["errors"]), 1)

    def test_missing_year_not_invented(self):
        raw = {"image_text": "Workshop October 18 at Little Hall", "events": [event(date_text="October 18")]}
        result = validate_extraction(raw, "", source_type="gatorconnect")["events"][0]
        self.assertIsNone(result["date"])

    def test_flyer_download_and_enrichment(self):
        item = post()
        item["image_urls"] = ["https://se-images.campuslabs.com/clink/images/flyer.png"]
        resolver = MagicMock()
        resolver.resolve.side_effect = lambda item: {**item, "location_status": "resolved"}
        with patch.object(pipeline, "download_image", return_value=(b"flyer", "image/png")) as download, \
                patch.object(pipeline, "extract_events", return_value={"image_text": "Workshop", "events": [event()]}) as extract:
            processed, errors = pipeline.process_gatorconnect_post(item, resolver)
        self.assertFalse(errors)
        self.assertEqual(extract.call_args.args[0], [(b"flyer", "image/png")])
        self.assertEqual(download.call_args.kwargs["allowed_hosts"], config.GATORCONNECT_MEDIA_HOSTS)
        self.assertEqual(processed["events"][0]["location_status"], "resolved")

    def test_source_online_venue_prevents_physical_lookup(self):
        item = post()
        item["source_details"].update(location="Online", online_location="https://example.test/meeting")
        fields = pipeline.source_fields(item)
        merged = pipeline.preserve_source({"image_text": "", "events": [event()]}, fields,
                                          pipeline.source_caption(item, fields))["events"][0]
        self.assertEqual(merged["location_kind"], "online")


class GeocodingTests(unittest.TestCase):
    def resolver(self, payload=None, status=200, key="test"):
        session = MagicMock()
        session.get.return_value = response([PLACE] if payload is None else payload, status)
        return GeocodeResolver(session=session, api_key=key)

    def test_resolved_and_query_reused(self):
        resolver = self.resolver()
        first = resolver.resolve(event())
        second = resolver.resolve(event())
        self.assertEqual(first["location_status"], "resolved")
        self.assertIsInstance(first["latitude"], float)
        self.assertEqual(first, second)
        self.assertEqual(resolver.session.get.call_count, 1)
        self.assertNotIn("api_key", resolver.session.get.call_args.kwargs["params"])
        self.assertEqual(resolver.session.get.call_args.kwargs["headers"]["Authorization"], "Bearer test")

    def test_online_missing_and_ambiguous_skip_requests(self):
        resolver = self.resolver()
        for kind in ("online", "missing", "ambiguous"):
            self.assertEqual(resolver.resolve(event(location_kind=kind))["location_status"], kind)
        resolver.session.get.assert_not_called()

    def test_bad_or_multiple_results(self):
        cases = [([], "not_found"), ([PLACE, PLACE], "ambiguous"),
                 ([{**PLACE, "lat": "NaN"}], "error"), ([{**PLACE, "lon": "200"}], "error"),
                 ([{**PLACE, "lat": True}], "error"), ([{**PLACE, "display_name": "Other Hall"}], "ambiguous")]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                result = self.resolver(payload).resolve(event())
                self.assertEqual(result["location_status"], expected)
                self.assertIsNone(result["latitude"])

    def test_address_and_explicit_city(self):
        result = self.resolver().resolve(event(address_text="1400 Stadium Road, Gainesville, FL"))
        self.assertEqual(result["location_status"], "resolved")
        query = location_query(event(address_text="123 Main Street", city_text="Orlando, FL"))
        self.assertIn("Orlando", query)
        self.assertNotIn("Gainesville", query)

    def test_missing_key_and_auth_disable_requests(self):
        resolver = self.resolver(key="")
        self.assertEqual(resolver.resolve(event())["location_status"], "error")
        resolver.session.get.assert_not_called()
        for status in (401, 403):
            resolver = self.resolver(status=status)
            resolver.resolve(event())
            resolver.resolve(event(location="New Hall", venue="New Hall"))
            self.assertEqual(resolver.session.get.call_count, 1)

    @patch("Scraper.geocode_resolver.time.sleep")
    def test_transient_failure_retries_but_is_not_cached(self, sleep):
        resolver = self.resolver()
        resolver.session.get.side_effect = [response([], 503), response([], 429), response([PLACE])]
        self.assertEqual(resolver.resolve(event())["location_status"], "error")
        self.assertEqual(resolver.resolve(event())["location_status"], "resolved")
        self.assertEqual(resolver.session.get.call_count, 3)

    @patch("Scraper.geocode_resolver.time.sleep")
    def test_long_retry_after_does_not_block_run(self, sleep):
        resolver = self.resolver()
        resolver.session.get.return_value = response([], 429, {"Retry-After": "3600"})
        self.assertEqual(resolver.resolve(event())["location_status"], "error")
        self.assertEqual(resolver.session.get.call_count, 1)


class GeminiRegressionTests(unittest.TestCase):
    @patch.dict(os.environ, {"GEMINI_API_KEY": "test"})
    def test_cached_text_skips_gemini_and_google(self):
        with patch.object(gemini_extractor, "cached_extraction", return_value={"image_text": "", "events": []}), \
                patch("google.genai.Client") as client, patch.object(gemini_extractor, "enrich_locations") as maps:
            result = gemini_extractor.extract_events([], "Workshop", source_type="gatorconnect", enrich=False)
        self.assertEqual(result["events"], [])
        client.assert_not_called()
        maps.assert_not_called()

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test"})
    def test_instagram_keeps_maps_and_requires_images(self):
        with self.assertRaises(ScraperError):
            gemini_extractor.extract_events([], "Workshop")
        image = b'\xff\xd8\xff\xd9'
        with patch.object(gemini_extractor, "cached_extraction", return_value={"image_text": "", "events": []}), \
                patch.object(gemini_extractor, "enrich_locations", return_value={"events": []}) as maps:
            gemini_extractor.extract_events([(image, "image/jpeg")], "Workshop")
        maps.assert_called_once()

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test"})
    def test_failed_json_not_saved(self):
        with patch.object(gemini_extractor, "cached_extraction", return_value=None) as cache, \
                patch("google.genai.Client") as client:
            client.return_value.__enter__.return_value.models.generate_content.return_value.text = "invalid JSON"
            with self.assertRaises(ScraperError):
                gemini_extractor.extract_events([], "Workshop", source_type="gatorconnect", enrich=False)
        self.assertEqual(cache.call_count, 1)  # Read attempted; no successful write.

    def test_cache_keys_distinguish_sources(self):
        self.assertNotEqual(cache_key([], "same", "model"),
                            cache_key([], "same", "model", source_type="gatorconnect"))

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test"})
    def test_multiple_page_events_are_not_cached(self):
        with patch.object(gemini_extractor, "cached_extraction", return_value=None) as cache, \
                patch("google.genai.Client") as client:
            client.return_value.__enter__.return_value.models.generate_content.return_value.text = json.dumps(
                {"image_text": "", "events": [event(), event()]})
            with self.assertRaises(ScraperError):
                gemini_extractor.extract_events([], "Workshop", source_type="gatorconnect", enrich=False)
        self.assertEqual(cache.call_count, 1)

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test"})
    def test_successful_text_call_writes_cache_and_uses_source_schema(self):
        item = post()
        caption = pipeline.source_caption(item, pipeline.source_fields(item))
        with patch.object(gemini_extractor, "cached_extraction", return_value=None) as cache, \
                patch("google.genai.Client") as client, patch.object(gemini_extractor, "enrich_locations") as maps:
            generate = client.return_value.__enter__.return_value.models.generate_content
            generate.return_value.text = json.dumps({"image_text": "", "events": [event()]})
            result = gemini_extractor.extract_events([], caption, source_type="gatorconnect", enrich=False)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(cache.call_count, 2)
        self.assertIn("venue", generate.call_args.kwargs["config"].response_json_schema["properties"]["events"]["items"]["properties"])
        maps.assert_not_called()


class MediaBoundaryTests(unittest.TestCase):
    @patch("Scraper.image_utils.socket.getaddrinfo", return_value=[(None, None, None, None, ("8.8.8.8", 443))])
    def test_campus_media_requires_explicit_allowlist(self, dns):
        url = "https://se-images.campuslabs.com/clink/images/flyer.png"
        with self.assertRaises(ScraperError):
            media_target(url)
        self.assertEqual(media_target(url, allowed_hosts=config.GATORCONNECT_MEDIA_HOSTS)[0], "se-images.campuslabs.com")
        with self.assertRaises(ScraperError):
            media_target("https://evil.test/flyer.png", allowed_hosts=config.GATORCONNECT_MEDIA_HOSTS)

    @patch("Scraper.image_utils.socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 443))])
    def test_private_dns_target_blocked(self, dns):
        with self.assertRaises(ScraperError):
            media_target("https://se-images.campuslabs.com/flyer.png", allowed_hosts=config.GATORCONNECT_MEDIA_HOSTS)


class BrowserFixtureTests(unittest.TestCase):
    def test_real_pagination_with_intercepted_public_responses(self):
        from playwright.sync_api import sync_playwright
        fixture = Path(__file__).parent / "fixtures" / "organization_events.html"
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True,
                    channel=os.getenv("GATORCONNECT_TEST_BROWSER_CHANNEL") or None)
            except Exception as error:
                self.skipTest(f"Install a Playwright browser to run browser fixtures ({type(error).__name__}).")
            try:
                context = browser.new_context()
                # Every browser request is fulfilled locally; there is no live network.
                def route(request):
                    if "/api/discovery/event/search?" in request.request.url:
                        rows = [listing(1), listing(2)] if "skip=0" in request.request.url else [listing(2), listing(3)]
                        request.fulfill(json={"value": rows})
                    elif "/organization/fixture/events" in request.request.url:
                        request.fulfill(content_type="text/html", body=fixture.read_text())
                    else:
                        request.abort()
                context.route("**/*", route)
                rows = collector.collect_listing(context.new_page(), collector.BASE_URL + "/organization/fixture")
                self.assertEqual([r["id"] for r in collector.select_events(rows, NOW, 30, 5)], ["1", "2", "3"])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
