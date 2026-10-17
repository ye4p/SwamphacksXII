"""Collect Instagram post metadata and photo URLs through Apify."""

import os  # Reads API keys from environment variables.
import sys  # Sends progress messages to stderr, separate from JSON output.

if __package__:
    from .config import CLUB_HANDLES, POSTS_PER_ACCOUNT, APIFY_ACTOR
else:
    from config import CLUB_HANDLES, POSTS_PER_ACCOUNT, APIFY_ACTOR


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



def collect_posts():
    """Collect post metadata and keep failures alongside successful results."""
    result = {"posts": [], "errors": []}
    if not CLUB_HANDLES:
        result["errors"].append({"stage": "settings", "message":
                                 "Add club usernames to CLUB_HANDLES first."})
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

    client = ApifyClient(token)
    for handle in CLUB_HANDLES:
        print(f"Collecting posts from @{handle} through Apify...", file=sys.stderr)
        try:
            # Each call starts a hosted job and may consume Apify credits.
            run = client.actor(APIFY_ACTOR).call(run_input={
                "directUrls": [f"https://www.instagram.com/{handle}/"],
                "resultsType": "posts",
                "resultsLimit": POSTS_PER_ACCOUNT,
            })
            # Apify SDK 3 returns a Run object, accessed with dots, not .get().
            if not run or run.status != "SUCCEEDED":
                status = run.status if run else "UNKNOWN"
                result["errors"].append({"stage": "collection",
                    "organization_handle": handle,
                    "message": f"Apify run did not succeed: {status}"})
                continue
            # A dataset is Apify's stored list of results for this run.
            for post in client.dataset(run.default_dataset_id).iterate_items():
                if post.get("error"):
                    result["errors"].append({"stage": "collection",
                        "organization_handle": handle,
                        "message": str(post.get("errorDescription") or post["error"])})
                    continue
                image_urls = get_image_urls(post)
                if not image_urls:
                    if post.get("type") != "Video":
                        result["errors"].append({"stage": "collection",
                            "organization_handle": handle,
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
            # Keep earlier results; avoid exception details containing credentials.
            result["errors"].append({
                "stage": "collection", "organization_handle": handle,
                "message": f"Apify collection failed ({type(error).__name__}); "
                           "check your token, credits, and Apify run logs.",
            })
    return result

