"""Read public GatorConnect pages in a fresh, signed-out Playwright browser.

The site embeds event details in initialAppState and loads organization event
lists through public JSON requests. We observe those requests while using the
page's pagination, rather than inventing a separate private API integration.
"""

from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import re
import sys
from urllib.parse import parse_qs, urlsplit

if __package__:
    from . import config
    from .runtime_utils import ScraperError, error_record
else:
    import config
    from runtime_utils import ScraperError, error_record


BASE_URL = "https://gatorconnect.ufl.edu"


class PlainText(HTMLParser):
    """Remove markup before sending descriptions to Gemini as source text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value):
    parser = PlainText()
    parser.feed(value if isinstance(value, str) else "")
    return " ".join(" ".join(parser.parts).split())


def organization_url(value):
    """Only configured public UF organization profiles are navigation targets."""
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.netloc != "gatorconnect.ufl.edu"
            or parsed.query or parsed.fragment
            or not re.fullmatch(r"/organization/[\w-]+/?", parsed.path)):
        raise ScraperError("settings", "organization_url",
                           "Use https://gatorconnect.ufl.edu/organization/CLUB profile URLs.")
    return value.rstrip("/")


def parse_start(value):
    """Only explicit, timezone-aware timestamps can determine upcoming order."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


def select_events(records, now, days, limit):
    """Deduplicate and sort before any flyer download or Gemini invocation.

    Undated public candidates come after known upcoming events, so they can be
    reviewed without inventing a year. Past/out-of-window dated events are gone.
    """
    unique = {}
    end = now + timedelta(days=days)
    for record in records:
        identity = str(record.get("id", ""))
        if (not identity.isdigit() or record.get("visibility") != "Public"
                or record.get("status") != "Approved"):
            continue
        start = parse_start(record.get("startsOn"))
        if start is not None and not now <= start < end:
            continue
        unique.setdefault(identity, record)
    latest = datetime.max.replace(tzinfo=timezone.utc)
    return sorted(unique.values(), key=lambda r: (
        parse_start(r.get("startsOn")) or latest, str(r["id"])))[:limit]


def collect_listing(page, url, *, warnings=None):
    """Observe only event-search responses for this organization's listing."""
    records = []
    failures = []

    def capture(response):
        parsed = urlsplit(response.url)
        if (parsed.netloc != "gatorconnect.ufl.edu"
                or parsed.path != "/api/discovery/event/search"):
            return
        # Only listen while this organization's listing page is active. Explicit
        # organization filters prevent accidentally capturing a global feed.
        params = parse_qs(parsed.query)
        if not any(key.startswith("organizationIds") for key in params):
            return
        try:
            payload = response.json()
            if response.status != 200 or not isinstance(payload.get("value"), list):
                raise ValueError()
            records.extend(item for item in payload["value"] if isinstance(item, dict))
        except Exception:
            failures.append("The public organization event list could not be read.")

    page.on("response", capture)
    try:
        navigate(page, url + "/events")
        for index in range(config.GATORCONNECT_MAX_PAGES):
            # A missing button means the list is complete, including empty lists.
            more = page.get_by_role("button", name=re.compile(r"^load more$", re.I))
            if more.count() == 0 or not more.first.is_visible():
                break
            if (index + 1 == config.GATORCONNECT_MAX_PAGES
                    or len(records) >= config.GATORCONNECT_MAX_CANDIDATES):
                raise ScraperError("collection", "discovery_limit",
                                   "Organization listing exceeded its discovery budget; increase the page/candidate limits.")
            before = len(records)
            # Waiting on the specific response avoids reusing the page's earlier
            # network-idle state before the click's fetch has actually started.
            with page.expect_response(lambda r: urlsplit(r.url).path == "/api/discovery/event/search") as pending:
                more.first.click()
            pending.value.body()
            expected = [str(item.get("id")) for item in records[before:]]
            page.wait_for_function("""ids => {
                const links = new Set([...document.querySelectorAll('a[href]')]
                    .map(a => new URL(a.href).pathname));
                return ids.every(id => links.has('/event/' + id));
            }""", arg=expected)
            if len(records) <= before:
                raise ScraperError("collection", "pagination_stalled",
                                   "GatorConnect pagination returned no new records.")
        body = page.locator("body").inner_text()
        if failures or (not records and not re.search(r"no (?:upcoming )?events|0 (?:out of|events)|no results", body, re.I)):
            raise ScraperError("collection", "listing_changed",
                               "Could not verify the public event listing; its page format may have changed.")
        return records
    except Exception as error:
        if not records:
            raise
        # A later failed page must not erase the public records already read.
        # Do not claim that this partial list contains the earliest events overall.
        warning = {**error_record(error, "collection"), "organization_url": url,
                   "partial_results": True,
                   "message": "Discovery incomplete; returning events collected before the limit or failure."}
        if warnings is not None:
            warnings.append(warning)
        else:
            print(warning["message"], file=sys.stderr)
        return records
    finally:
        page.remove_listener("response", capture)


