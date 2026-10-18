# Scraper

## GatorConnect setup and run

GatorConnect is an additional source. It shares Gemini extraction and event
validation and **Google Places API (New)** location lookup with Instagram.
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
$env:GOOGLE_MAPS_API_KEY = "your-google-maps-key"
```

These are two separate keys. Do not put real keys in Python source or commit
them. This launcher reads environment variables; it does not automatically load
a `.env` file. Enable **Places API (New)** and billing in the Google Cloud project
that owns your Maps key; restrict that key to Places API (New). GatorConnect
needs no Apify or geocode.maps.co key.

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

By default, `posts` now contains only **new or changed** event records. Unchanged
events are remembered across runs. Use this option to include saved unchanged
results for the events selected by the current run:

```powershell
python Scraper/main.py --source gatorconnect --include-unchanged
```

The five-event-per-organization limit still applies. Shared IDs already collected
from another organization do not consume the next organization's five slots.
This is not a full historical export: normal collection/date limits still apply.

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
  pages produce errors instead of silently appearing empty. If a later page
  fails or the discovery budget is reached, already-collected records survive
  with `warnings[].partial_results: true`. Their order is earliest among the
  records actually read, not a guarantee about unseen pages.
- `gatorconnect_pipeline.py` prepares page text and optional flyer bytes, calls
  the shared extractor, restores explicit source details, then geocodes each
  extracted event. A broken flyer falls back to text with a download error.
  A failed/empty Gemini enrichment returns the approved page's source facts
  with empty tags and a review warning. It remains pending rather than being
  marked successfully enriched. Provider-wide failures pause further Gemini
  calls for five minutes, while already-saved successful extraction can be reused.
- `gemini_extractor.py` accepts text-only GatorConnect input and can return
  extraction without Google enrichment. Its existing Instagram defaults remain.
  The prompt permits one event per detail page. Instagram keeps its short-lived
  extraction cache. GatorConnect uses durable source/content revisions instead;
  matching extraction survives the old 24-hour expiry. Failed extraction is
  never saved as successful.
- `event_validator.py` checks the shared fields and allows an expanded building
  name as an unverified lookup candidate for GatorConnect. Proposed street
  addresses must occur in the page/flyer text. Source checks are consistency
  checks; model OCR is not independent proof that an event is authentic.
- `location_resolver.py` calls Google Places Text Search (New), requesting only
  the name, address, physical-place flag, coordinates, and pagination token.
  `PlacesResolver` shares repeated venue lookups within a GatorConnect run and
  preserves each event's own source fields. Missing credentials, authorization
  failures, and exhausted quota disable further Google requests for that run.
  Transient errors use bounded retries; unresolved events keep null coordinates.
- `geocode_resolver.py`, `location_matching.py`, and `verified_locations.py` are
  retained as inactive legacy modules/tests. Neither current scraper pipeline
  calls maps.co or resolves coordinates from that reference table.
- `gatorconnect_state.py` keeps source IDs, revision fingerprints, successful
  extraction, last generated output, and cooldowns in SQLite. An OS file lock
  prevents overlapping local runs using the same directory. Each completed
  stage commits independently; a geocoding failure does not undo Gemini work.
  Storage failures stop processing rather than silently disabling protection.

## JSON fields and location behavior

The envelope retains `posts`, `errors`, and `processed_posts`, and adds `warnings`,
`unchanged_posts`, `deferred_posts`, and `reused_extractions`. A post can be
processed again for a location retry and still count as unchanged if its output
does not change; these counters measure different things, not disjoint totals.
Each retained post contains `events` plus `source_type: "gatorconnect"`,
`source_event_id`, `post_url`, organization metadata, and `source_details`.
No Instagram handle is fabricated. Each output post includes `change_type`
(`new`, `updated`, or `unchanged`) and `enrichment_status` (`complete`, `pending`,
or `disabled`). An empty Gemini result no longer erases an approved source event.
Events sharing the same source ID are deduplicated; different IDs are not
automatically merged based on titles or approximate locations.

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

Google Places prefers the written address, then a validated `full_address`, then
`venue`/`location`. Room numbers are retained in event output but removed from
building searches. Explicit address locality is preserved instead of appending
Gainesville to an out-of-town event.

The existing Google resolver accepts one physical place with valid numeric
coordinates and a matching address/venue/locality. Multiple results or a next
page token stay ambiguous. A provider change cannot guarantee coordinates for
missing or genuinely ambiguous venues. `enrichment_status: complete` concerns
Gemini; check `location_status` separately for location success. Successful
results identify `location_provider: "google_places"`.

Old maps.co location caches and cooldowns are ignored. Google lookup reuse is
in memory for the current run; no separate durable Google location cache is
created. Existing event snapshots, duplicate tracking, extraction reuse, and
refresh scheduling continue. Switching providers changes the revision
fingerprint, so the first run may repeat Gemini extraction for selected posts.
The default output still emits only new/changed posts; use `--include-unchanged`
to display all selected saved results.

Page dates and locations take precedence over conflicting Gemini values, with
review warnings. Source timestamps retain their explicit offsets in
`source_details`; missing years or ambiguous timestamps are never filled in.
The organization contact address and the site's existing coordinates are not
used as substitutes for the event location.

Progress is written to stderr and JSON to stdout. Exit codes retain the existing
behavior: 0 for success, 1 for failure without usable results, 2 for partial results.
Deferred enrichment and incomplete discovery also produce a partial-result exit
code when usable records are available.

## Persistent state and request budgets

The default Windows state folder is `%LOCALAPPDATA%\UFEventTracker`. Linux uses
`$XDG_STATE_HOME/UFEventTracker`, or `~/.local/state/UFEventTracker`. Override it
with `GATORCONNECT_STATE_DIR`; use the same directory for scheduled runs that
should share progress. No API keys or image bytes are stored. Runtime files stay
outside the repository by default.

```python
GATORCONNECT_USE_GEMINI = True
GATORCONNECT_IMAGE_RECHECK_SECONDS = 3600
GATORCONNECT_RETRY_SECONDS = 300
GATORCONNECT_LOCATION_TTL_SECONDS = 7 * 86400
```

Unchanged successful revisions skip images, Gemini, and geocoding until a refresh
is due. Changes to source fields, image URLs, model, tags, or extraction rules
trigger processing immediately. Flyers at the same URL are downloaded again
after an hour and compared by content hash. Replaced bytes at an unchanged URL
can therefore take up to that recheck interval to be noticed. Set the image
interval to 0 if every run must verify the bytes instead of reducing downloads.

Successful extraction is committed before geocoding and reused on location
retries. Failed stages retry on a later run after five minutes; the scraper does
not schedule those runs itself. Failed, ambiguous, or missing lookup results do
not become permanent successful geocodes. `GATORCONNECT_LOCATION_TTL_SECONDS`
controls how long a completed event snapshot can remain unchanged before
refreshing. Google venue lookup reuse is limited to the current run.

Set `GATORCONNECT_USE_GEMINI = False` to use structured GatorConnect details
without Gemini or flyer downloads. Tags remain empty, and flyer-only details
will not be extracted. Geocoding continues independently in that mode.

Deduplication tracks generated output, not confirmation from a downstream
database. If terminal output is lost, use `--include-unchanged` to recover current
selected records. Downstream consumers should upsert by `(source_type,
source_event_id)` instead of blindly inserting each update. Separate machines or
state directories do not share locks/progress; no backend schema is modified.

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
produce explicit partial-discovery warnings. Live Gemini accuracy and geocoding
coverage still need a small credentialed run. State writes are local SQLite only;
there are no backend writes or persistent cross-source semantic event merges.

References: [GatorConnect](https://gatorconnect.ufl.edu/),
[Google Places Text Search documentation](https://developers.google.com/maps/documentation/places/web-service/text-search), and
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
