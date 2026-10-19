"""Import the entire public GatorConnect listing without Gemini."""
import argparse
import asyncio
import json
from pathlib import Path

from Scraper.gatorconnect_feed import collect_mappable_events


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Geocode and print mappable events without database access")
    parser.add_argument("--report", type=Path, help="Write counts and skipped-location diagnostics as JSON")
    args = parser.parse_args()
    result = await asyncio.to_thread(collect_mappable_events)
    events = result["events"]
    if args.report:
        args.report.write_text(json.dumps({"mappable": len(events), "skipped": result["skipped"]}, indent=2))
    if args.dry_run:
        print(json.dumps(events, ensure_ascii=False, indent=2))
        return

    # Import only after config has loaded backend/.env, and only when needed.
    from backend.core.tigerdata import TigerData
    db = TigerData()
    if not db.dsn:
        raise RuntimeError("Set CONNECTION in backend/.env before importing events")
    try:
        await db.connect()
        await db.init_db()
        count = await db.import_gatorconnect_events(events)
        print(f"Imported {count} public events (inserted or updated)")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
