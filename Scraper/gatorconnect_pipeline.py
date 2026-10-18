"""Connect public event collection, shared Gemini extraction, and geocoding."""

import json
import os
import re
import sys
import hashlib
import time
from pathlib import Path

if __package__:
    from . import config
    from .gatorconnect_state import GatorConnectState
    from .config import GATORCONNECT_MEDIA_HOSTS, MAX_IMAGE_BYTES, MAX_IMAGES
    from .event_validator import normalized, validate_extraction
    from .gatorconnect_scraper import collect_gatorconnect, parse_start
    from .gemini_extractor import extract_events
    from .location_resolver import PlacesResolver
    from .image_utils import download_image
    from .runtime_utils import ScraperError, error_record
else:
    import config
    from gatorconnect_state import GatorConnectState
    from config import GATORCONNECT_MEDIA_HOSTS, MAX_IMAGE_BYTES, MAX_IMAGES
    from event_validator import normalized, validate_extraction
    from gatorconnect_scraper import collect_gatorconnect, parse_start
    from gemini_extractor import extract_events
    from location_resolver import PlacesResolver
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


def fingerprint(value):
    """Stable JSON fingerprints distinguish source edits from another run."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def revision_key(post):
    """Source changes, extraction rules, model, and tags invalidate saved work."""
    code = hashlib.sha256()
    for filename in ("gemini_extractor.py", "event_validator.py", "gatorconnect_pipeline.py", "location_resolver.py"):
        code.update(Path(__file__).with_name(filename).read_bytes())
    return fingerprint([post, os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
                        config.EVENT_TAGS, config.GATORCONNECT_USE_GEMINI, code.hexdigest()])


def source_fallback(fields, caption, warning):
    """Keep an approved page's facts even when optional AI enrichment is unavailable."""
    raw = {**fields, "Tags": [], "venue": fields.get("location"),
           "supporting_text": fields.get("title")}
    extracted = validate_extraction({"image_text": "", "events": [raw]}, caption, source_type="gatorconnect")
    if warning:
        event = extracted["events"][0]
        event["validation_warnings"].append(warning)
        event["validation_status"] = "needs_review"
    return extracted


def process_gatorconnect_post(post, resolver, *, store=None):
    """Reuse successful extraction independently of image/geocoding retry state.

    Source IDs identify events, while fingerprints identify revisions. A failed
    enrichment is never marked complete, even when we can return source facts.
    """
    fields = source_fields(post)
    caption = source_caption(post, fields)
    source_key = revision_key(post)
    state_key = "event:" + post["source_event_id"]
    previous = (store.get(state_key) or {}) if store else {}
    same_source = previous.get("source_key") == source_key
    now = time.time()
    gemini_cooldown = (store.get("cooldown:gemini") or {}) if store else {}
    provider_paused = gemini_cooldown.get("until", 0) > now
    images, total_bytes, errors = [], 0, []
    urls = post.get("image_urls", [])
    if not isinstance(urls, list) or len(urls) > MAX_IMAGES:
        raise ScraperError("download", "image_count", "Event contains too many flyer images.")
    if same_source and previous.get("extraction"):
        try:
            validate_extraction(previous["extraction"], caption, source_type="gatorconnect")
        except ScraperError:
            previous["extraction"] = None
    recent_images = bool(same_source and previous.get("extraction")
                         and previous.get("images_until", 0) > now)
    # Rechecking an unchanged URL periodically catches replaced image bytes.
    # A failed download never advances this timestamp, so it remains retryable.
    if (config.GATORCONNECT_USE_GEMINI and not recent_images
            and (not provider_paused or previous.get("extraction"))):
        for url in dict.fromkeys(urls):
            try:
                data, mime = download_image(url, MAX_IMAGE_BYTES - total_bytes,
                                            allowed_hosts=GATORCONNECT_MEDIA_HOSTS)
                total_bytes += len(data)
                images.append((data, mime))
            except Exception as error:
                errors.append({**error_record(error, "download"), "post_url": post["post_url"]})

    content_key = (previous.get("content_key") if recent_images else fingerprint(
        [source_key, [(hashlib.sha256(data).hexdigest(), mime) for data, mime in images]]))
    extraction_ok = False
    reused = False
    extracted = None
    images_until = previous.get("images_until", 0) if recent_images else now + config.GATORCONNECT_IMAGE_RECHECK_SECONDS
    if errors or (provider_paused and not recent_images and not images and urls):
        images_until = 0

    if not config.GATORCONNECT_USE_GEMINI:
        extracted = source_fallback(fields, caption, None)
        extraction_ok = True
    elif same_source and previous.get("content_key") == content_key and previous.get("extraction"):
        # This extraction has no 24-hour expiry: matching content and code/model
        # versions are sufficient. Revalidate before trusting persisted data.
        try:
            extracted = validate_extraction(previous["extraction"], caption, source_type="gatorconnect")
            extraction_ok = bool(extracted["events"])
            reused = extraction_ok
        except ScraperError:
            extracted = None

    if extracted is None or not extracted["events"]:
        try:
            if provider_paused:
                raise ScraperError("gemini", "provider_cooldown",
                                   "Gemini enrichment is deferred after an earlier service failure.")
            # Only the durable store handles caching here. A failed/empty result
            # must not get stuck in the shared Instagram cache for 24 hours.
            options = {"use_cache": False} if store else {}
            extracted = extract_events(images, caption, source_type="gatorconnect", enrich=False, **options)
            if not extracted["events"]:
                raise ScraperError("validation", "empty_event_enrichment",
                                   "Gemini returned no event for an approved GatorConnect page.")
            extraction_ok = True
        except Exception as error:
            record = error_record(error, "gemini")
            errors.append({**record, "post_url": post["post_url"]})
            if store and record["code"] in {
                    "authentication", "access_denied", "rate_limit", "service_unavailable",
                    "connection_error", "timeout", "missing_gemini_key", "missing_dependency"}:
                # One provider-wide outage should not trigger paid retries for
                # every remaining event. Known successful extraction still works.
                store.put("cooldown:gemini", {"until": now + config.GATORCONNECT_RETRY_SECONDS})
            extracted = source_fallback(fields, caption,
                "Gemini enrichment unavailable; source details retained and tags left empty. Retry pending.")

    entry = {**previous, "source_key": source_key, "content_key": content_key,
             "extraction": extracted if extraction_ok else None,
             "images_until": images_until, "complete": False, "retry_at": 0}
    if store:
        # Commit extraction before geocoding. A Maps outage or process failure
        # must not force another paid Gemini call on the same successful content.
        store.put(state_key, entry)
    checked = preserve_source(extracted, fields, caption)
    events = [resolver.resolve(event) for event in checked["events"]]
    status = "disabled" if not config.GATORCONNECT_USE_GEMINI else "complete" if extraction_ok else "pending"
    processed = {**post, "caption": caption, "image_text": checked["image_text"],
                 "events": events, "enrichment_status": status}
    if store:
        complete = extraction_ok and not errors and all(
            event.get("location_status") not in {"error", "ambiguous", "not_found"} for event in events)
        next_check = now + config.GATORCONNECT_LOCATION_TTL_SECONDS
        if urls and config.GATORCONNECT_USE_GEMINI:
            next_check = min(next_check, images_until)
        # No maps.co cache is consulted after switching to Google Places.
        # The existing event refresh deadline controls when a saved output is
        # processed again; the Places resolver shares lookups only within a run.
        entry.update(processed=processed, complete=complete, next_check=next_check,
                     retry_at=0 if complete else now + config.GATORCONNECT_RETRY_SECONDS,
                     reused_extraction=reused)
        store.put(state_key, entry)
    return processed, errors


