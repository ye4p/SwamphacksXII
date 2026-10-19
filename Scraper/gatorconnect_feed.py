"""Traditional HTTP/JSON scraper for the public GatorConnect /events feed.

No browser, model, or OCR is used. Google Places resolves missing coordinates.
The default query follows
GatorConnect's public upcoming listing, without a local date or organization cap.
"""
import math
import re
import sys
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config
from .gatorconnect_scraper import plain_text, parse_start


def valid_coordinates(event):
    return all(type(event.get(key)) in (int, float)
               and math.isfinite(event[key]) and abs(event[key]) <= bound
               for key, bound in (("longitude", 180), ("latitude", 90)))


def geocode_events(events, *, resolver=None, progress=True):
    """Return only mappable events and explicit rejection diagnostics.

    Reuse the existing Places name/address matching, locality guards, and
    per-run cache. Never accept the top result solely because it ranked first.
    """
    from .location_resolver import PlacesResolver
    own_resolver = resolver is None
    resolver = resolver or PlacesResolver()
    accepted, skipped, locations = [], [], {}
    try:
        for index, event in enumerate(events):
            if valid_coordinates(event):
                accepted.append(event)
                continue
            venue = event.get("address") or ""
            if venue not in locations:
                online = re.search(r"\b(?:zoom|virtual|online|teams\.microsoft)\b|https?://", venue, re.I)
                vague = re.fullmatch(r"\s*(?:tba|tbd|to be announced|on campus)?\s*", venue, re.I)
                location = {
                    "location": venue, "venue": venue,
                    "location_kind": "online" if online else "missing" if vague else "physical",
                    "address_text": venue if re.match(r"^\d+\s+\S", venue) else None,
                }
                locations[venue] = resolver.resolve(location)
            resolved = locations[venue]
            if resolved.get("location_status") == "resolved" and valid_coordinates(resolved):
                accepted.append({**event, "latitude": resolved["latitude"],
                                 "longitude": resolved["longitude"],
                                 "address": resolved.get("address") or venue,
                                 "payload": {**event["payload"], "source_venue": venue,
                                             "location_status": "resolved",
                                             "location_provider": resolved.get("location_provider")}})
            else:
                skipped.append({"source_event_id": event["payload"]["source_event_id"],
                                "venue": venue, "status": resolved.get("location_status"),
                                "reason": resolved.get("location_warning"),
                                "error_code": resolved.get("location_error_code")})
            if progress and (index + 1) % 100 == 0:
                print(f"Geocoded {index + 1}/{len(events)} events: "
                      f"{len(accepted)} mappable, {len(skipped)} skipped", file=sys.stderr)
        if progress:
            print(f"Geocoding complete: {len(accepted)} mappable, {len(skipped)} skipped", file=sys.stderr)
        return {"events": accepted, "skipped": skipped}
    finally:
        if own_resolver:
            resolver.close()


def collect_mappable_events():
    return geocode_events(collect_events())


def parse_event(record):
    """Map explicit source fields to database fields; never invent coordinates."""
    identity = str(record.get("id", ""))
    start = parse_start(record.get("startsOn"))
    title = plain_text(record.get("name"))
    if not identity.isdigit() or not start or not title:
        raise ValueError(f"Event {identity!r} is missing a valid ID, aware date, or title")
    coordinates = [record.get("longitude"), record.get("latitude")]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) and abs(v) <= bound
               for v, bound in zip(coordinates, (180, 90))):
        coordinates = [None, None]
    labels = {record.get("theme")}
    for key in ("categoryNames", "benefitNames"):
        labels.update(record.get(key) or [])
    url = f"https://gatorconnect.ufl.edu/event/{identity}"
    return {
        "timestamp": start.isoformat(), "title": title,
        "description": plain_text(record.get("description")),
        "address": plain_text(record.get("location")) or None,
        "longitude": coordinates[0], "latitude": coordinates[1],
        "organization_name": plain_text(record.get("organizationName")) or None,
        "payload": {
            "source": "gatorconnect", "source_event_id": identity,
            "source_url": url, "source_organization_id": record.get("organizationId"),
            "ends_on": record.get("endsOn"), "image_path": record.get("imagePath"),
            "notes": f"Source: {url}",
            "tags": sorted(tag for tag, names in config.GATORCONNECT_GLOBAL_TAG_MAP.items()
                           if labels.intersection(names)),
            "location_status": "source" if coordinates[0] is not None else "unavailable",
        },
    }


def collect_events(*, session=None, page_size=config.GATORCONNECT_GLOBAL_TAKE, max_pages=1000, pause=0.2):
    """Fetch every page; fail closed on malformed/incomplete/stalled discovery.

    A short page isn't necessarily the end: the server can cap requested sizes.
    Counts and distinct IDs must agree before any database writes are allowed.
    """
    if not 1 <= page_size <= 2000 or max_pages < 1:
        raise ValueError("Invalid pagination limits")
    own_session = session is None
    session = session or requests.Session()
    if own_session:
        retry = Retry(total=4, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods={"GET"}, respect_retry_after_header=True)
        session.mount("https://", HTTPAdapter(max_retries=retry))
    records = {}
    skip = 0
    expected = None
    try:
        for _ in range(max_pages):
            response = session.get(config.GATORCONNECT_GLOBAL_URL,
                                   params={"take": page_size, "skip": skip,
                                           "orderByField": "startsOn",
                                           "orderByDirection": "ascending"},
                                   timeout=config.GATORCONNECT_GLOBAL_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
                raise ValueError("GatorConnect feed format changed")
            count = payload.get("@odata.count")
            if type(count) is not int or count < 0:
                raise ValueError("GatorConnect feed lacks a valid total count")
            if expected is None:
                expected = count
            elif count != expected:
                raise ValueError("GatorConnect listing changed during pagination; retry the import")
            batch = payload["value"]
            before = len(records)
            for record in batch:
                if not isinstance(record, dict) or not str(record.get("id", "")).isdigit():
                    raise ValueError("Malformed GatorConnect record")
                records[str(record["id"])] = record
            if len(records) == expected:
                return [parse_event(r) for r in records.values()
                        if r.get("visibility") == "Public" and r.get("status") == "Approved"]
            if not batch or len(records) == before or len(records) > expected:
                raise ValueError("Incomplete or stalled GatorConnect pagination")
            skip += len(batch)
            time.sleep(pause)
        raise ValueError("GatorConnect page safety limit reached; no events imported")
    finally:
        if own_session:
            session.close()


async def import_events(db):
    """Run blocking HTTP off the event loop, then atomically persist the snapshot."""
    import asyncio
    result = await asyncio.to_thread(collect_mappable_events)
    return await db.import_gatorconnect_events(result["events"])
