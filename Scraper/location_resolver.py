"""Resolve event venues with Google Maps and preserve unresolved events."""

import os  # Reads API keys from environment variables.
import re

if __package__:
    from .runtime_utils import ScraperError, http_failure, retry_call, error_record
    from .config import REQUEST_SECONDS, RETRY_ATTEMPTS, UF_BUILDING_ALIASES
else:
    from runtime_utils import ScraperError, http_failure, retry_call, error_record
    from config import REQUEST_SECONDS, RETRY_ATTEMPTS, UF_BUILDING_ALIASES


def building_name(text):
    """Remove room details from search text while leaving the source untouched."""
    text = re.split(r"\b(?:room|rm\.?|suite)\b|#", text or "", flags=re.I)[0]
    return re.sub(r"\s+\d+[a-z]?\s*$", "", text, flags=re.I).strip(" ,")


def lookup_fields(event):
    """Prepare lookup text without changing source fields in the JSON output.

    GatorConnect supplies full street addresses and room numbers. Prefer its
    written address; only use a full_address that passed extraction validation.
    An explicit address locality prevents adding an unrelated Gainesville hint.
    """
    lookup = dict(event)
    lookup["address_text"] = event.get("address_text") or event.get("full_address")
    lookup["location"] = building_name(event.get("venue") or event.get("location"))
    address = lookup["address_text"] or ""
    if not lookup.get("city_text") and address.count(",") >= 2:
        lookup["city_text"] = address.partition(",")[2].strip()
    # A known source code takes precedence over a speculative Gemini expansion.
    # Match the whole code: LIT must never alter words such as 'Literature'.
    # UF aliases do not apply when an explicit non-Gainesville city is supplied.
    city = lookup.get("city_text") or ""
    if not city or re.search(r'\bgainesville\b', city, re.I):
        aliases = {code.casefold(): name for code, name in UF_BUILDING_ALIASES.items()}
        source_building = building_name(event.get("location"))
        lookup["location"] = (aliases.get(source_building.casefold())
                              or aliases.get(lookup["location"].casefold())
                              or lookup["location"])
    return lookup


def place_mismatch(event, place, latitude, longitude):
    """Return a readable rejection reason, or None for a source-consistent place.

    Matching is deterministic. Google ranking alone does not establish that a
    place is the building in the post, and room numbers are not building names.
    """
    def words(text):
        aliases = {'st': 'street', 'rd': 'road', 'ave': 'avenue', 'blvd': 'boulevard',
                   'dr': 'drive', 'fl': 'florida', 'uf': 'florida'}
        return {aliases.get(word, word) for word in re.findall(r'[a-z0-9]+', text.casefold())
                if word not in {'the', 'of', 'at'}}

    address = place.get('formattedAddress', '')
    city = event.get('city_text')
    if city:
        # Include a written state too: Gainesville, FL must not match another
        # Gainesville in a different state merely because the city name agrees.
        if not words(city).issubset(words(address)):
            return "City/state does not match the source."
    if (not city or 'gainesville' in words(city)) and not (
            29.45 <= latitude <= 29.85 and -82.6 <= longitude <= -82.1):
        # Without explicit city evidence we assume Gainesville, not anywhere in
        # the world. This broad city-area box is a guard, not a venue match.
        return "Coordinates are outside the expected Gainesville area."
    if event.get('address_text'):
        requested = words(event['address_text'].split(',')[0])
        if not requested or not requested.issubset(words(address.split(',')[0])):
            return "Street address does not match the source."
        return None
    venue = event.get('location') or ''
    # Room identifiers remain in output, but do not form part of building identity.
    venue = re.split(r'\b(?:room|rm|suite)\b|#', venue, flags=re.I)[0]
    requested = words(venue) - {'university', 'florida', 'gainesville'}
    name = place.get('displayName', {}).get('text', '')
    if not requested or not requested.issubset(words(name)):
        return "Place name does not match the source venue."
    # A department, office, or parking lot mentioning the building is not the
    # building itself. Keep such candidates unresolved unless explicitly named.
    ancillary = {'parking', 'garage', 'department', 'office', 'atm', 'cafe', 'bookstore'}
    if (words(name) - requested) & ancillary:
        return "Result names a facility within/near the venue, not the requested venue."
    return None


def place_matches(event, place, latitude, longitude):
    """Keep the boolean matching interface available to existing callers."""
    return place_mismatch(event, place, latitude, longitude) is None


