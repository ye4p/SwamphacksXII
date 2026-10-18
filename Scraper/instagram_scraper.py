"""Collect Instagram post metadata and photo URLs through Apify."""

import os  # Reads API keys from environment variables.
import sys  # Sends progress messages to stderr, separate from JSON output.
import re
from datetime import timedelta
from decimal import Decimal

if __package__:
    from .config import CLUB_HANDLES, POSTS_PER_ACCOUNT, APIFY_ACTOR
    from .config import APIFY_RUN_SECONDS, APIFY_MAX_CHARGE_USD, MAX_CLUBS, MAX_POSTS_PER_ACCOUNT
    from .runtime_utils import ScraperError, error_record
else:
    from config import CLUB_HANDLES, POSTS_PER_ACCOUNT, APIFY_ACTOR
    from config import APIFY_RUN_SECONDS, APIFY_MAX_CHARGE_USD, MAX_CLUBS, MAX_POSTS_PER_ACCOUNT
    from runtime_utils import ScraperError, error_record


def get_image_urls(post):
    """Read Apify photo URLs, skipping videos and their thumbnail images."""
    if post.get("type") == "Video":
        return []
    # Carousel children describe individual slides, including their media type.
    children = post.get("childPosts") or []
    if children:
        urls = [child.get("displayUrl") for child in children
                if child.get("type") == "Image"]
    elif post.get("type") == "Image":
        urls = [post.get("displayUrl")]
    else:
        # Do not guess whether an unidentified carousel slide is a video.
        urls = []
    return list(dict.fromkeys(url for url in urls if url))



def collect_posts(handles=None, *, progress=True):
    """Collect post metadata and keep failures alongside successful results."""
    result = {"posts": [], "errors": []}
    # Explicit input never mutates module settings or falls back on an empty list.
    handles = CLUB_HANDLES if handles is None else handles
    if not handles:
        result["errors"].append({"stage": "settings", "message":
                                 "Add club usernames to CLUB_HANDLES first."})
        return result

    if (len(handles) > MAX_CLUBS or type(POSTS_PER_ACCOUNT) is not int
            or not 1 <= POSTS_PER_ACCOUNT <= MAX_POSTS_PER_ACCOUNT
            or any(not isinstance(handle, str) or not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", handle)
                   for handle in handles)):
        result["errors"].append({"stage": "settings", "code": "invalid_config",
            "message": "Check club usernames and configured club/post limits."})
        return result
    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        result["errors"].append({"stage": "settings", "message":
                                 "Set APIFY_API_TOKEN in your terminal first."})
        return result
    # Import here so local Gemini tests do not require the Apify package.
    try:
        from apify_client import ApifyClient
    except ImportError:
        result["errors"].append({"stage": "settings", "message":
                                 "Install Apify: python -m pip install apify-client"})
        return result

    # Do not automatically retry starting a billable job: a lost response may
    # hide an already-started run. Read-only dataset requests can be retried later.
    client = ApifyClient(token, max_retries=1, timeout_max=timedelta(seconds=APIFY_RUN_SECONDS + 15))
    for handle in dict.fromkeys(handles):
        if progress:
            print(f"Collecting posts from @{handle} through Apify...", file=sys.stderr)
        try:
            # Each call starts a hosted job and may consume Apify credits.
            run = client.actor(APIFY_ACTOR).call(run_input={
                "directUrls": [f"https://www.instagram.com/{handle}/"],
                "resultsType": "posts",
                "resultsLimit": POSTS_PER_ACCOUNT,
            }, run_timeout=timedelta(seconds=APIFY_RUN_SECONDS),
                wait_duration=timedelta(seconds=APIFY_RUN_SECONDS + 5),
                max_total_charge_usd=Decimal(APIFY_MAX_CHARGE_USD),
                max_items=POSTS_PER_ACCOUNT, restart_on_error=False, logger=None,
                timeout=timedelta(seconds=APIFY_RUN_SECONDS + 15))
            # Apify SDK 3 returns a Run object, accessed with dots, not .get().
            if not run or run.status != "SUCCEEDED":
                status = run.status if run else "UNKNOWN"
                result["errors"].append({"stage": "collection",
                    "code": "run_incomplete",
                    "organization_handle": handle,
                    "message": f"Apify run did not succeed: {status}"})
                continue
            # A dataset is Apify's stored list of results for this run.
            for post in client.dataset(run.default_dataset_id).iterate_items(limit=POSTS_PER_ACCOUNT, timeout=timedelta(seconds=30)):
                if post.get("error"):
                    result["errors"].append({"stage": "collection",
                        "organization_handle": handle,
                        "code": "actor_item_error", "message": "Apify reported a failed item; inspect its run logs."})
                    continue
                image_urls = get_image_urls(post)
                if not image_urls:
                    if post.get("type") != "Video":
                        result["errors"].append({"stage": "collection",
                            "organization_handle": handle,
                            "code": "no_photo_urls",
                            "message": "Post has no identifiable photo URLs.",
                            "post_url": post.get("url")})
                    continue
                result["posts"].append({
                    "organization_handle": handle,
                    "post_url": post.get("url"),
                    "caption": post.get("caption") or "",
                    # Publication time is not the event's date.
                    "posted_at": post.get("timestamp"),
                    "image_urls": image_urls,
                })
        except Exception as error:
            # Preserve safe JSON errors and continue collecting other clubs.
            result["errors"].append({**error_record(error, "collection"),
                "organization_handle": handle})
    return result

