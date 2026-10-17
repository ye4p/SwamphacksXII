"""Collect Instagram posts with Apify and extract event details with Gemini.

Install: python -m pip install "apify-client>=3,<4" google-genai requests
Run from the project folder: python Scraper/main.py
Test Gemini: python Scraper/main.py --images flyer.jpg --caption "Club meeting"
Location lookup: set GOOGLE_MAPS_API_KEY with Places API (New) enabled."""

import argparse  # Reads terminal options such as --images.
import json  # Turns Python dictionaries into JSON text.
import sys

if __package__:
    from .gemini_extractor import extract_events
    from .pipeline import scrape_events
    from .image_utils import read_local_images
    from .runtime_utils import error_record
else:
    from gemini_extractor import extract_events
    from pipeline import scrape_events
    from image_utils import read_local_images
    from runtime_utils import error_record


def main():
    """Read command-line options, run the requested mode, and print JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", nargs="+", help="Saved images from ONE post")
    parser.add_argument("--caption", default="", help="That post's caption")
    args = parser.parse_args()
    if args.images:
        # This mode tests Gemini without contacting Instagram.
        try:
            images = read_local_images(args.images)
            result = extract_events(images, args.caption)
        except Exception as error:
            result = {"events": [], "errors": [error_record(error, "local_image")]}
    else:
        try:
            result = scrape_events()
        except Exception as error:
            # Unexpected setup/runtime failures still produce machine-readable JSON.
            result = {"posts": [], "errors": [error_record(error, "pipeline")]}
    print(json.dumps(result, indent=2, ensure_ascii=True))
    # Schedulers need a meaningful process status, including degraded Maps results.
    events = result.get("events", []) + [event for post in result.get("posts", [])
                                        for event in post.get("events", [])]
    failed = bool(result.get("errors")) or any(event.get("location_status") == "error" for event in events)
    if failed:
        # A successfully processed non-event also counts as a successful post.
        partial = bool(events or result.get("processed_posts", 0))
        sys.exit(2 if partial else 1)
    # No events, no errors is a successful empty result (exit 0).


# Only run when this file is executed directly, rather than imported.
if __name__ == "__main__":
    main()
