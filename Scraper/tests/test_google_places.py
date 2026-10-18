"""Offline provider-switch tests: requests are mocked, never billed."""

from copy import deepcopy
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from Scraper import gatorconnect_pipeline as pipeline
from Scraper.location_resolver import PlacesResolver, resolve_location
from test_gatorconnect import event, post, response


PLACE = {"displayName": {"text": "Little Hall"},
         "formattedAddress": "1400 Stadium Road, Gainesville, FL 32611",
         "location": {"latitude": 29.65, "longitude": -82.34}}


@patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "test-maps-key"})
class GooglePlacesTests(unittest.TestCase):
    @patch("requests.post")
    def test_google_request_and_original_room_preserved(self, request):
        request.return_value = response({"places": [PLACE]})
        original = event(location="Little Hall 0113", venue=None)
        result = resolve_location(original)
        self.assertEqual(result["location_status"], "resolved")
        self.assertEqual(result["location"], "Little Hall 0113")
        self.assertEqual(result["location_provider"], "google_places")
        args, kwargs = request.call_args
        self.assertEqual(args[0], "https://places.googleapis.com/v1/places:searchText")
        self.assertEqual(kwargs["headers"]["X-Goog-Api-Key"], "test-maps-key")
        self.assertNotIn("0113", kwargs["json"]["textQuery"])
        self.assertIn("places.location", kwargs["headers"]["X-Goog-FieldMask"])

    @patch("requests.post")
    def test_full_address_and_out_of_town_city(self, request):
        place = deepcopy(PLACE)
        place.update(formattedAddress="123 Main Street, Orlando, FL 32801",
                     location={"latitude": 28.54, "longitude": -81.38})
        request.return_value = response({"places": [place]})
        result = resolve_location(event(address_text=None, city_text=None,
                                        full_address="123 Main Street, Orlando, FL 32801"))
        self.assertEqual(result["location_status"], "resolved")
        query = request.call_args.kwargs["json"]["textQuery"]
        self.assertNotIn("Gainesville", query)
        self.assertEqual(query.count("Orlando"), 1)
        self.assertIsNone(result["address_text"])

    @patch("requests.post")
    def test_same_location_reused_without_copying_event_details(self, request):
        request.return_value = response({"places": [PLACE]})
        resolver = PlacesResolver()
        resolver.resolve(event(title="First", location="Little Hall 101"))
        result = resolver.resolve(event(title="Second", location="Little Hall 202"))
        self.assertEqual(request.call_count, 1)
        self.assertEqual(result["title"], "Second")
        self.assertEqual(result["location"], "Little Hall 202")
        resolver.close()
        self.assertEqual(resolver.cache, {})

    @patch("requests.post")
    def test_online_missing_and_ambiguous_do_not_call_google(self, request):
        resolver = PlacesResolver()
        for kind in ("online", "missing", "ambiguous"):
            self.assertEqual(resolver.resolve(event(location_kind=kind))["location_status"], kind)
        request.assert_not_called()

    @patch("requests.post")
    def test_missing_key_preserves_event(self, request):
        with patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": ""}):
            result = PlacesResolver().resolve(event())
        self.assertEqual(result["location_error_code"], "missing_maps_key")
        self.assertIsNone(result["latitude"])
        request.assert_not_called()

    @patch("Scraper.runtime_utils.time.sleep")
    @patch("requests.post")
    def test_auth_and_quota_disable_later_requests(self, request, sleep):
        for status, attempts in ((401, 1), (403, 1), (429, 2)):
            request.reset_mock()
            request.return_value = response({}, status)
            resolver = PlacesResolver()
            resolver.resolve(event())
            result = resolver.resolve(event(location="Other Hall", venue="Other Hall"))
            self.assertEqual(result["location_error_code"], f"http_{status}")
            self.assertEqual(request.call_count, attempts)

    @patch("requests.post")
    def test_no_match_multiple_matches_and_invalid_coordinates(self, request):
        for payload, status in (({}, "not_found"), ({"places": [PLACE, PLACE]}, "ambiguous"),
                                ({"places": [PLACE], "nextPageToken": "more"}, "ambiguous"),
                                ({"places": [{**PLACE, "location": {"latitude": True, "longitude": -82.34}}]}, "error")):
            request.return_value = response(payload)
            result = PlacesResolver().resolve(event())
            self.assertEqual(result["location_status"], status)
            self.assertIsNone(result["longitude"])

    @patch("Scraper.runtime_utils.time.sleep")
    @patch("requests.post")
    def test_transient_failures_remain_retryable(self, request, sleep):
        request.side_effect = [response({}, 503), response({}, 503), response({"places": [PLACE]})]
        resolver = PlacesResolver()
        self.assertEqual(resolver.resolve(event())["location_status"], "error")
        self.assertEqual(resolver.resolve(event())["location_status"], "resolved")

    @patch("requests.get", side_effect=AssertionError("maps.co must not be called"))
    @patch("requests.post")
    def test_pipeline_uses_google_and_ignores_old_location_cache(self, request, get):
        request.return_value = response({"places": [PLACE]})
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"GATORCONNECT_STATE_DIR": directory}), \
                patch.object(pipeline, "collect_gatorconnect", return_value={"posts": [post()], "errors": []}), \
                patch.object(pipeline, "extract_events", return_value={"image_text": "", "events": [event()]}):
            # Old maps.co state must neither supply a coordinate nor block Google.
            with pipeline.GatorConnectState() as store:
                store.put("cooldown:geocode.maps.co", {"until": 99999999999})
                store.put("event:1", {"source_key": "old-provider", "complete": True,
                                     "next_check": 99999999999, "processed": {"events": []}})
            result = pipeline.scrape_gatorconnect()
        self.assertEqual(result["posts"][0]["events"][0]["location_provider"], "google_places")
        self.assertEqual(request.call_count, 1)
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