def scrape_gatorconnect(*, include_unchanged=False):
    """Emit new/changed records; unchanged or cooling-down revisions skip APIs."""
    # Opening state and acquiring the run lock happens BEFORE collection or paid
    # calls. A broken database never silently falls back to duplicate processing.
    with GatorConnectState() as store:
        collected = collect_gatorconnect()
        result = {"posts": [], "errors": list(collected["errors"]),
                  "warnings": list(collected.get("warnings", [])), "processed_posts": 0,
                  "unchanged_posts": 0, "deferred_posts": 0, "reused_extractions": 0}
        resolver = PlacesResolver()
        try:
            return process_collected(collected, result, resolver, store, include_unchanged)
        finally:
            resolver.close()


def process_collected(collected, result, resolver, store, include_unchanged):
    """Persist revisions while keeping stdout a recoverable, explicit change feed."""
    seen = set()
    for post in collected["posts"]:
        identity = post["source_event_id"]
        if identity in seen:
            continue
        seen.add(identity)
        state_key = "event:" + identity
        previous = store.get(state_key) or {}
        same_source = previous.get("source_key") == revision_key(post)
        due = previous.get("next_check", 0) if previous.get("complete") else previous.get("retry_at", 0)
        if same_source and previous.get("processed") and due > time.time():
            result["unchanged_posts" if previous.get("complete") else "deferred_posts"] += 1
            if include_unchanged:
                result["posts"].append({**previous["processed"], "change_type": "unchanged"})
            continue

        print("Processing selected GatorConnect event revision...", file=sys.stderr)
        try:
            processed, errors = process_gatorconnect_post(post, resolver, store=store)
            result["errors"].extend(errors)
            result["processed_posts"] += 1
            current = store.get(state_key)
            result["reused_extractions"] += int(current.get("reused_extraction", False))
            output_key = fingerprint(processed)
            changed = previous.get("output_key") != output_key
            if changed or include_unchanged:
                change = "updated" if previous.get("output_key") else "new"
                result["posts"].append({**processed, "change_type": change if changed else "unchanged"})
            else:
                result["unchanged_posts"] += 1
            current["output_key"] = output_key
            store.put(state_key, current)
        except Exception as error:
            result["errors"].append({**error_record(error, "processing"), "post_url": post["post_url"]})
            if isinstance(error, ScraperError) and error.stage == "storage":
                break  # No more paid calls after losing durable progress.
    return result