def navigate(page, url):
    """Never follow a sign-in page or mistake an access failure for no events."""
    response = page.goto(url, wait_until="networkidle")
    if not response or response.status >= 400 or not page.url.startswith(BASE_URL + "/"):
        raise ScraperError("collection", "page_unavailable",
                           "Public GatorConnect page unavailable or redirected to sign-in.")


def read_detail(page, record, org_url):
    """Read the actual event object, excluding recommendations and club contacts."""
    event_url = BASE_URL + "/event/" + str(record["id"])
    navigate(page, event_url)
    data = page.evaluate("() => window.initialAppState?.preFetchedData?.event ?? null")
    if (not isinstance(data, dict) or str(data.get("id")) != str(record["id"])
            or data.get("visibility") != "Public"
            or (data.get("state") or {}).get("status") != "Approved"):
        raise ScraperError("collection", "event_unavailable",
                           "Event is restricted, unapproved, or its public data format changed.")

    address = data.get("address") or {}
    if not isinstance(address, dict):
        address = {}
    # Never use organization contact addresses or existing website coordinates
    # as event locations. Keep only fields belonging to this event's address.
    structured = {
        "title": plain_text(data.get("name")),
        "description": plain_text(data.get("description")),
        "starts_on": data.get("startsOn"),
        "ends_on": data.get("endsOn"),
        "location": plain_text(address.get("name")) or None,
        "address_text": plain_text(address.get("address")) or None,
        "city_text": ", ".join(filter(None, (address.get("city"), address.get("state")))) or None,
        "online_location": address.get("onlineLocation"),
        "full_address": None,
    }
    if all(address.get(key) for key in ("line1", "city", "state", "zip")):
        structured["full_address"] = ", ".join(
            str(address[key]) for key in ("line1", "city", "state", "zip"))
    image = data.get("imageUrl")
    return {
        "source_type": "gatorconnect",
        "source_event_id": str(data["id"]),
        "post_url": event_url,
        "organization_url": org_url,
        "organization_id": record.get("organizationId"),
        "organization_name": record.get("organizationName"),
        # imageUrl may contain the site's default event graphic when imagePath
        # is empty. Only an actual uploaded flyer belongs in the Gemini call.
        "image_urls": [image] if data.get("imagePath") and isinstance(image, str) and image else [],
        "source_details": structured,
    }


def collect_gatorconnect(organization_urls=None, *, now=None):
    """Return the same posts/errors envelope as the Instagram collector."""
    urls = config.GATORCONNECT_ORGANIZATION_URLS if organization_urls is None else organization_urls
    if not isinstance(urls, list) or not urls or len(urls) > config.MAX_CLUBS:
        raise ScraperError("settings", "gatorconnect_organizations",
                           "Set GATORCONNECT_ORGANIZATION_URLS to 1-20 public organization URLs in config.py.")
    urls = list(dict.fromkeys(organization_url(url) for url in urls))
    limit = config.GATORCONNECT_EVENTS_PER_ORG
    if type(limit) is not int or not 1 <= limit <= 5:
        raise ScraperError("settings", "gatorconnect_limit", "GatorConnect currently allows 1-5 events per organization.")
    if type(config.GATORCONNECT_DAYS_AHEAD) is not int or config.GATORCONNECT_DAYS_AHEAD < 1:
        raise ScraperError("settings", "gatorconnect_window", "GATORCONNECT_DAYS_AHEAD must be positive.")

    from playwright.sync_api import sync_playwright

    now = now or datetime.now(timezone.utc)
    result = {"posts": [], "errors": [], "warnings": []}
    seen = set()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            # Fresh context means no personal browser cookies or UF login.
            context = browser.new_context()
            # Do not download flyers while discovering/sorting candidates.
            context.route("**/*", lambda route: route.abort()
                          if route.request.resource_type in {"image", "media", "font"}
                          else route.continue_())
            page = context.new_page()
            page.set_default_timeout(config.GATORCONNECT_PAGE_SECONDS * 1000)
            for url in urls:
                print(f"Collecting public GatorConnect events: {url}", file=sys.stderr)
                try:
                    records = collect_listing(page, url, warnings=result["warnings"])
                    # Shared IDs already collected must not consume this club's
                    # five slots and hide its next distinct event.
                    records = [record for record in records if str(record.get("id")) not in seen]
                    selected = select_events(records, now, config.GATORCONNECT_DAYS_AHEAD, limit)
                    for record in selected:
                        identity = str(record["id"])
                        if identity in seen:
                            continue
                        try:
                            post = read_detail(page, record, url)
                            # Recheck a date edited between the list and detail reads.
                            start = parse_start(post["source_details"]["starts_on"])
                            if start and not now <= start < now + timedelta(days=config.GATORCONNECT_DAYS_AHEAD):
                                continue
                            result["posts"].append(post)
                            seen.add(identity)
                        except Exception as error:
                            result["errors"].append({**error_record(error, "collection"),
                                                     "source_event_id": identity, "organization_url": url})
                except Exception as error:
                    result["errors"].append({**error_record(error, "collection"), "organization_url": url})
        finally:
            browser.close()
    return result