def exact_venue_name(name):
    """Normalize punctuation/case and a campus label, but keep meaningful words.

    'Weimer Hall' beats 'College of Journalism and Communications Weimer Hall'.
    'UF Little Hall' and 'Little Hall' are equally exact, so two such candidates
    remain ambiguous. This preference never overrides city/address checks.
    """
    name = re.sub(r'\b(?:university of florida|uf)\b', '', name, flags=re.I)
    return ' '.join(re.findall(r'[a-z0-9]+', name.casefold()))


def assess_candidate(event, place):
    """Validate one API result and produce safe, bounded diagnostic fields.

    Never include headers, raw HTTP errors, or API payloads in diagnostics.
    An unreadable candidate prevents us from claiming a unique match.
    """
    diagnostic = {"name": None, "address": None, "matched": False, "reason": None}
    if not isinstance(place, dict):
        diagnostic["reason"] = "Malformed place result."
        return diagnostic, True
    name = place.get("displayName")
    name = name.get("text") if isinstance(name, dict) else None
    address = place.get("formattedAddress")
    diagnostic.update(name=name[:240] if isinstance(name, str) else None,
                      address=address[:400] if isinstance(address, str) else None)
    if place.get("pureServiceAreaBusiness"):
        diagnostic["reason"] = "Service-area business has no physical event venue."
        return diagnostic, False
    coordinates = place.get("location")
    coordinates = coordinates if isinstance(coordinates, dict) else {}
    latitude, longitude = coordinates.get("latitude"), coordinates.get("longitude")
    # Exact numeric types exclude booleans; range checks also reject NaN/infinity.
    if (type(latitude) not in (int, float) or not -90 <= latitude <= 90
            or type(longitude) not in (int, float) or not -180 <= longitude <= 180
            or not isinstance(address, str) or not address.strip()
            or not isinstance(name, str) or not name.strip()):
        diagnostic["reason"] = "Incomplete or invalid name, coordinates, or address."
        return diagnostic, True
    reason = place_mismatch(event, place, latitude, longitude)
    diagnostic.update(matched=reason is None, reason=reason or "Matches source venue/address and locality.")
    return diagnostic, False



