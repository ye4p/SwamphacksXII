"""Connect public event collection, shared Gemini extraction, and geocoding."""

import json
import os
import re
import sys

if __package__:
    from .config import GATORCONNECT_MEDIA_HOSTS, MAX_IMAGE_BYTES, MAX_IMAGES
    from .event_validator import normalized, validate_extraction
    from .gatorconnect_scraper import collect_gatorconnect, parse_start
    from .gemini_extractor import extract_events
    from .geocode_resolver import GeocodeResolver
    from .image_utils import download_image
    from .runtime_utils import ScraperError, error_record
else:
    from config import GATORCONNECT_MEDIA_HOSTS, MAX_IMAGE_BYTES, MAX_IMAGES
    from event_validator import normalized, validate_extraction
    from gatorconnect_scraper import collect_gatorconnect, parse_start
    from gemini_extractor import extract_events
    from geocode_resolver import GeocodeResolver
    from image_utils import download_image
    from runtime_utils import ScraperError, error_record


def source_fields(post):
    """Translate explicit page details to extraction fields without guessing dates."""
    details = post["source_details"]
    start = parse_start(details.get("starts_on"))
    end = parse_start(details.get("ends_on"))
    fields = {key: details.get(key) for key in (
        "title", "description", "location", "address_text", "city_text", "full_address")}
    fields["date"] = start.date().isoformat() if start else None
    fields["date_text"] = fields["date"]
    fields["time"] = start.strftime("%I:%M %p") if start else None
    if start and end:
        fields["time"] += " - " + end.strftime("%I:%M %p")

    location = fields["location"] or ""
    vague = re.fullmatch(r"(?:tba|tbd|on campus|to be announced|room\s+\w+)", location, re.I)
    online_name = re.fullmatch(r"(?:online|virtual|zoom|microsoft teams|google meet)", location, re.I)
    if fields["address_text"] or (location and not vague and not online_name):
        fields["location_kind"] = "physical"
    elif details.get("online_location") or online_name:
        fields["location_kind"] = "online"
    else:
        fields["location_kind"] = "missing"
    return fields


def source_caption(post, fields):
    """Use only this event's explicit data, including stable identity for caching."""
    # Render source fields as readable lines too, so the validator can check
    # exact excerpts without JSON escape sequences changing their whitespace.
    lines = [f"GatorConnect event: {post['post_url']}",
             f"Organization: {post.get('organization_name') or ''}"]
    lines.extend(f"{key}: {value}" for key, value in fields.items() if value is not None)
    lines.append("Original source details: " + json.dumps(post["source_details"], ensure_ascii=False))
    return "\n".join(lines)


def preserve_source(extracted, fields, caption):
    """Source values win conflicts; retain warnings rather than silently replacing."""
    if len(extracted["events"]) > 1:
        raise ScraperError("validation", "multiple_page_events",
                           "One GatorConnect detail page produced multiple events; review required.")
    events = []
    for event in extracted["events"]:
        merged = dict(event)
        warnings = list(event.get("validation_warnings", []))
        for field, value in fields.items():
            if value is None or value == "":
                continue
            old = merged.get(field)
            if old is not None and normalized(str(old)) != normalized(str(value)):
                warnings.append(f"{field}: Gemini disagreed with the page; explicit page value retained.")
                if field in {"location", "address_text", "city_text"}:
                    # Do not use an expanded name tied to a conflicting flyer.
                    merged["venue"] = None
                    merged["full_address"] = None
            merged[field] = value

        # If the page has no location, allow supported flyer evidence. A page
        # that explicitly says online, however, must not become a physical event.
        if fields["location_kind"] == "missing":
            merged["location_kind"] = event.get("location_kind", "missing")
        checked = validate_extraction({"image_text": extracted["image_text"], "events": [merged]},
                                      caption, source_type="gatorconnect")["events"][0]
        if not fields["date"]:
            warnings.append("source date: missing or timezone-ambiguous; upcoming window could not be verified.")
        # Remove obsolete 'missing' notices once an explicit source field fills it.
        warnings = [warning for warning in warnings if not any(
            warning == f"{key}: missing or uncertain." and checked.get(key)
            for key in ("title", "date", "time", "location"))]
        checked["validation_warnings"] = list(dict.fromkeys(warnings + checked["validation_warnings"]))
        checked["validation_status"] = "needs_review" if checked["validation_warnings"] else "checked"
        events.append(checked)
    return {**extracted, "events": events}


def process_gatorconnect_post(post, resolver):
    """One selected event gets one Gemini call, followed by its own geocoder."""
    fields = source_fields(post)
    caption = source_caption(post, fields)
    images, total_bytes, errors = [], 0, []
    urls = post.get("image_urls", [])
    if not isinstance(urls, list) or len(urls) > MAX_IMAGES:
        raise ScraperError("download", "image_count", "Event contains too many flyer images.")
    for url in dict.fromkeys(urls):
        try:
            data, mime = download_image(url, MAX_IMAGE_BYTES - total_bytes,
                                        allowed_hosts=GATORCONNECT_MEDIA_HOSTS)
            total_bytes += len(data)
            images.append((data, mime))
        except Exception as error:
            # A failed optional flyer does not erase readable event page text.
            errors.append({**error_record(error, "download"), "post_url": post["post_url"]})

    extracted = extract_events(images, caption, source_type="gatorconnect", enrich=False)
    checked = preserve_source(extracted, fields, caption)
    events = [resolver.resolve(event) for event in checked["events"]]
    return {**post, "caption": caption, "image_text": checked["image_text"], "events": events}, errors


def scrape_gatorconnect():
    """Keep the posts/errors envelope and isolate failures to individual events."""
    if not os.getenv("GEMINI_API_KEY"):
        raise ScraperError("settings", "missing_gemini_key", "Set GEMINI_API_KEY before collecting events.")
    # Fail before browser collection when the extraction SDK is missing.
    from google import genai  # noqa: F401

    collected = collect_gatorconnect()
    result = {"posts": [], "errors": list(collected["errors"]), "processed_posts": 0}
    resolver = GeocodeResolver()
    try:
        for post in collected["posts"]:
            print("Extracting selected GatorConnect event...", file=sys.stderr)
            try:
                processed, errors = process_gatorconnect_post(post, resolver)
                result["errors"].extend(errors)
                result["processed_posts"] += 1
                if processed["events"]:
                    result["posts"].append(processed)
            except Exception as error:
                result["errors"].append({**error_record(error, "processing"),
                                         "post_url": post["post_url"]})
    finally:
        resolver.close()
    return result
