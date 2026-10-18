"""Offline location selection tests; all coordinates below are test fixtures.

No test sends requests to a geocoder or asserts that a synthetic point is an
actual building location. Tests verify decisions, source preservation and cost
controls, while live provider coverage requires a separate credentialed check.
"""

from copy import deepcopy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from Scraper import geocode_resolver as geocode
from Scraper.gatorconnect_state import GatorConnectState


def event(**changes):
    value = {"location_kind": "physical", "location": "Little Hall 0113",
             "venue": "Little Hall", "address_text": "1400 Stadium Rd, Gainesville, FL 32611",
             "full_address": None, "city_text": None}
    return {**value, **changes}


def place(**changes):
    value = {"lat": "29.65", "lon": "-82.34",
             "display_name": "Little Hall, 1400 Stadium Road, Gainesville, Florida, 32611",
             "address": {"house_number": "1400", "road": "Stadium Road",
                         "city": "Gainesville", "state": "Florida", "postcode": "32611"}}
    return {**value, **changes}


class LocationMatchingTests(unittest.TestCase):
    def resolver(self, responses, **kwargs):
        resolver = geocode.GeocodeResolver(api_key="test", session=MagicMock(), **kwargs)
        resolver.search = MagicMock(side_effect=responses)
        return resolver

    def test_unique_match_among_unrelated_places(self):
        wrong = place(address={"house_number": "999", "road": "Wrong Road"})
        resolver = self.resolver([[wrong, place()]])
        result = resolver.resolve(event())
        self.assertEqual(result["location_status"], "resolved")
        self.assertEqual(result["location_diagnostics"][0]["matching"], 1)
        self.assertEqual(result["location"], "Little Hall 0113")
        self.assertEqual(resolver.search.call_count, 1)

    def test_multiple_matching_candidates_remain_ambiguous(self):
        resolver = self.resolver([[place(), place(lat="29.66")]])
        result = resolver.resolve(event())
        self.assertEqual(result["location_status"], "ambiguous")
        self.assertIsNone(result["latitude"])
        self.assertEqual(resolver.search.call_count, 1)

    def test_full_result_page_does_not_claim_uniqueness(self):
        wrong = place(display_name="Elsewhere", address={})
        result = self.resolver([[place(), wrong, wrong, wrong, wrong]]).resolve(event())
        self.assertEqual(result["location_status"], "ambiguous")

    def test_bounded_fallback_finds_source_consistent_building(self):
        resolver = self.resolver([[], [], [place()]])
        result = resolver.resolve(event())
        self.assertEqual(result["location_status"], "resolved")
        self.assertEqual(resolver.search.call_count, 3)
        query = resolver.search.call_args.args[0]
        self.assertIn("Little Hall", query)
        self.assertNotIn("0113", query)
        self.assertEqual(result["address_text"], event()["address_text"])

    def test_postal_conflict_survives_every_fallback(self):
        resolver = self.resolver([[place()], [place()], [place()]])
        result = resolver.resolve(event(address_text="1400 Stadium Rd, Gainesville, FL 32601"))
        self.assertEqual(result["location_status"], "ambiguous")
        self.assertIsNone(result["longitude"])
        self.assertTrue(all("Postal code" in row["rejections"][0] for row in result["location_diagnostics"]))

    def test_reference_cannot_override_conflicting_street(self):
        resolver = self.resolver([])
        result = resolver.resolve(event(address_text="999 Other Road, Gainesville, FL"))
        self.assertEqual(result["location_status"], "ambiguous")
        resolver.search.assert_not_called()

    def test_wrong_structured_city_rejected(self):
        candidate = place()
        candidate["address"]["city"] = "Orlando"
        self.assertIsNone(geocode.checked_coordinates(candidate, event()))

    def test_postal_extension_and_abbreviations(self):
        result = self.resolver([[place()]]).resolve(event(address_text="1400 Stadium Rd, Gainesville, FL 32611-1234"))
        self.assertEqual(result["location_status"], "resolved")

    def test_out_of_town_fallback_retains_explicit_city(self):
        queries = geocode.location_queries(event(venue="Convention Center", location="Convention Center",
                                                address_text="123 Main Street, Orlando, FL"))
        self.assertTrue(all("Orlando" in query for query in queries))
        self.assertTrue(all("Gainesville" not in query for query in queries))

    def test_venue_only_fallback_removes_university_qualifier(self):
        resolver = self.resolver([[], [place(display_name="Example Park, Gainesville, Florida", address={})]])
        result = resolver.resolve(event(venue="Example Park", location="Example Park", address_text=None))
        self.assertEqual(result["location_status"], "resolved")
        self.assertEqual(resolver.search.call_args.args[0], "Example Park, Gainesville, FL")

    def test_no_results_stops_after_budget(self):
        resolver = self.resolver([[], [], []])
        self.assertEqual(resolver.resolve(event())["location_status"], "not_found")
        self.assertLessEqual(resolver.search.call_count, 3)

    def test_bad_candidate_prevents_unsafe_selection(self):
        resolver = self.resolver([[place(lat="NaN"), place()]])
        result = resolver.resolve(event())
        self.assertEqual(result["location_status"], "error")
        self.assertEqual(resolver.search.call_count, 1)

    def test_known_abbreviation_uses_reference(self):
        resolver = self.resolver([[place()]])
        result = resolver.resolve(event(location="LIT 0113", venue="LIT", address_text=None))
        self.assertEqual(result["location_status"], "resolved")
        self.assertIn("location_reference", result)
        self.assertEqual(result["venue"], "LIT")

    def test_verified_coordinates_skip_api_and_need_provenance(self):
        ref = deepcopy(geocode.VERIFIED_LOCATIONS[0])
        ref.update(latitude=29.65, longitude=-82.34,
                   coordinates_source_url="https://example.org/verified-test-fixture")
        resolver = self.resolver([])
        resolver.api_key = ""
        with patch.object(geocode, "VERIFIED_LOCATIONS", (ref,)):
            result = resolver.resolve(event(address_text=None))
        self.assertEqual(result["location_provider"], "verified_reference")
        resolver.search.assert_not_called()
        ref["coordinates_source_url"] = None
        resolver = self.resolver([[place()]])
        with patch.object(geocode, "VERIFIED_LOCATIONS", (ref,)):
            result = resolver.resolve(event(address_text=None))
        self.assertEqual(result["location_provider"], "geocode.maps.co")

    def test_lake_needs_shore_but_explicit_address_can_be_searched(self):
        resolver = self.resolver([])
        result = resolver.resolve(event(location="Lake Wauburg", venue="Lake Wauburg", address_text=None))
        self.assertEqual(result["location_status"], "ambiguous")
        self.assertIn("north and south", result["location_warning"])
        resolver.search.assert_not_called()
        queries = geocode.location_queries(event(location="Lake Wauburg", venue="Lake Wauburg",
                                                 address_text="133 Regatta Drive, Micanopy, FL 32667"))
        self.assertTrue(all("Micanopy" in query for query in queries))

    def test_accepted_fallback_reused_across_runs_without_new_calls(self):
        with TemporaryDirectory() as directory, patch.object(geocode.time, "time", return_value=1000):
            with GatorConnectState(directory) as store:
                first = self.resolver([[], [], [place()]], store=store).resolve(event())
                original = store.get(geocode.location_cache_key(event()))
            with GatorConnectState(directory) as store:
                resolver = self.resolver([], store=store)
                second = resolver.resolve(event())
                resolver.search.assert_not_called()
                self.assertEqual(first, second)
                self.assertEqual(store.get(geocode.location_cache_key(event()))["expires"], original["expires"])

    def test_different_source_constraints_do_not_share_selected_match(self):
        self.assertNotEqual(geocode.location_cache_key(event()),
                            geocode.location_cache_key(event(address_text=None)))

    def test_authentication_failure_does_not_trigger_fallback(self):
        resolver = self.resolver([])
        resolver.search.side_effect = geocode.ScraperError("geocoding", "authentication", "Authentication failed.")
        result = resolver.resolve(event())
        self.assertEqual(result["location_status"], "error")
        self.assertEqual(resolver.search.call_count, 1)


if __name__ == "__main__":
    unittest.main()
