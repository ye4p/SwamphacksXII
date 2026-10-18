# Scraper

## Instagram OCR setup

Instagram images are transcribed with [OCR.space](https://ocr.space/ocrapi).
Gemini receives the resulting text plus the post caption to extract events;
it does not receive Instagram image bytes. Carousel images retain numbered
labels, and the original OCR text is preserved in `image_text` for validation.
Cached extractions skip both OCR and Gemini calls.

Set `OCR_SPACE_API_KEY` alongside `GEMINI_API_KEY` in the scraper process:

```bash
export OCR_SPACE_API_KEY='your-ocr-space-key'
```

PowerShell: `$env:OCR_SPACE_API_KEY = "your-ocr-space-key"`.
The scraper automatically loads `backend/.env`; you can put
`OCR_SPACE_API_KEY=your-ocr-space-key` there instead. Existing process environment
variables take precedence. Keep keys out of source control.
This integration uses the free endpoint with Engine 2 and one
upload per image. JPEG/PNG images below 1 MB are uploaded unchanged. Larger images
are automatically compressed to JPEG, reducing dimensions only when needed to
fit below 1 MB. WebP is converted automatically; transparency is flattened onto
white and EXIF orientation is applied during conversion. Originals are not modified.
Compression requires Pillow and may reduce readability of very small text.
OCR errors fail that post
instead of silently extracting events from incomplete text. GatorConnect keeps
its existing extraction path and does not require an OCR.space key.

## Importing from a scheduled server job

Use the synchronous wrapper in `main.py`; it takes exactly four arguments:

```python
from Scraper.main import run_scraper
from Scraper.server_runner import ScraperRunError

organizations = [
    {"id": 7, "name": "ACM", "handle": "uf.acm", "conURL": None},
    {"id": 8, "name": "ASME", "handle": "", "conURL": "https://gatorconnect.ufl.edu/organization/asme"},
]

# Fetch this snapshot from your DB before each job. Include events from BOTH
# sources and all relevant organizations so cross-source duplicates are found.
existing_events = load_events_from_database()

try:
    new_events = run_scraper(
        "instagram",          # Or "gatorconnect" / "gator connect".
        organizations,
        existing_events,      # List of dictionaries matching the Event schema.
        allocate_event_id,    # Your sync function: no arguments, returns an int.
    )
except ScraperRunError as failure:
    new_events = failure.events  # Valid events whose IDs were already allocated.
    report_scraper_issues(failure.issues)

save_events_to_database(new_events)
```

`load_events_from_database`, `allocate_event_id`, `report_scraper_issues`, and
`save_events_to_database` above are your server functions, not scraper functions.
There are no extra required arguments. API credentials remain environment
variables. Per-organization collection budgets remain in `config.py` (currently
five posts/events). Large organization lists are batched to the collector cap.
Missing/blank `handle` or `conURL` entries are skipped for the selected source;
empty input never falls back to the organizations in config. Unrelated fields
such as `name` are ignored. Caller dictionaries and global config are not changed.

The wrapper returns **only new `Event` dictionaries**. Organization IDs come
directly from your input. Event IDs come only from the callback, after schema
validation and duplicate checks. This server path bypasses both dummy database
functions; the existing CLI still supports its separate dummy lookup behavior.

Matching is deterministic: the same organization and exact UTC start instant
is a duplicate regardless of title; different organizations match only on
normalized title plus exact UTC start instant. Unicode, case, and whitespace
are normalized, and equivalent timestamp offsets match. Location is not part
of identity. Matches against the existing snapshot AND earlier candidates in
this run are suppressed. Existing records are not updated or overwritten;
changed venues/titles at the same organization/time still count as duplicates.
Incomplete records are logged and skipped without allocating an ID.

GatorConnect includes saved unchanged selected records because scraper state
does not prove that the server saved an event. Gemini extraction caching and
cooldowns still apply. Duplicate detection here avoids duplicate output and
ID allocation; new source posts can still require Gemini and Places calls before
their event identity is known. This is not cross-post fuzzy matching.

The wrapper does not print JSON or call `sys.exit`. Normal progress is disabled;
warnings use Python logging, and collection/provider failures raise
`ScraperRunError` with safe `.issues` and any valid `.events`. Invalid caller input
raises `ValueError` before paid collection. Callback exceptions, invalid IDs, and
IDs already in the supplied snapshot/current output stop allocation immediately,
without callback retries. An allocator that allocates then throws can consume an
ID externally; no scraper can roll that back. Persist partial events before a
retry and refresh the existing-events snapshot to avoid allocating again.

This function performs blocking I/O and uses synchronous Playwright. In an async
server, run the entire call in a worker thread (for example, `asyncio.to_thread`),
and provide a synchronous, thread-safe ID allocator. One active wrapper run is
allowed per Python process. Serialize the full fetch/scrape/save job in your
scheduler; separate processes or independent backend writes still need database
uniqueness/transaction protection. A stale snapshot alone cannot prevent races.

## Frontend Event output

The default CLI output is now a flat JSON `Event[]` array matching the frontend
interface. Internal collection/caching records keep their original structure.
Only the final formatter in `event_output.py` changes the public output.

```json
[
  {
    "id": 42,
    "organization_id": 7,
    "timestamp": "2026-10-21T21:00:00Z",
    "title": "ADT Exclusive Session",
    "description": "Meet the ADT recruiting team.",
    "address": "1885 Stadium Rd, Gainesville, FL 32611, USA",
    "longitude": -82.347,
    "latitude": 29.647,
    "payload": {
      "notes": "Source: https://www.instagram.com/p/example/\nVenue: Weimer Hall 1064",
      "tags": ["professional", "networking"]
    }
  }
]
```

The values above are illustrative. `database.fetch_event_ids(organization_key,
event_key)` is an explicitly **dummy database lookup**, returning mock numeric
event and organization IDs. Replace its body with your real parameterized lookup
before using the output against a database. The formatter consumes those IDs;
it does not create database rows. Missing IDs or lookup failures reject the event.
The dummy keys include source/title/time; production lookup should use your
stored source associations to preserve identity across renames/rescheduling.

`timestamp` combines the date and explicit start time, defaults to
`OUTPUT_TIMEZONE = "America/New_York"`, and converts to UTC. A GatorConnect
source timestamp with an explicit offset takes precedence. Ambiguous AM/PM,
unsupported timezones, DST gaps/overlaps, and missing dates/times are rejected
instead of guessed. Explicit EST/EDT can disambiguate a DST overlap.

Install timezone data, especially on Windows:

```powershell
python -m pip install tzdata
python Scraper/main.py --source instagram
python Scraper/main.py --source gatorconnect --include-unchanged
```

`Tags` becomes `payload.tags`. Source links, venue/room text, and review warnings
become the string `payload.notes`. A missing description becomes an empty string.
Missing addresses/coordinates cannot satisfy the non-null schema: those records
are retained in stderr diagnostics under `rejected_events`, with their source
details and reasons, instead of fake coordinates or invalid `Event` objects.
Errors and counters also go to stderr; stdout contains only the array. Rejected
events produce a nonzero partial-result exit status. No extra paid calls are
made by formatting. Existing GatorConnect change-feed limits still apply.

Use `--raw-output` to inspect the previous rich envelope, including incomplete
events and location diagnostics. For saved-image schema output, supply the real
organization ID; the event ID still comes from the dummy database lookup:

```powershell
python Scraper/main.py --raw-output
python Scraper/main.py --images flyer.jpg --organization-id 7
python Scraper/main.py --images flyer.jpg --raw-output
```

To save only frontend events, redirect stdout (not stderr):

```powershell
python Scraper/main.py --source instagram > events.json
```

## GatorConnect setup and run

GatorConnect is an additional source. It shares Gemini extraction and event
validation and **Google Places API (New)** location lookup with Instagram.
All settings, implementation, and tests for this integration are in `Scraper/`.

From the project root, install the additional dependencies into your usual
Python environment:

```powershell
python -m pip install google-genai requests playwright python-dotenv Pillow
python -m playwright install chromium
```

Set your keys as environment variables (or through your server's secret manager):

```powershell
$env:GEMINI_API_KEY = "your-gemini-key"
$env:GOOGLE_MAPS_API_KEY = "your-google-maps-key"
```

These are two separate keys. Do not put real keys in Python source or commit
them. The scraper also loads `backend/.env` automatically without overriding
existing environment variables. Enable **Places API (New)** and billing in the Google Cloud project
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
python Scraper/main.py --images flyer.jpg --caption "Club meeting" --raw-output
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

## Internal / --raw-output JSON fields and location behavior

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

Venue searches now use a simpler city context: `Weimer Hall 1064` becomes
`Weimer Hall, Gainesville, FL`, while the source location keeps room 1064.
`UF_BUILDING_ALIASES` in `config.py` maps known UF codes to building names:

```python
UF_BUILDING_ALIASES = {
    "LIT": "Little Hall",
}
```

`LIT 101` therefore searches for `Little Hall, Gainesville, FL`. Add verified
code/name pairs to extend this dictionary. Codes match case-insensitively as
whole building names after room removal; unknown codes and longer words are
unchanged. Explicit addresses still take priority, and UF aliases are skipped
for explicitly identified non-Gainesville cities. This changes only search
preparation, not source text, coordinates, or candidate validation. It makes no
additional Gemini or fallback Places calls. GatorConnect's per-run cache shares
expanded/full-name queries, and dictionary changes invalidate saved revisions.

The Google resolver checks up to five candidates in one Text Search request.
It accepts exactly one physical place with valid numeric coordinates and a
matching source address/venue/locality, even when other unrelated results were
returned. When several names match a venue search, the only exact building-name
match is preferred over broader listings (for example, `Weimer Hall` over
`College of Journalism and Communications Weimer Hall`). Case/punctuation and
UF campus labels are normalized; two equally exact matches remain ambiguous.
This preference cannot override city/coordinate validation or street-address
conflicts. Diagnostics record the selection reason. Remaining tied matches, or a next-page token indicating unseen
results, stay ambiguous. Malformed candidates leave coordinates unresolved
rather than creating a false unique match. A provider change cannot guarantee coordinates for
missing or genuinely ambiguous venues. `enrichment_status: complete` concerns
Gemini; check `location_status` separately for location success. Successful
results identify `location_provider: "google_places"`.

Each event also includes `location_diagnostics`: the query, candidate names and
addresses, whether each matched, its acceptance/rejection reason, and whether
the response was truncated. This explains null coordinates without logging API
keys, headers, raw HTTP errors, or pagination tokens. Skipped lookups have a null
query and no candidates. Reused lookups retain their original query diagnostics.

Gemini is instructed to exclude officer introductions and recaps with incidental
invitations, while keeping genuine announcements with incomplete details. A
clearly applicable year printed elsewhere on the same flyer can complete a date
(for example, `FALL 2026 SOCCER SOCIAL` and `October 15th`). Publication dates,
and unrelated officer years cannot supply an event year. If no year appears in
the source, Python now uses the computer/server's current year for a supported
month/day (for example, `October 21st` or US-format `10/21`). It marks the event
with `date_year_inferred: true` and a review warning. Explicit years are retained;
vague dates, conflicting years, or invalid calendar dates remain unresolved.
This policy also applies to old posts: it uses the run year, not the posting year.
Python cannot establish whether a flyer header semantically applies to an event.
General club activity catalogs should return no events. Gemini classifies
announcements explicitly, and a narrow Python fallback also drops the observed
ACM activity-list promotions without discarding genuine TBA announcements.
`supporting_text` should be one verbatim excerpt from either the caption or OCR,
not joined snippets; unverifiable quotes keep their review warning. OCR itself
comes from Gemini, so validation is a consistency check, not independent proof.
Changes to the extractor/validator invalidate extraction fingerprints: the next
run can require fresh Gemini calls instead of reusing an old prompt's results.

Old maps.co location caches and cooldowns are ignored. Google lookup reuse is
in memory for the current run; no separate durable Google location cache is
created. Existing event snapshots, duplicate tracking, extraction reuse, and
refresh scheduling continue. Switching providers changes the revision
fingerprint, so the first run may repeat Gemini extraction for selected posts.
The default output still emits only new/changed posts; use `--include-unchanged`
to display all selected saved results.

Page dates and locations take precedence over conflicting Gemini values, with
review warnings. Source timestamps retain their explicit offsets in
`source_details`; these source timestamps are not rewritten. Extracted dates
without a year use the marked current-year fallback described above. Persistent
GatorConnect revisions refresh at New Year so inferred dates cannot remain
silently tied to the previous year. Instagram's raw extraction cache is
revalidated each run, including application of the current-year rule.
The organization contact address and the site's existing coordinates are not
used as substitutes for the event location.

Progress is written to stderr and JSON to stdout. In default mode the JSON is
the frontend array, with counters/rejections on stderr; `--raw-output` prints
the rich envelope described in this section. Exit codes retain the existing
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
