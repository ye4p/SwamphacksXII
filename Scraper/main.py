"""Collect Instagram posts with Apify and extract event details with Gemini.

Install: python -m pip install "apify-client>=3,<4" google-genai requests
Run from the project folder: python Scraper/main.py
Test Gemini: python Scraper/main.py --images flyer.jpg --caption "Club meeting"
Location lookup: set GOOGLE_MAPS_API_KEY with Places API (New) enabled."""

import argparse  # Reads terminal options such as --images.
import json  # Turns Python dictionaries into JSON text.
import sys
from pathlib import Path  # Reads saved image files into memory.

if __package__:
    from .gemini_extractor import extract_events
    from .pipeline import scrape_events
else:
    from gemini_extractor import extract_events
    from pipeline import scrape_events


def main():
    """Read command-line options, run the requested mode, and print JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", nargs="+", help="Saved images from ONE post")
    parser.add_argument("--caption", default="", help="That post's caption")
    args = parser.parse_args()
    if args.images:
        # This mode tests Gemini without contacting Instagram.
        try:
            images = []
            mime_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                          ".png": "image/png", ".webp": "image/webp"}
            for filename in args.images:
                path = Path(filename)
                if path.suffix.lower() not in mime_types:
                    raise ValueError("Use JPEG, PNG, or WebP images.")
                images.append((path.read_bytes(), mime_types[path.suffix.lower()]))
            result = extract_events(images, args.caption)
        except (OSError, ValueError, RuntimeError, ImportError) as error:
            print(json.dumps({"events": [], "errors": [str(error)]}))
            sys.exit(1)
    else:
        result = scrape_events()
    print(json.dumps(result, indent=2, ensure_ascii=True))


# Only run when this file is executed directly, rather than imported.
if __name__ == "__main__":
    main()
