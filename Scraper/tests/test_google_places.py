"""Offline provider-switch tests: requests are mocked, never billed."""

from copy import deepcopy
import os
import json
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from Scraper import gatorconnect_pipeline as pipeline
from Scraper.location_resolver import PlacesResolver, resolve_location, lookup_fields
from test_gatorconnect import event, post, response


PLACE = {"displayName": {"text": "Little Hall"},
         "formattedAddress": "1400 Stadium Road, Gainesville, FL 32611",
         "location": {"latitude": 29.65, "longitude": -82.34}}


@patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "test-maps-key"})
class GooglePlacesTests(unittest.TestCase):
    @patch('requests.post')
    def test_building_only_query_uses_city_without_institution(self, request):
        request.return_value = response({'places': [{**PLACE, 'displayName': {'text': 'Weimer Hall'}}]})
        result = resolve_location(event(location='Weimer Hall 1064', venue=None, city_text=None))
        self.assertEqual(request.call_args.kwargs['json']['textQuery'], 'Weimer Hall, Gainesville, FL')
        self.assertEqual(result['location'], 'Weimer Hall 1064')
        self.assertEqual(result['location_status'], 'resolved')

    @patch('requests.post')
    def test_aliases_expand_after_room_removal_and_share_lookup(self, request):
        request.return_value = response({'places': [PLACE]})
        resolver = PlacesResolver()
        for location in ('LIT 101', 'lit Room 202', 'LIT #303', 'Little Hall 404'):
            result = resolver.resolve(event(location=location, venue=None, city_text=None))
            self.assertEqual(result['location'], location)
            self.assertEqual(result['location_status'], 'resolved')
            self.assertEqual(result['location_diagnostics']['query'], 'Little Hall, Gainesville, FL')
        self.assertEqual(request.call_count, 1)

    def test_unknown_codes_and_substrings_are_not_expanded(self):
        for name in ('XYZ 101', 'Literature Hall 101', 'LIT Annex 101'):
            result = lookup_fields(event(location=name, venue=None, city_text=None))
            self.assertEqual(result['location'], name.removesuffix(' 101'))

    def test_source_alias_overrides_model_candidate_but_not_explicit_city(self):
        result = lookup_fields(event(location='LIT 101', venue='Wrong Hall', city_text=None))
        self.assertEqual(result['location'], 'Little Hall')
        outside = lookup_fields(event(location='LIT 101', venue=None, city_text='Orlando, FL'))
        self.assertEqual(outside['location'], 'LIT')

    @patch('requests.post')
    def test_written_address_still_has_priority_over_alias(self, request):
        request.return_value = response({'places': [PLACE]})
        result = resolve_location(event(location='LIT 101', venue=None,
                                        address_text='1400 Stadium Road, Gainesville, FL 32611', city_text=None))
        self.assertEqual(request.call_args.kwargs['json']['textQuery'],
                         '1400 Stadium Road, Gainesville, FL 32611')
        self.assertEqual(result['location_status'], 'resolved')

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

    @patch("requests.post")
    def test_weimer_unique_match_among_unrelated_places(self, request):
        weimer = {**PLACE, "displayName": {"text": "Weimer Hall"}}
        request.return_value = response({"places": [PLACE, weimer]})
        result = resolve_location(event(location="Weimer Hall 1064", venue=None))
        self.assertEqual(result["location_status"], "resolved")
        self.assertEqual(result["location"], "Weimer Hall 1064")
        diagnostics = result["location_diagnostics"]
        self.assertNotIn("1064", diagnostics["query"])
        self.assertEqual([c["matched"] for c in diagnostics["candidates"]], [False, True])
        self.assertIn("name", diagnostics["candidates"][0]["reason"])
        self.assertNotIn("test-maps-key", json.dumps(result))
        self.assertEqual(request.call_count, 1)

    @patch("requests.post")
    def test_two_plausible_buildings_stay_ambiguous(self, request):
        request.return_value = response({"places": [PLACE, {**PLACE,
            "displayName": {"text": "University of Florida Little Hall"}}]})
        result = resolve_location(event())
        self.assertEqual(result["location_status"], "ambiguous")
        self.assertTrue(all(c["matched"] for c in result["location_diagnostics"]["candidates"]))
        self.assertIsNone(result["latitude"])

    @patch('requests.post')
    def test_exact_weimer_name_preferred_over_college_listing(self, request):
        exact = {**PLACE, 'displayName': {'text': 'Weimer Hall'}}
        broader = {**PLACE, 'displayName': {'text': 'College of Journalism and Communications Weimer Hall'}}
        request.return_value = response({'places': [broader, exact]})
        result = resolve_location(event(location='Weimer Hall 1064', venue=None))
        self.assertEqual(result['location_status'], 'resolved')
        self.assertIn('only exact', result['location_diagnostics']['selection_reason'])
        self.assertEqual(result['location'], 'Weimer Hall 1064')
        self.assertEqual(request.call_count, 1)

    @patch('requests.post')
    def test_exact_preference_does_not_override_invalid_city_or_pagination(self, request):
        for payload in (
            {'places': [PLACE, {**PLACE, 'displayName': {'text': 'College Little Hall'}}], 'nextPageToken': 'more'},
            {'places': [{**PLACE, 'formattedAddress': 'Orlando, FL'}]},
        ):
            request.return_value = response(payload)
            result = resolve_location(event())
            self.assertEqual(result['location_status'], 'ambiguous')
            self.assertIsNone(result['latitude'])

    @patch('requests.post')
    def test_exact_name_does_not_break_competing_address_tie(self, request):
        request.return_value = response({'places': [PLACE, {**PLACE,
            'displayName': {'text': 'College Little Hall'}}]})
        result = resolve_location(event(address_text='1400 Stadium Road'))
        self.assertEqual(result['location_status'], 'ambiguous')

    @patch("requests.post")
    def test_truncated_results_do_not_establish_uniqueness(self, request):
        request.return_value = response({"places": [PLACE], "nextPageToken": "not-in-output"})
        result = resolve_location(event())
        self.assertEqual(result["location_status"], "ambiguous")
        self.assertTrue(result["location_diagnostics"]["truncated"])
        self.assertNotIn("not-in-output", json.dumps(result))
        self.assertEqual(request.call_count, 1)

    @patch("requests.post")
    def test_reject_wrong_city_department_and_service_area(self, request):
        candidates = [
            {**PLACE, "formattedAddress": "1400 Stadium Road, Orlando, FL"},
            {**PLACE, "displayName": {"text": "Little Hall Parking Garage"}},
            {**PLACE, "pureServiceAreaBusiness": True},
        ]
        request.return_value = response({"places": candidates + [PLACE]})
        result = resolve_location(event())
        self.assertEqual(result["location_status"], "resolved")
        self.assertEqual([c["matched"] for c in result["location_diagnostics"]["candidates"]],
                         [False, False, False, True])

    @patch("requests.post")
    def test_street_address_distinguishes_candidates(self, request):
        request.return_value = response({"places": [PLACE, {**PLACE,
            "formattedAddress": "1500 Stadium Road, Gainesville, FL 32611"}]})
        result = resolve_location(event(address_text="1400 Stadium Rd"))
        self.assertEqual(result["location_status"], "resolved")
        self.assertIn("Street address", result["location_diagnostics"]["candidates"][1]["reason"])

    @patch("requests.post")
    def test_malformed_candidate_prevents_false_unique_match(self, request):
        for candidate in (None, {**PLACE, "displayName": None},
                          {**PLACE, "location": {"latitude": float("nan"), "longitude": -82.34}},
                          {**PLACE, "location": {"latitude": 91, "longitude": -82.34}}):
            with self.subTest(candidate=candidate):
                request.return_value = response({"places": [PLACE, candidate]})
                result = resolve_location(event())
                self.assertEqual(result["location_status"], "error")
                self.assertIsNone(result["latitude"])
                self.assertTrue(result["location_diagnostics"]["candidates"][1]["reason"])

    @patch("requests.post")
    def test_reused_and_disabled_diagnostics_belong_to_the_query(self, request):
        request.return_value = response({"places": [PLACE]})
        resolver = PlacesResolver()
        first = resolver.resolve(event())
        again = resolver.resolve(event(location="Little Hall 202"))
        self.assertEqual(first["location_diagnostics"], again["location_diagnostics"])
        self.assertEqual(request.call_count, 1)
        request.return_value = response({}, 403)
        resolver = PlacesResolver()
        resolver.resolve(event())
        disabled = resolver.resolve(event(location="Weimer Hall", venue=None))
        self.assertIsNone(disabled["location_diagnostics"]["query"])
        self.assertEqual(disabled["location_diagnostics"]["candidates"], [])

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
