"""Conservative, deterministic comparisons for GatorConnect geocoding.

Search text can be broadened, but acceptance always uses the original source.
No model, fuzzy score, or provider ranking decides which candidate wins.
"""

import math
import re


def words(value):
    """Normalize common address abbreviations without changing house numbers."""
    aliases = {"rd": "road", "st": "street", "ave": "avenue", "dr": "drive",
               "blvd": "boulevard", "fl": "florida", "n": "north", "s": "south",
               "e": "east", "w": "west", "sw": "southwest", "se": "southeast",
               "nw": "northwest", "ne": "northeast"}
    return {aliases.get(word, word) for word in re.findall(r"[a-z0-9]+", value.casefold())
            if word not in {"the", "of", "at", "usa", "us"}}


def building_name(value):
    """Strip rooms from lookup text only, leaving the event's location intact."""
    value = re.split(r"\b(?:room|rm\.?|suite)\b|#", value, flags=re.I)[0]
    return re.sub(r"\s+\d+[a-z]?\s*$", "", value, flags=re.I).strip(" ,")


def numeric_coordinates(candidate):
    """Reject missing, non-finite, boolean, and out-of-range coordinates."""
    values = candidate.get("lat"), candidate.get("lon")
    if any(isinstance(value, bool) for value in values):
        raise ValueError("Boolean coordinates are invalid.")
    latitude, longitude = map(float, values)
    if (not math.isfinite(latitude) or not -90 <= latitude <= 90
            or not math.isfinite(longitude) or not -180 <= longitude <= 180):
        raise ValueError("Coordinates are out of range.")
    return latitude, longitude


def address_parts(value):
    """Parse a conventional US street line and retain explicit locality tokens.

    Unknown formats fall back to a full token comparison rather than guessing.
    This intentionally does not infer a city from an unstructured venue name.
    """
    first, separator, locality = (value or "").partition(",")
    match = re.fullmatch(r"\s*(\d+[a-z]?(?:-\d+)?)\s+(.+?)\s*", first, re.I)
    return (match.group(1).casefold(), words(match.group(2)), words(locality)) if match else (None, set(), words(value or ""))


def candidate_check(candidate, event):
    """Return (coordinates, rejection reason); malformed data raises ValueError.

    Prefer separate provider address fields when present. A display-name-only
    response still works, but must contain all source address tokens. Explicit
    ZIP/city/house-number conflicts never disappear during a fallback lookup.
    """
    latitude, longitude = numeric_coordinates(candidate)
    display = candidate.get("display_name")
    if not isinstance(display, str) or not display.strip():
        raise ValueError("Missing formatted address.")
    details = candidate.get("address") or {}
    if not isinstance(details, dict):
        raise ValueError("Invalid structured address.")
    available = words(display)
    for value in details.values():
        if isinstance(value, str):
            available |= words(value)

    city = event.get("city_text") or ""
    street = event.get("address_text") or event.get("full_address") or ""
    if city and not words(city).issubset(available):
        return None, "Explicit city/state does not match."
    # A structured locality must not contradict an otherwise plausible display
    # name. Strip the state suffix from source city_text before comparing cities.
    source_city = city.split(",")[0].strip() if city else ""
    if not source_city and street.count(",") >= 2:
        source_city = street.split(",")[1].strip()
    returned_city = details.get("city") or details.get("town") or details.get("village")
    if source_city and returned_city and words(source_city) != words(returned_city):
        return None, "City conflicts with the source location."
    if (not city and not (street and "," in street)) or "gainesville" in words(city):
        if not (29.45 <= latitude <= 29.85 and -82.6 <= longitude <= -82.1):
            return None, "Outside the expected UF/Gainesville area."

    if street:
        house, road, _ = address_parts(street)
        source_zip = re.search(r"\b(\d{5})(?:-\d{4})?\b", street.partition(",")[2])
        returned_zip = str(details.get("postcode") or "")[:5]
        if source_zip and returned_zip and source_zip[1] != returned_zip:
            return None, "Postal code conflicts with the source address."
        if house and details.get("house_number") and str(details["house_number"]).casefold() != house:
            return None, "House number conflicts with the source address."
        returned_road = details.get("road") or details.get("pedestrian")
        if house and returned_road and road != words(returned_road):
            return None, "Street name conflicts with the source address."
        # ZIP+4 and the five-digit ZIP identify the same postal region here.
        normalized_street = re.sub(r"\b(\d{5})-\d{4}\b", r"\1", street)
        if not words(normalized_street).issubset(available):
            return None, "Source street/address details could not be confirmed."
    else:
        venue = words(building_name(event.get("venue") or event.get("location") or ""))
        venue -= {"university", "florida", "gainesville"}
        if not venue or not venue.issubset(available):
            return None, "Venue name does not match."
    return (latitude, longitude, display), None


def reference_for(event, references):
    """Match a configured alias exactly after removing rooms; never fuzzy-match."""
    name = words(building_name(event.get("venue") or event.get("location") or ""))
    matches = [ref for ref in references if any(name == words(alias) for alias in ref["aliases"])]
    return matches[0] if len(matches) == 1 else None


def reference_conflict(event, reference):
    """A venue reference must not override a conflicting source street or city."""
    address = reference["address"]
    if event.get("city_text") and not words(event["city_text"]).issubset(words(address)):
        return "Written city conflicts with the verified venue reference."
    street = event.get("address_text") or event.get("full_address")
    if street:
        house, road, locality = address_parts(street)
        ref_house, ref_road, ref_locality = address_parts(address)
        # Compare locality excluding ZIP only when the reference omits a ZIP.
        comparable = {word for word in locality if not word.isdigit()}
        if house != ref_house or road != ref_road or not comparable.issubset(ref_locality):
            return "Written address conflicts with the verified venue reference."
        source_zip = re.search(r"\b\d{5}\b", street.partition(",")[2])
        ref_zip = re.search(r"\b\d{5}\b", address.partition(",")[2])
        if source_zip and ref_zip and source_zip[0] != ref_zip[0]:
            return "Written ZIP code conflicts with the verified venue reference."
    return None
