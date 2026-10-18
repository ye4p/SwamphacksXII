"""Download post images and connect Apify collection to Gemini extraction."""

import os  # Reads API keys from environment variables.
from datetime import date
import sys  # Sends progress messages to stderr, separate from JSON output.

if __package__:
    from .gemini_extractor import extract_events
    from .instagram_scraper import collect_posts
    from .config import MAX_IMAGE_BYTES, MAX_IMAGES
    from .image_utils import download_image
    from .runtime_utils import ScraperError, error_record
    from .database import fetch_events
else:
    from gemini_extractor import extract_events
    from instagram_scraper import collect_posts
    from config import MAX_IMAGE_BYTES, MAX_IMAGES
    from image_utils import download_image
    from runtime_utils import ScraperError, error_record
    from database import fetch_events


def process_post(post):
    """Download post photos, transcribe with OCR.space, then extract with Gemini."""
    urls = post.get("image_urls")
    if not isinstance(urls, list) or not 1 <= len(urls) <= MAX_IMAGES:
        raise ScraperError("download", "image_count", f"Expected 1-{MAX_IMAGES} photo URLs.")
    images, total_bytes = [], 0
    for url in dict.fromkeys(urls):
        data, mime = download_image(url, MAX_IMAGE_BYTES - total_bytes)
        total_bytes += len(data)
        images.append((data, mime))

    # One request per post keeps carousel images and their caption together.
    extracted = extract_events(images, caption=post.get("caption", ""))
    if (not isinstance(extracted, dict)
            or not isinstance(extracted.get("image_text"), str)
            or not isinstance(extracted.get("events"), list)):
        raise ScraperError("validation", "invalid_structure", "Gemini returned an unexpected JSON structure.")
    # Retain the original metadata; Gemini supplies only the extracted content.
    return {**post, "image_text": extracted["image_text"],
            "events": extracted["events"]}



def scrape_events(handles=None, *, progress=True, use_database=True):
    """Connect collection to extraction, preserving errors from both steps."""
    # Check setup before starting a potentially billable Apify run.
    if not os.getenv("GEMINI_API_KEY"):
        return {"posts": [], "errors": [{"stage": "settings", "code": "missing_gemini_key",
                "message": "Set GEMINI_API_KEY in your terminal first."}]}
    if not os.getenv("OCR_SPACE_API_KEY"):
        return {"posts": [], "errors": [{"stage": "settings", "code": "missing_ocr_key",
                "message": "Set OCR_SPACE_API_KEY in your terminal first."}]}
    try:
        import requests
        from google import genai
    except ImportError:
        return {"posts": [], "errors": [{"stage": "settings", "code": "missing_dependency",
                "message": "Install dependencies: python -m pip install requests google-genai"}]}

    # The server wrapper supplies its own database snapshot and deduplicates
    # exact timestamps later; it must not also use this legacy same-day filter.
    db_events = fetch_events(date.today().isoformat()) if use_database else []
    db_keys = set()
    for event in db_events:
        club = event.get("club") or event.get("organization") or event.get("organization_handle")
        db_keys.add((str(club).casefold() if club is not None else None, event.get("date")))
    scraped = collect_posts(handles, progress=progress)
    result = {"posts": [], "errors": list(scraped["errors"]), "processed_posts": 0}
    seen = set()
    for post in scraped["posts"]:
        identity = post.get("post_url")
        if identity and identity in seen:
            continue
        if identity:
            seen.add(identity)
        if progress:
            print("Extracting events from collected post...", file=sys.stderr)
        try:
            processed = process_post(post)
            result["processed_posts"] += 1
            filtered = []
            for event in processed.get("events", []):
                key = (str(post.get("organization_handle")).casefold(), event.get("date"))
                if key in db_keys:
                    continue
                filtered.append(event)
            processed["events"] = filtered
            if processed["events"]:
                result["posts"].append(processed)
        except Exception as error:
            # Keep safe diagnostics and continue even if a single post fails.
            result["errors"].append({**error_record(error, "processing"),
                "post_url": post.get("post_url"),
                "organization_handle": post.get("organization_handle")})
    return result

