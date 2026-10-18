"""Resolve GatorConnect locations with geocode.maps.co, never with Google keys."""

import hashlib
import json
import math
import os
import re
import time
from datetime import timezone
from email.utils import parsedate_to_datetime

import requests

if __package__:
    from .location_matching import words, building_name, candidate_check, reference_for, reference_conflict
    from .verified_locations import VERIFIED_LOCATIONS, AMBIGUOUS_VENUES
    from .config import GEOCODE_MIN_INTERVAL_SECONDS, REQUEST_SECONDS, RETRY_ATTEMPTS, GATORCONNECT_LOCATION_TTL_SECONDS
    from .runtime_utils import ScraperError, error_record, http_failure
else:
    from location_matching import words, building_name, candidate_check, reference_for, reference_conflict
    from verified_locations import VERIFIED_LOCATIONS, AMBIGUOUS_VENUES
    from config import GEOCODE_MIN_INTERVAL_SECONDS, REQUEST_SECONDS, RETRY_ATTEMPTS, GATORCONNECT_LOCATION_TTL_SECONDS
    from runtime_utils import ScraperError, error_record, http_failure


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
    """Compatibility wrapper: return coordinates only for a source-consistent place."""
    return candidate_check(candidate, event)[0]


def location_cache_key(event):
    """Keep accepted results separate for different source constraints.

    Caching only by query could let one event's choice hide alternatives from
    another event. Include original venue/address/city and reference settings.
    The v2 prefix also prevents trusting older single-result cache entries.
    """
    fields = {key: event.get(key) for key in
              ("location", "venue", "address_text", "full_address", "city_text")}
    encoded = json.dumps([fields, VERIFIED_LOCATIONS, AMBIGUOUS_VENUES], sort_keys=True)
    return "location-match:v2:" + hashlib.sha256(encoded.encode()).hexdigest()


def location_queries(event, reference=None):
    """At most three unique searches; broaden queries, never acceptance rules."""
    queries = [location_query(event)]
    if reference:
        queries.append(reference["address"])
    venue = building_name(event.get("venue") or event.get("location") or "")
    if reference:
        venue = reference["aliases"][0]
    street = event.get("address_text") or event.get("full_address") or ""
    # Preserve an explicit locality in fallback searches. Without one, remove
    # the university qualifier but retain Gainesville to avoid worldwide hits.
    locality = event.get("city_text") or street.partition(",")[2].strip() or "Gainesville, FL"
    if venue:
        queries.append(venue + ", " + locality)
    return list(dict.fromkeys(query for query in queries if query))[:3]


