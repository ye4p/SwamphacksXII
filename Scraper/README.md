# Scraper

## Duplicate prevention

Before scraping Instagram posts, `pipeline.py` calls `fetch_events(start_date)` from
`database.py` to retrieve events already stored from `start_date` onward. The
returned list is converted into a set of `(club, date)` keys.

While processing each scraped post, events whose `(organization_handle, date)`
matches an existing database event are skipped, since that club already has an
event on the same day. This avoids pushing duplicate posts/events without
additional API calls.
