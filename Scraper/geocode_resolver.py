"""Resolve GatorConnect locations with geocode.maps.co, never with Google keys."""

import math
import os
import re
import time

import requests

if __package__:
    from .config import GEOCODE_MIN_INTERVAL_SECONDS, REQUEST_SECONDS, RETRY_ATTEMPTS
    from .runtime_utils import ScraperError, error_record, http_failure
else:
    from config import GEOCODE_MIN_INTERVAL_SECONDS, REQUEST_SECONDS, RETRY_ATTEMPTS
    from runtime_utils import ScraperError, error_record, http_failure


def words(value):
    """Compare street abbreviations without fuzzy or model-based matching."""
    aliases = {"rd": "road", "st": "street", "ave": "avenue", "dr": "drive",
               "blvd": "boulevard", "fl": "florida"}
    return {aliases.get(word, word) for word in re.findall(r"[a-z0-9]+", value.casefold())
            if word not in {"the", "of", "at", "usa", "us"}}


def building_name(value):
    """Remove room identifiers from search input, preserving the original output."""
    value = re.split(r"\b(?:room|rm\.?|suite)\b|#", value, flags=re.I)[0]
    return re.sub(r"\s+\d+[a-z]?\s*$", "", value, flags=re.I).strip(" ,")


def location_query(event):
    street = event.get("address_text") or event.get("full_address")
    query = street or building_name(event.get("venue") or event.get("location") or "")
    if not query:
        return None
    city = event.get("city_text")
    if city and not words(city).issubset(words(query)):
        query += ", " + city
    elif not city and not (street and "," in street):
        # A source address already containing locality details must not receive
        # an invented Gainesville suffix (e.g. a trip to another city).
        query += ", University of Florida, Gainesville, FL"
    return query


def checked_coordinates(candidate, event):
    """Return numeric coordinates only after the candidate matches source text."""
    if not isinstance(candidate, dict):
        raise ValueError("Expected a place object.")
    values = (candidate.get("lat"), candidate.get("lon"))
    if any(isinstance(value, bool) for value in values):
        raise ValueError("Boolean coordinates are invalid.")
    latitude, longitude = map(float, values)
    if (not math.isfinite(latitude) or not -90 <= latitude <= 90
            or not math.isfinite(longitude) or not -180 <= longitude <= 180):
        raise ValueError("Coordinates are out of range.")
    address = candidate.get("display_name")
    if not isinstance(address, str) or not address.strip():
        raise ValueError("Missing formatted address.")

    city = event.get("city_text")
    street = event.get("address_text") or event.get("full_address")
    if city and not words(city).issubset(words(address)):
        return None
    if (not city and not (street and "," in street)) or (city and "gainesville" in words(city)):
        if not (29.45 <= latitude <= 29.85 and -82.6 <= longitude <= -82.1):
            return None
    # A single result is not automatically the correct result. Require the
    # street/house number or building name to agree, plus explicit locality.
    requested = words(street) if street else words(building_name(
        event.get("venue") or event.get("location") or ""))
    requested -= {"university", "florida", "gainesville"} if not street else set()
    if not requested or not requested.issubset(words(address)):
        return None
    return latitude, longitude, address


class GeocodeResolver:
    """One instance per run shares pacing, successful queries, and auth failures."""

    def __init__(self, *, session=None, api_key=None):
        self.api_key = os.getenv("GEOCODE_MAPS_API_KEY") if api_key is None else api_key
        self.session = session or requests.Session()
        self.cache = {}
        self.next_request = 0.0
        self.disabled = None

    def close(self):
        self.session.close()

    def search(self, query):
        """Bound retries; never persist response snapshots or cache failures."""
        if not self.api_key:
            self.disabled = ScraperError("geocoding", "missing_geocode_key",
                                         "Set GEOCODE_MAPS_API_KEY for GatorConnect location lookup.")
        if self.disabled:
            raise self.disabled
        if query in self.cache:
            return self.cache[query]

        for attempt in range(RETRY_ATTEMPTS):
            time.sleep(max(0, self.next_request - time.monotonic()))
            self.next_request = time.monotonic() + GEOCODE_MIN_INTERVAL_SECONDS
            try:
                with self.session.get(
                    "https://geocode.maps.co/search",
                    params={"q": query, "format": "json", "addressdetails": 1, "limit": 2},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=(5, REQUEST_SECONDS), allow_redirects=False,
                ) as response:
                    if response.status_code != 200:
                        error = http_failure("geocoding", response.status_code)
                        if response.status_code in (401, 403):
                            self.disabled = error
                        # Respect a reasonable Retry-After value; long waits end
                        # this lookup instead of keeping a scheduled run hanging.
                        delay = response.headers.get("Retry-After", "")
                        if delay:
                            try:
                                delay = float(delay)
                                if not math.isfinite(delay) or delay < 0 or delay > 30:
                                    error.retryable = False
                                else:
                                    self.next_request = max(self.next_request, time.monotonic() + delay)
                            except ValueError:
                                error.retryable = False
                        raise error
                    payload = response.json()
                    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
                        raise ScraperError("geocoding", "invalid_response", "Geocoding returned an invalid place list.")
                    self.cache[query] = payload
                    return payload
            except (requests.Timeout, requests.ConnectionError):
                error = ScraperError("geocoding", "connection_error", "Geocoding connection failed or timed out.", True)
            except ScraperError as caught:
                error = caught
            if not error.retryable or attempt + 1 == RETRY_ATTEMPTS:
                raise error
            self.next_request = max(self.next_request, time.monotonic() + 2 ** attempt)

    def resolve(self, event):
        """Preserve the event even if its location cannot be resolved."""
        result = {**event, "address": None, "latitude": None, "longitude": None,
                  "location_status": "missing", "location_warning": None}
        kind = event.get("location_kind", "missing")
        if kind != "physical":
            result["location_status"] = kind if kind in {"online", "ambiguous", "missing"} else "missing"
            result["location_warning"] = "No lookup for a missing, online-only, or ambiguous location."
            return result
        query = location_query(event)
        if not query:
            result["location_warning"] = "No readable address or venue."
            return result

        try:
            places = self.search(query)
            if not places:
                result.update(location_status="not_found", location_warning="No location matched this query.")
            elif len(places) != 1:
                result.update(location_status="ambiguous", location_warning="Multiple places matched; no result selected.")
            else:
                coordinates = checked_coordinates(places[0], event)
                if coordinates is None:
                    result.update(location_status="ambiguous", location_warning="Place does not agree with the requested venue/address and city.")
                else:
                    latitude, longitude, address = coordinates
                    result.update(address=address, latitude=latitude, longitude=longitude, location_status="resolved",
                                  location_provider="geocode.maps.co",
                                  location_attribution=places[0].get("licence") or "OpenStreetMap contributors")
        except (ScraperError, requests.RequestException, ValueError, TypeError) as error:
            record = error_record(error, "geocoding")
            if isinstance(error, (ValueError, TypeError)):
                record = {"code": "invalid_response", "message": "Geocoding returned invalid coordinates or JSON."}
            result.update(location_status="error", location_error_code=record["code"], location_warning=record["message"])
            # Malformed results must be retryable on a later event/run.
            self.cache.pop(query, None)
        return result
