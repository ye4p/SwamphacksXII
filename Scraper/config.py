"""Club accounts and Apify settings; API keys stay in environment variables."""

from pathlib import Path

from dotenv import load_dotenv

# Use the same local credentials as the backend, regardless of working directory.
# Explicit process environment variables retain precedence.
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env", override=False)

# Add club usernames here, without the @ symbol, as quoted strings.
CLUB_HANDLES = ["ufsase"]
POSTS_PER_ACCOUNT = 5

OUTPUT_TIMEZONE = "America/New_York"  # UF's timezone; UTC export accounts for DST.

# Known UF building codes used only to prepare Places searches. Add verified
# code/name pairs here; do not put guessed street addresses or coordinates here.
# Matching ignores case and requires the entire building code after room removal.
UF_BUILDING_ALIASES = {
    # General classroom buildings.
    "LIT": "Little Hall",
    "MAT": "Matherly Hall",
    "TUR": "Turlington Hall",
    "AND": "Anderson Hall",
    "WEIM": "Weimer Hall",

    # Engineering buildings.
    "CSE": "Computer Sciences/Engineering",
    "NEB": "Engineering Building",
    "WEIL": "Weil Hall",
    "BEN": "Benton Hall",
    "LAR": "Larsen Hall",
    "BLK": "Black Hall",
    "RHN": "Rhines Hall",
    "CHE": "Chemical Engineering",
    "MAEA": "Mechanical & Aerospace Engineering Building A",
    "MAEB": "Mechanical & Aerospace Engineering Building B",
    "MAEC": "Mechanical & Aerospace Engineering Building C",
    "NANO": "Nanoscale Research Facility",
    "WERT": "Herbert Wertheim Laboratory of Engineering Excellence",

    # Both codes refer to the same building.
    "MALA": "Malachowsky Hall for Data Science & Information Technology",
    "MALAC": "Malachowsky Hall for Data Science & Information Technology",

    # Research and health sciences buildings.
    "NPB": "New Physics Building",
    "HPNP": "Health Professions, Nursing and Pharmacy Building",
    "MBI": "McKnight Brain Institute",
    "CGRC": "Cancer and Genetics Research Building",

    # Your existing name aliases.
    "Weimer": "Weimer Hall",
    "Turlington Hall": "Turlington Hall",
}

# Set APIFY_API_TOKEN in your terminal; no Instagram login session is used.
APIFY_ACTOR = "apify/instagram-scraper"

# Gemini may assign only these tags. Add or edit labels here to change the list.
EVENT_TAGS = ["sports", "food included", "professional", "networking", "recreational", "STEM", "medicine"]

# Explicit budgets keep a scheduled run from waiting or spending indefinitely.
MAX_IMAGE_BYTES = 50 * 1024 * 1024  # Total compressed bytes per post.
MAX_IMAGES = 20
MAX_EVENTS = 20
REQUEST_SECONDS = 30
GEMINI_SECONDS = 60
APIFY_RUN_SECONDS = 120  # Per club; the hosted job also gets this timeout.
APIFY_MAX_CHARGE_USD = "0.25"  # Per club, for pay-per-event Actors.
MAX_CLUBS = 20
MAX_POSTS_PER_ACCOUNT = 20
RETRY_ATTEMPTS = 2  # Includes the first attempt, not two extra attempts.
CACHE_TTL_SECONDS = 86400  # Reuse Gemini text extraction for up to one day.

# GatorConnect is a separate source; use public organization profile URLs.
# Copy each URL from https://gatorconnect.ufl.edu/organizations.
# An empty list produces a setup message instead of scraping every club.
GATORCONNECT_ORGANIZATION_URLS = ["https://gatorconnect.ufl.edu/organization/aerogator", "https://gatorconnect.ufl.edu/organization/asme"]
GATORCONNECT_DAYS_AHEAD = 30
GATORCONNECT_EVENTS_PER_ORG = 5  # Applied BEFORE flyer downloads and Gemini.
GATORCONNECT_MAX_PAGES = 10  # Bounds discovery even if pagination breaks.
GATORCONNECT_MAX_CANDIDATES = 100  # Public detail pages per organization.
GATORCONNECT_PAGE_SECONDS = 30
GATORCONNECT_MEDIA_HOSTS = ("se-images.campuslabs.com",)

# Legacy maps.co pacing, retained for its standalone module/tests.
# Active Instagram and GatorConnect lookups use GOOGLE_MAPS_API_KEY (Places New).
GEOCODE_MIN_INTERVAL_SECONDS = 1.1

# GatorConnect keeps durable source/extraction state separately from the short
# Instagram cache. Set GATORCONNECT_STATE_DIR to choose its runtime directory.
GATORCONNECT_USE_GEMINI = True  # False uses source fields only; Tags stays [].
GATORCONNECT_IMAGE_RECHECK_SECONDS = 3600  # Detect replaced flyers at the same URL.
GATORCONNECT_RETRY_SECONDS = 4  # Failed enrichment can retry on a later run.
GATORCONNECT_LOCATION_TTL_SECONDS = 7 * 86400  # Refresh successful geocoding weekly.

# GatorConnect global /events feed. The public discovery API serves every
# upcoming event in one unauthenticated request, so no browser or Gemini is
# needed. Set False to skip this feed and rely only on per-organization URLs.
GATORCONNECT_GLOBAL_ENABLED = True
GATORCONNECT_GLOBAL_URL = "https://gatorconnect.ufl.edu/api/discovery/event/search"
GATORCONNECT_GLOBAL_TAKE = 2000  # Single-request page size; the API caps at ~2000.
GATORCONNECT_GLOBAL_DAYS_AHEAD = 90  # Only events starting within this window.
GATORCONNECT_GLOBAL_MIN_RESULTS = 10  # Below this the run is treated as degraded.
GATORCONNECT_GLOBAL_MAX_RESULTS = 2000  # Hard cap on events pushed per run.
GATORCONNECT_GLOBAL_TIMEOUT_SECONDS = 60  # HTTP timeout for the discovery request.

# Map GatorConnect theme/category labels to the app's tag vocabulary. Labels not
# listed here are dropped; the app's own tag list is the source of truth.
GATORCONNECT_GLOBAL_TAG_MAP = {
    "sports": {"Athletics", "Athletic/Recreational", "Walks/Runs"},
    "food included": {"Free Food"},
    "professional": {"Professional/Career", "Leadership", "Meeting"},
    "networking": {"GroupBusiness", "Professional/Career", "Leadership"},
    "recreational": {"Athletic/Recreational", "Social", "Walks/Runs", "Dance/Performance",
                     "Show/Concert", "Movie/Film"},
    "STEM": {"Engineering & Technology", "Workshop", "Academic/Educational"},
    "medicine": {"Health & Wellness"},
}
