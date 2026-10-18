# Scraper

## GatorConnect setup and run

GatorConnect is an additional source. It shares Gemini extraction and event
validation with Instagram, but uses **geocode.maps.co**, not Google Places.
All settings, implementation, and tests for this integration are in `Scraper/`.

From the project root, install the additional dependencies into your usual
Python environment:

```powershell
python -m pip install google-genai requests playwright
python -m playwright install chromium
```

Set your keys as environment variables (or through your server's secret manager):

```powershell
$env:GEMINI_API_KEY = "your-gemini-key"
$env:GEOCODE_MAPS_API_KEY = "your-geocode-maps-co-key"
```

These are two separate keys. Do not put real keys in Python source or commit
them. This launcher reads environment variables; it does not automatically load
a `.env` file. No Google Maps or Apify key is needed in GatorConnect mode.

In `Scraper/config.py`, add the public profiles of the organizations you want:

```python
GATORCONNECT_ORGANIZATION_URLS = [
    "https://gatorconnect.ufl.edu/organization/asme",
    # Add other organization profile URLs copied from GatorConnect.
]
GATORCONNECT_DAYS_AHEAD = 30
GATORCONNECT_EVENTS_PER_ORG = 5
```

The list starts empty intentionally: choose your organizations before running.
The collector selects up to **five unique events per organization**, prioritizing
the earliest explicit start times within the next 30 days. The cap is applied
before flyer downloads and Gemini. This version accepts limits from 1 to 5.
Undated public events come after dated events and remain marked for review.
An event shared by two selected organizations is processed once per run.

```powershell
python Scraper/main.py --source gatorconnect
```

Existing commands still work:

```powershell
python Scraper/main.py
python Scraper/main.py --images flyer.jpg --caption "Club meeting"
```

The first uses Instagram and Google Places. Saved-image mode also keeps its
existing Google Places behavior. `--images` cannot be combined with
`--source gatorconnect`.

## How the new modules fit together

- `gatorconnect_scraper.py` opens a fresh signed-out browser, observes public
  organization event-list responses, and uses the page's Load More button.
  It sorts and limits the list, then reads the selected event detail records.
  Browser image downloads are blocked during discovery. Restricted or changed
  pages produce errors instead of silently appearing empty.
- `gatorconnect_pipeline.py` prepares page text and optional flyer bytes, calls
  the shared extractor, restores explicit source details, then geocodes each
  extracted event. A broken flyer falls back to text with a download error.
  One failed event does not discard subsequent events.
- `gemini_extractor.py` accepts text-only GatorConnect input and can return
  extraction without Google enrichment. Its existing Instagram defaults remain.
  The prompt permits one event per detail page, and cache keys include the source
  type, URL/text, model, and image bytes. Failed extraction is not cached.
- `event_validator.py` checks the shared fields and allows an expanded building
  name as an unverified lookup candidate for GatorConnect. Proposed street
  addresses must occur in the page/flyer text. Source checks are consistency
  checks; model OCR is not independent proof that an event is authentic.
- `geocode_resolver.py` queries addresses or venue names, checks a single result,
  converts coordinates to numbers, and preserves events when lookup fails.
  It shares pacing and successful query results only within a run. It does not
  write geocoding response snapshots to the extraction cache. Authorization
  failures disable further geocoding for that run. Long Retry-After values end
  a lookup; short ones and transient errors have bounded retries.

## JSON fields and location behavior

The existing envelope is preserved: `posts`, `errors`, and `processed_posts`.
Each retained post contains `events` plus `source_type: "gatorconnect"`,
`source_event_id`, `post_url`, organization metadata, and `source_details`.
No Instagram handle is fabricated. Empty Gemini event lists are omitted.

Each event retains the shared date/time, description, tags, and validation fields:

- `location`: the original venue text, including room numbers.
- `venue`: a building-name candidate, possibly expanded by Gemini. An inferred
  expansion carries a validation warning rather than becoming a verified fact.
- `address_text`: a written source address; `full_address`: a complete address
  supported by the source. Unknown full addresses stay null.
- `address`: the geocoder's resolved display address.
- `latitude` / `longitude`: numeric coordinates, or null when unresolved.
- `location_status`: `resolved`, `missing`, `online`, `ambiguous`, `not_found`,
  or `error`. `location_warning` explains unresolved results.
- Resolved results include `location_provider` and `location_attribution`.

The geocoder prefers source addresses, then a supported full address, then a
venue name. Room numbers are preserved but removed from building searches.
UF/Gainesville context is added only without an explicit other locality.
Multiple matches are not automatically resolved; a single match must still
agree with the requested name/address and city. Campus building coverage depends
on OpenStreetMap data, so some valid venues may remain unresolved.

Page dates and locations take precedence over conflicting Gemini values, with
review warnings. Source timestamps retain their explicit offsets in
`source_details`; missing years or ambiguous timestamps are never filled in.
The organization contact address and the site's existing coordinates are not
used as substitutes for the event location.

Progress is written to stderr and JSON to stdout. Exit codes retain the existing
behavior: 0 for success, 1 for failure without usable results, 2 for partial results.

## Verification and limitations

```powershell
python -m unittest discover -s Scraper/tests -v
```

Tests mock paid services and include a browser pagination fixture whose network
requests are intercepted locally. The browser test is skipped if no Playwright
browser is installed. For a locally installed Edge browser, you may instead set
`GATORCONNECT_TEST_BROWSER_CHANNEL=msedge` for that test run.

The public event data and pagination were inspected on GatorConnect, but these
are website implementation details, not a versioned API guarantee. A site
redesign may require adapting the collector. Page/candidate discovery budgets
produce an explicit error rather than silently claiming a complete listing.
Live Gemini accuracy and geocoding coverage still need a small credentialed run.
There are no database writes or persistent cross-source event merges in this
integration; extraction caching and per-run source IDs avoid repeated work only
within their respective scope.

References: [GatorConnect](https://gatorconnect.ufl.edu/),
[geocode.maps.co API documentation](https://geocode.maps.co/docs/), and
[Playwright Python setup](https://playwright.dev/python/docs/intro).

## Duplicate prevention

Before scraping Instagram posts, `pipeline.py` calls `fetch_events(start_date)` from
`database.py` to retrieve events already stored from `start_date` onward. The
returned list is converted into a set of `(club, date)` keys.

While processing each scraped post, events whose `(organization_handle, date)`
matches an existing database event are skipped, since that club already has an
event on the same day. This filters Instagram output after extraction; it does
not prevent Gemini or Maps calls for those posts. GatorConnect does not use the
current placeholder database function.