class GeocodeResolver:
    """One instance per run shares pacing, successful queries, and auth failures."""

    def __init__(self, *, session=None, api_key=None, store=None):
        self.api_key = os.getenv("GEOCODE_MAPS_API_KEY") if api_key is None else api_key
        self.session = session or requests.Session()
        self.cache = {}
        self.next_request = 0.0
        self.disabled = None
        self.store = store
        self.cooldown_until = 0.0

    def close(self):
        self.session.close()

    def search(self, query):
        """Share raw query results within this run; bound pacing and retries.

        Only resolve() persists accepted matches. Keeping all candidates here
        avoids hiding alternatives from another event using the same query.
        """
        query_key = " ".join(query.casefold().split())
        if query_key in self.cache:
            return self.cache[query_key]
        if self.store:
            cooldown = self.store.get("cooldown:geocode.maps.co")
            if cooldown:
                self.cooldown_until = max(self.cooldown_until, cooldown["until"])
        if not self.api_key:
            self.disabled = ScraperError("geocoding", "missing_geocode_key",
                                         "Set GEOCODE_MAPS_API_KEY for GatorConnect location lookup.")
        if self.disabled:
            raise self.disabled
        for attempt in range(RETRY_ATTEMPTS):
            remaining = self.cooldown_until - time.time()
            if remaining > 30:
                raise ScraperError("geocoding", "provider_cooldown",
                                   "Geocoding is cooling down after a service response; retry on a later run.")
            if remaining > 0:
                time.sleep(remaining)
            time.sleep(max(0, self.next_request - time.monotonic()))
            self.next_request = time.monotonic() + GEOCODE_MIN_INTERVAL_SECONDS
            try:
                with self.session.get(
                    "https://geocode.maps.co/search",
                    params={"q": query, "format": "json", "addressdetails": 1, "limit": 5},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=(5, REQUEST_SECONDS), allow_redirects=False,
                ) as response:
                    if response.status_code != 200:
                        error = http_failure("geocoding", response.status_code)
                        if response.status_code in (401, 403):
                            self.disabled = error
                        # Persist Retry-After across events AND future runs.
                        # Numeric seconds and HTTP-date header formats are valid.
                        header = response.headers.get("Retry-After", "")
                        delay = 60.0 if response.status_code == 429 else 0.0
                        if header:
                            try:
                                delay = float(header)
                            except (ValueError, TypeError):
                                try:
                                    deadline = parsedate_to_datetime(header)
                                    if deadline.tzinfo is None:
                                        deadline = deadline.replace(tzinfo=timezone.utc)
                                    delay = max(0.0, deadline.timestamp() - time.time())
                                except (ValueError, TypeError, OverflowError):
                                    delay = 60.0
                        if not math.isfinite(delay) or delay < 0:
                            delay = 60.0
                        if delay:
                            self.cooldown_until = max(self.cooldown_until, time.time() + delay)
                            if self.store:
                                self.store.put("cooldown:geocode.maps.co", {"until": self.cooldown_until})
                        if delay > 30:
                            error.retryable = False
                        raise error
                    payload = response.json()
                    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
                        raise ScraperError("geocoding", "invalid_response", "Geocoding returned an invalid place list.")
                    self.cache[query_key] = payload
                    return payload
            except (requests.Timeout, requests.ConnectionError):
                error = ScraperError("geocoding", "connection_error", "Geocoding connection failed or timed out.", True)
            except ScraperError as caught:
                error = caught
            if not error.retryable or attempt + 1 == RETRY_ATTEMPTS:
                raise error
            self.next_request = max(self.next_request, time.monotonic() + 2 ** attempt)

    def resolve(self, event):
        """Select one defensible place; keep source data and diagnostics on failure.

        Only semantic failures trigger fallback searches. Auth, throttling, or
        transport failures stop immediately so fallbacks cannot bypass cooldowns.
        """
        result = {**event, "address": None, "latitude": None, "longitude": None,
                  "location_status": "missing", "location_warning": None,
                  "location_diagnostics": []}
        kind = event.get("location_kind", "missing")
        if kind != "physical":
            result["location_status"] = kind if kind in {"online", "ambiguous", "missing"} else "missing"
            result["location_warning"] = "No lookup for a missing, online-only, or ambiguous location."
            return result

        reference = reference_for(event, VERIFIED_LOCATIONS)
        if reference:
            conflict = reference_conflict(event, reference)
            if conflict:
                result.update(location_status="ambiguous", location_warning=conflict)
                return result
            result["location_reference"] = reference["source_url"]

        name = building_name(event.get("venue") or event.get("location") or "").casefold()
        if name in AMBIGUOUS_VENUES and not (event.get("address_text") or event.get("full_address")):
            result.update(location_status="ambiguous", location_warning=AMBIGUOUS_VENUES[name])
            return result

        queries = location_queries(event, reference)
        if not queries:
            result["location_warning"] = "No readable address or venue."
            return result

        # A reference may expand a known abbreviation, but original street/city
        # constraints still take precedence over every fallback and cached match.
        checked_event = dict(event)
        if reference:
            checked_event["venue"] = reference["aliases"][0]
            if not (event.get("address_text") or event.get("full_address")):
                checked_event["address_text"] = reference["address"]

        cache_key = location_cache_key(event)
        query = queries[0]
        try:
            # Manually verified coordinates can resolve without a provider key.
            # Require provenance for coordinates separately from address evidence.
            if reference and reference.get("coordinates_source_url") and all(
                    reference.get(key) is not None for key in ("latitude", "longitude")):
                candidate = {"lat": reference["latitude"], "lon": reference["longitude"],
                             "display_name": reference["aliases"][0] + ", " + reference["address"]}
                coordinates, reason = candidate_check(candidate, checked_event)
                if coordinates:
                    latitude, longitude, address = coordinates
                    result.update(address=address, latitude=latitude, longitude=longitude,
                                  location_status="resolved", location_provider="verified_reference",
                                  location_attribution=reference["coordinates_source_url"])
                    return result
                # A reference cannot resolve a source ZIP that it does not verify;
                # let the provider attempt to supply the missing evidence instead.

            saved = self.store.get(cache_key) if self.store else None
            if saved and saved.get("expires", 0) > time.time():
                coordinates, reason = candidate_check(saved["place"], checked_event)
                if coordinates:
                    latitude, longitude, address = coordinates
                    result.update(address=address, latitude=latitude, longitude=longitude,
                                  location_status="resolved", location_provider="geocode.maps.co",
                                  location_attribution=saved["place"].get("licence") or "OpenStreetMap contributors",
                                  location_diagnostics=saved.get("diagnostics", []))
                    return result

            saw_places = False
            for query in queries:
                places = self.search(query)
                saw_places = saw_places or bool(places)
                matches, rejected = [], []
                for candidate in places:
                    coordinates, reason = candidate_check(candidate, checked_event)
                    if coordinates:
                        matches.append((candidate, coordinates))
                    else:
                        rejected.append(reason)
                result["location_diagnostics"].append({
                    "query": query, "returned": len(places), "matching": len(matches),
                    "rejections": sorted(set(rejected)),
                })
                # A full five-result page might hide another valid match. Do not
                # pretend we exhaustively searched it or pick the top-ranked hit.
                if len(matches) > 1 or len(places) >= 5:
                    result.update(location_status="ambiguous",
                                  location_warning="Multiple matching places or search result limit reached; specify a more precise location.")
                    return result
                if not matches:
                    continue

                candidate, (latitude, longitude, address) = matches[0]
                result.update(address=address, latitude=latitude, longitude=longitude,
                              location_status="resolved", location_provider="geocode.maps.co",
                              location_attribution=candidate.get("licence") or "OpenStreetMap contributors")
                if self.store:
                    # Keep only the selected public address fields needed for
                    # revalidation, coordinates and attribution, with a fixed TTL.
                    details = candidate.get("address") or {}
                    self.store.put(cache_key, {
                        "expires": time.time() + GATORCONNECT_LOCATION_TTL_SECONDS,
                        "diagnostics": result["location_diagnostics"],
                        "place": {"lat": latitude, "lon": longitude, "display_name": address,
                                  "address": {key: details[key] for key in
                                              ("house_number", "road", "pedestrian", "city", "town", "village", "state", "postcode")
                                              if key in details},
                                  "licence": result["location_attribution"]},
                    })
                return result

            result.update(location_status="ambiguous" if saw_places else "not_found",
                          location_warning="No candidate agreed with all source location details; check location_diagnostics for conflicts."
                          if saw_places else "No location matched the bounded address/venue searches.")
        except (ScraperError, requests.RequestException, ValueError, TypeError) as error:
            if isinstance(error, ScraperError) and error.stage == "storage":
                raise
            record = error_record(error, "geocoding")
            if isinstance(error, (ValueError, TypeError)):
                record = {"code": "invalid_response", "message": "Geocoding returned invalid coordinates or JSON."}
            result.update(location_status="error", location_error_code=record["code"], location_warning=record["message"])
            self.cache.pop(" ".join(query.casefold().split()), None)
        return result
