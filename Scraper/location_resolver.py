"""Resolve event venues with Google Maps and preserve unresolved events."""

import os  # Reads API keys from environment variables.
import re

if __package__:
    from .runtime_utils import ScraperError, http_failure, retry_call, error_record
    from .config import REQUEST_SECONDS, RETRY_ATTEMPTS
else:
    from runtime_utils import ScraperError, http_failure, retry_call, error_record
    from config import REQUEST_SECONDS, RETRY_ATTEMPTS


def lookup_fields(event):
    """Prepare lookup text without changing source fields in the JSON output.

    GatorConnect supplies full street addresses and room numbers. Prefer its
    written address; only use a full_address that passed extraction validation.
    An explicit address locality prevents adding an unrelated Gainesville hint.
    """
    lookup = dict(event)
    lookup["address_text"] = event.get("address_text") or event.get("full_address")
    venue = event.get("venue") or event.get("location") or ""
    venue = re.split(r"\b(?:room|rm\.?|suite)\b|#", venue, flags=re.I)[0]
    lookup["location"] = re.sub(r"\s+\d+[a-z]?\s*$", "", venue, flags=re.I).strip(" ,")
    address = lookup["address_text"] or ""
    if not lookup.get("city_text") and address.count(",") >= 2:
        lookup["city_text"] = address.partition(",")[2].strip()
    return lookup


def place_matches(event, place, latitude, longitude):
    """Conservative matching: a search result is a candidate, not proof of identity."""
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
            return False
    if (not city or 'gainesville' in words(city)) and not (
            29.45 <= latitude <= 29.85 and -82.6 <= longitude <= -82.1):
        # Without explicit city evidence we assume Gainesville, not anywhere in
        # the world. This broad city-area box is a guard, not a venue match.
        return False
    if event.get('address_text'):
        requested = words(event['address_text'].split(',')[0])
        return bool(requested) and requested.issubset(words(address))
    venue = event.get('location') or ''
    # Room identifiers remain in output, but do not form part of building identity.
    venue = re.split(r'\b(?:room|rm|suite)\b|#', venue, flags=re.I)[0]
    requested = words(venue) - {'university', 'florida', 'gainesville'}
    name = place.get('displayName', {}).get('text', '')
    return bool(requested) and requested.issubset(words(name))



def resolve_location(event):
    """Use Google Maps to resolve one venue; preserve the event on failure."""
    import requests

    resolved = {**event, "address": None, "latitude": None, "longitude": None,
                "location_status": "missing", "location_warning": None}
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
        query = f"{query}, University of Florida, Gainesville, FL"
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
                    json={"textQuery": query, "pageSize": 2,
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
        if not places:
            resolved.update(location_status="not_found", location_warning="No matching place found.")
        elif len(places) != 1 or payload.get("nextPageToken"):
            resolved.update(location_status="ambiguous", location_warning="Multiple places matched the location.")
        else:
            place = places[0]
            coordinates = place.get("location", {})
            latitude = coordinates.get("latitude")
            longitude = coordinates.get("longitude")
            address = place.get("formattedAddress")
            # Reject booleans, out-of-range values, NaN, and missing coordinates.
            if (place.get("pureServiceAreaBusiness")
                    or type(latitude) not in (int, float) or not -90 <= latitude <= 90
                    or type(longitude) not in (int, float) or not -180 <= longitude <= 180
                    or not isinstance(address, str) or not address.strip()):
                raise ScraperError("geocoding", "invalid_coordinates", "Maps returned incomplete or invalid coordinates/address.")
            if not place_matches(lookup_event, place, latitude, longitude):
                resolved.update(location_status="ambiguous",
                    location_warning="Returned place does not clearly match the source venue/address and city.")
            else:
                resolved.update(address=address, latitude=latitude, longitude=longitude,
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
            return {**event, **self.disabled}

        result = resolve_location(event)
        fields = {name: result[name] for name in
                  ("address", "latitude", "longitude", "location_status", "location_warning",
                   "location_error_code", "location_provider") if name in result}
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