def resolve_location(event):
    """Use Google Maps to resolve one venue; preserve the event on failure."""
    import requests

    resolved = {**event, "address": None, "latitude": None, "longitude": None,
                "location_status": "missing", "location_warning": None,
                "location_diagnostics": {"query": None, "candidates": [], "truncated": False}}
    kind = event.get("location_kind", "missing")
    if kind != "physical":
        status = kind if kind in {"online", "missing", "ambiguous"} else "missing"
        resolved.update(location_status=status,
                        location_warning=f"No map lookup: location is {status}.")
        return resolved

    # Prefer the printed address; otherwise search for the printed venue name.
    lookup_event = lookup_fields(event)
    query = lookup_event.get("address_text") or lookup_event.get("location")
    if not isinstance(query, str) or not query.strip():
        resolved["location_warning"] = "No readable venue or street address."
        return resolved
    city = lookup_event.get("city_text")
    if city and city.casefold() not in query.casefold():
        query = f"{query}, {city}"
    elif not city and not (lookup_event.get("address_text") and "," in query):
        # A building name plus city is sufficient context. Avoid overconstraining
        # Google's text search with an extra institution name on every lookup.
        query = f"{query}, Gainesville, FL"
    resolved["location_diagnostics"]["query"] = query
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        resolved.update(location_status="error",
                        location_error_code="missing_maps_key",
                        location_warning="Set GOOGLE_MAPS_API_KEY and enable Places API (New).")
        return resolved

    try:
        # Ask for only the fields we need. The key stays in a request header.
        def lookup():
            try:
                with requests.post(
                    "https://places.googleapis.com/v1/places:searchText",
                    headers={"X-Goog-Api-Key": key,
                        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.pureServiceAreaBusiness,nextPageToken"},
                    json={"textQuery": query, "pageSize": 5,
                          "includePureServiceAreaBusinesses": False},
                    allow_redirects=False, timeout=(5, REQUEST_SECONDS),
                ) as response:
                    if response.status_code != 200:
                        raise http_failure("geocoding", response.status_code)
                    return response.json()
            except requests.Timeout:
                raise ScraperError("geocoding", "timeout", "Maps lookup timed out.", True) from None
            except requests.ConnectionError:
                raise ScraperError("geocoding", "connection_error", "Maps connection failed.", True) from None
        payload = retry_call(lookup, RETRY_ATTEMPTS)
        if not isinstance(payload, dict) or "error" in payload:
            raise ScraperError("geocoding", "invalid_response", "Maps returned an invalid response.")
        places = payload.get("places", [])
        if not isinstance(places, list):
            raise ScraperError("geocoding", "invalid_response", "Maps returned an invalid places list.")
        diagnostics = resolved["location_diagnostics"]
        diagnostics["truncated"] = bool(payload.get("nextPageToken"))
        matches = []
        invalid_candidate = False
        for place in places:
            diagnostic, invalid = assess_candidate(lookup_event, place)
            diagnostics["candidates"].append(diagnostic)
            invalid_candidate = invalid_candidate or invalid
            if diagnostic["matched"]:
                matches.append(place)

        # Prefer one exact building name over broader names containing it. Only
        # apply this to venue searches, never to competing street-address matches.
        if len(matches) > 1 and not lookup_event.get('address_text'):
            requested = exact_venue_name(lookup_event.get('location') or '')
            exact = [place for place in matches
                     if exact_venue_name(place['displayName']['text']) == requested]
            if requested and len(exact) == 1:
                matches = exact
                diagnostics['selection_reason'] = 'Preferred the only exact venue-name match among source-consistent candidates.'

        # Inspect one bounded page without making additional paid search calls.
        # A next-page token or unreadable result means uniqueness is unproven.
        if invalid_candidate:
            raise ScraperError("geocoding", "invalid_coordinates",
                               "Maps returned an incomplete or invalid candidate; inspect location_diagnostics.")
        if diagnostics["truncated"]:
            resolved.update(location_status="ambiguous",
                            location_warning="More search results exist; a unique match could not be confirmed.")
        elif not places:
            resolved.update(location_status="not_found", location_warning="No matching place found.")
        elif len(matches) != 1:
            warning = ("Multiple source-consistent places matched; no result selected." if matches else
                       "No returned place clearly matches the source venue/address and city.")
            resolved.update(location_status="ambiguous", location_warning=warning)
        else:
            place = matches[0]
            resolved.update(address=place["formattedAddress"],
                            latitude=place["location"]["latitude"],
                            longitude=place["location"]["longitude"],
                            location_status="resolved", location_provider="google_places")
    except (ScraperError, requests.RequestException, ValueError, TypeError, AttributeError) as error:
        # Do not expose HTTP exception details, which could include credentials.
        record = error_record(error, "geocoding")
        resolved.update(location_status="error", location_warning=record["message"],
                        location_error_code=record["code"])
    return resolved


class PlacesResolver:
    """Share Google lookups for repeated venues during one GatorConnect run.

    Cache only location fields, not event titles/descriptions. Another club's
    event must keep its own details even when it meets in the same building.
    No maps.co key, reference table, or persistent maps.co cache is used here.
    """

    def __init__(self):
        self.cache = {}
        self.disabled = None

    def close(self):
        """Release transient lookup results when this run finishes."""
        self.cache.clear()

    def resolve(self, event):
        lookup = lookup_fields(event)
        key = tuple(lookup.get(field) for field in
                    ("location_kind", "address_text", "location", "city_text"))
        if key in self.cache:
            return {**event, **self.cache[key]}
        if self.disabled and event.get("location_kind") == "physical":
            # No request was made for this event: do not copy the previous query.
            return {**event, **self.disabled, "location_diagnostics": {
                "query": None, "candidates": [], "truncated": False}}

        result = resolve_location(event)
        fields = {name: result[name] for name in
                  ("address", "latitude", "longitude", "location_status", "location_warning",
                   "location_error_code", "location_provider", "location_diagnostics") if name in result}
        if result.get("location_error_code") in {"missing_maps_key", "http_401", "http_403", "http_429"}:
            # Repeated events cannot fix missing credentials or quota exhaustion.
            # A fresh resolver on a later run can retry after the setup is fixed.
            self.disabled = fields
        elif result["location_status"] != "error":
            self.cache[key] = fields
        # Transient server failures stay retryable for a subsequent event/run.
        return result



def enrich_locations(extracted):
    """Apply the same location handling to scraped posts and saved images."""
    if (not isinstance(extracted, dict)
            or not isinstance(extracted.get("image_text"), str)
            or not isinstance(extracted.get("events"), list)
            or any(not isinstance(event, dict) for event in extracted["events"])):
        raise ValueError("Gemini returned an unexpected JSON structure.")
    # An unrelated post has no events, so it makes no Maps requests.
    return {**extracted, "events": [resolve_location(event) for event in extracted["events"]]}

