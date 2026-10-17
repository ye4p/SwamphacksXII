"""Resolve event venues with Google Maps and preserve unresolved events."""

import os  # Reads API keys from environment variables.


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
    query = event.get("address_text") or event.get("location")
    if not isinstance(query, str) or not query.strip():
        resolved["location_warning"] = "No readable venue or street address."
        return resolved
    city = event.get("city_text")
    query = f"{query}, {city}" if city else f"{query}, University of Florida, Gainesville, FL"
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        resolved.update(location_status="error",
                        location_warning="Set GOOGLE_MAPS_API_KEY and enable Places API (New).")
        return resolved

    try:
        # Ask for only the fields we need. The key stays in a request header.
        with requests.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers={"X-Goog-Api-Key": key,
                     "X-Goog-FieldMask": "places.formattedAddress,places.location,places.pureServiceAreaBusiness,nextPageToken"},
            json={"textQuery": query, "pageSize": 2,
                  "includePureServiceAreaBusinesses": False},
            timeout=30,
        ) as response:
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict) or "error" in payload:
            raise ValueError("Invalid Maps response")
        places = payload.get("places", [])
        if not isinstance(places, list):
            raise ValueError("Invalid places list")
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
                raise ValueError("Incomplete or invalid place result")
            resolved.update(address=address, latitude=latitude, longitude=longitude,
                            location_status="resolved")
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        # Do not expose HTTP exception details, which could include credentials.
        resolved.update(location_status="error",
                        location_warning="Maps lookup failed; check API setup, quota, and connectivity.")
    return resolved



def enrich_locations(extracted):
    """Apply the same location handling to scraped posts and saved images."""
    if (not isinstance(extracted, dict)
            or not isinstance(extracted.get("image_text"), str)
            or not isinstance(extracted.get("events"), list)
            or any(not isinstance(event, dict) for event in extracted["events"])):
        raise ValueError("Gemini returned an unexpected JSON structure.")
    # An unrelated post has no events, so it makes no Maps requests.
    return {**extracted, "events": [resolve_location(event) for event in extracted["events"]]}

