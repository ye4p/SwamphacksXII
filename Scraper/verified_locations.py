"""Manually checked UF venue references; never populate these from Gemini.

Addresses below were checked against the linked UF pages on 2026-10-18.
Those pages do not establish coordinates, so coordinates are deliberately null.
Add numeric coordinates only with a coordinates_source_url documenting them.
Postal codes are omitted here because UF sources disagree; the resolver still
checks any postal code explicitly supplied by an event against geocoder results.
"""

VERIFIED_LOCATIONS = (
    {
        "aliases": ("Little Hall", "LIT"),
        "address": "1400 Stadium Road, Gainesville, FL",
        "source_url": "https://circle.math.ufl.edu/location-and-parking/",
        "verified_on": "2026-10-18",
        "latitude": None,
        "longitude": None,
        "coordinates_source_url": None,
    },
    {
        "aliases": ("New Physics Building", "NPB"),
        "address": "2001 Museum Road, Gainesville, FL",
        "source_url": "https://phys.ufl.edu/department/",
        "verified_on": "2026-10-18",
        "latitude": None,
        "longitude": None,
        "coordinates_source_url": None,
    },
)

# A general lake name cannot identify which entrance an event uses. Retain
# this explicit ambiguity instead of placing people at a guessed entrance.
AMBIGUOUS_VENUES = {
    "lake wauburg": (
        "Lake Wauburg has separate north and south locations; specify the shore "
        "or an event address. Reference: https://recsports.ufl.edu/locations/lake-wauburg/"
    ),
}
