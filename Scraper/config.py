"""Club accounts and Apify settings; API keys stay in environment variables."""

# Add club usernames here, without the @ symbol, as quoted strings.
CLUB_HANDLES = ["uf.acm"]
POSTS_PER_ACCOUNT = 5

# Set APIFY_API_TOKEN in your terminal; no Instagram login session is used.
APIFY_ACTOR = "apify/instagram-scraper"

# Gemini may assign only these tags. Add or edit labels here to change the list.
EVENT_TAGS = ["sports", "food included", "professional", "networking"]
