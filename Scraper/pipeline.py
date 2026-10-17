"""Download post images and connect Apify collection to Gemini extraction."""

import os  # Reads API keys from environment variables.
import sys  # Sends progress messages to stderr, separate from JSON output.

if __package__:
    from .gemini_extractor import extract_events
    from .instagram_scraper import collect_posts
else:
    from gemini_extractor import extract_events
    from instagram_scraper import collect_posts


def process_post(post):
    """Download one post's photos, then send them together to Gemini."""
    import requests

    images = []
    total_bytes = 0
    for url in post["image_urls"]:
        # Stream downloads so we can stop before exceeding our 10 MB limit.
        with requests.get(url, timeout=30, stream=True) as response:
            response.raise_for_status()
            mime_type = response.headers.get("Content-Type", "")
            mime_type = mime_type.split(";")[0].strip().lower()
            if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
                raise ValueError("Image URL did not return JPEG, PNG, or WebP.")
            data = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                total_bytes += len(chunk)
                if total_bytes > 10 * 1024 * 1024:
                    raise ValueError("Post images exceed the 10 MB request limit.")
                data.extend(chunk)
            if not data:
                raise ValueError("Image URL returned an empty file.")
            images.append((bytes(data), mime_type))

    # One request per post keeps carousel images and their caption together.
    extracted = extract_events(images, caption=post.get("caption", ""))
    if (not isinstance(extracted, dict)
            or not isinstance(extracted.get("image_text"), str)
            or not isinstance(extracted.get("events"), list)):
        raise ValueError("Gemini returned an unexpected JSON structure.")
    # Retain the original metadata; Gemini supplies only the extracted content.
    return {**post, "image_text": extracted["image_text"],
            "events": extracted["events"]}



def scrape_events():
    """Connect collection to extraction, preserving errors from both steps."""
    # Check setup before starting a potentially billable Apify run.
    if not os.getenv("GEMINI_API_KEY"):
        return {"posts": [], "errors": [{"stage": "settings",
                "message": "Set GEMINI_API_KEY in your terminal first."}]}
    try:
        import requests
        from google import genai
    except ImportError:
        return {"posts": [], "errors": [{"stage": "settings",
                "message": "Install dependencies: python -m pip install requests google-genai"}]}

    scraped = collect_posts()
    result = {"posts": [], "errors": list(scraped["errors"])}
    for post in scraped["posts"]:
        print(f"Extracting events from {post['post_url']}...", file=sys.stderr)
        try:
            processed = process_post(post)
            # An empty event list means unrelated content, not a processing error.
            if processed["events"]:
                result["posts"].append(processed)
        except Exception as error:
            # Continue with other posts; never present a partial carousel as complete.
            # Exception text from network libraries may contain signed URLs or keys.
            result["errors"].append({
                "stage": "processing", "post_url": post.get("post_url"),
                "organization_handle": post.get("organization_handle"),
                "message": f"Image download or Gemini extraction failed ({type(error).__name__}).",
            })
    return result

