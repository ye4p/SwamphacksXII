"""Club accounts and Apify settings; API keys stay in environment variables."""

# Add club usernames here, without the @ symbol, as quoted strings.
CLUB_HANDLES = ["uf.acm"]
POSTS_PER_ACCOUNT = 5

# Set APIFY_API_TOKEN in your terminal; no Instagram login session is used.
APIFY_ACTOR = "apify/instagram-scraper"

# Gemini may assign only these tags. Add or edit labels here to change the list.
EVENT_TAGS = ["sports", "food included", "professional", "networking"]

# Explicit budgets keep a scheduled run from waiting or spending indefinitely.
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # Total compressed bytes per post.
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
