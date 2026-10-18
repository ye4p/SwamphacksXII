import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "Scraper"))

from Scraper.server_runner import run as run_scraper  # noqa: E402
from Scraper import config  # noqa: E402
from core.tigerdata import TigerData  # noqa: E402


async def main():
    db = TigerData()
    await db.connect()
    await db.init_db()

    orgs = []
    for url in config.GATORCONNECT_ORGANIZATION_URLS:
        name = url.rstrip("/").split("/")[-1]
        oid = await db.upsert_organization(name, "", None, None, url)
        orgs.append({"id": oid, "conURL": url})

    existing = await db.get_current_events()
    # normalize existing for duplicate detection
    existing_list = []
    for e in existing:
        existing_list.append({
            "id": e["id"],
            "organization_id": e["organization_id"],
            "timestamp": e["timestamp"].isoformat() if hasattr(e["timestamp"], "isoformat") else e["timestamp"],
            "title": e["title"],
        })

    def create_event_id():
        return None  # placeholder; replaced below

    # run_scraper requires sync id callback; use DB sequence via sync? Use incrementing counter based on max id
    import itertools
    counter = itertools.count(max((e["id"] for e in existing), default=0) + 1)

    def create_id():
        return next(counter)

    try:
        events = run_scraper("gatorconnect", orgs, existing_list, create_id)
    except Exception as e:
        print("Scraper error:", e)
        events = getattr(e, "events", [])

    inserted = 0
    for ev in events:
        ts = ev["timestamp"]
        await db.add_event(
            timestamp=ts,
            title=ev["title"],
            description=ev.get("description", ""),
            address=ev["address"],
            longitude=ev["longitude"],
            latitude=ev["latitude"],
            organization_id=ev["organization_id"],
            payload=ev.get("payload", {}),
        )
        inserted += 1

    await db.close()
    print(f"Inserted {inserted} events")


if __name__ == "__main__":
    asyncio.run(main())
