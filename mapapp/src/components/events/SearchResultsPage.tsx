import { useEffect, useMemo, useState } from "react";
import hardcodedEvents from "../../data/events";
import { EVENT_TAGS, useEventFilters } from "../../hooks/useEventFilters";
import { useEvents } from "../../hooks/useEvents";
import Header from "../layout/Header";

const dateFormatter = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
const timeFormatter = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });

export default function SearchResultsPage() {
  const { events, setEvents } = useEvents();
  const query = new URLSearchParams(window.location.search).get("q") ?? "";
  const { filters, setFilters, filteredEvents, invalidRange, resetFilters } = useEventFilters(events);
  const [sortOrder, setSortOrder] = useState<"soonest" | "latest">("soonest");

  useEffect(() => setEvents(hardcodedEvents), [setEvents]);

  const sortedEvents = useMemo(() => {
    if (sortOrder === "soonest") return filteredEvents;
    return [...filteredEvents].reverse();
  }, [filteredEvents, sortOrder]);

  const tagCounts = useMemo(() => Object.fromEntries(
    EVENT_TAGS.map((tag) => [tag, events.filter((event) => event.payload.tags?.includes(tag)).length]),
  ), [events]);

  return (
    <div className="app-shell results-shell">
      <Header query={filters.query} onSearch={(value) => window.location.assign(`/search?q=${encodeURIComponent(value.trim())}`)} />
      <main className="results-page">
        <nav className="results-breadcrumb" aria-label="Breadcrumb">
          <a href="/">Explore campus</a><span aria-hidden="true">/</span><span>Events</span>
        </nav>
        <div className="results-intro">
          <div>
            <h1>Events for &quot;{filters.query.trim()}&quot;</h1>
            <p>Find events happening at the University of Florida.</p>
          </div>
          <a className="outline-button results-home-link" href="/">Explore the map</a>
        </div>

        <div className="results-layout">
          <aside className="results-filters" aria-label="Filter events">
            <div className="results-filter-heading"><h2>Filter events</h2><span aria-hidden="true">☷</span></div>
            <fieldset className="results-filter-group">
              <legend>Dates</legend>
              <label htmlFor="results-from">From</label>
              <input id="results-from" type="date" value={filters.from} onChange={(event) => setFilters({ ...filters, from: event.target.value })} />
              <label htmlFor="results-to">To</label>
              <input id="results-to" type="date" value={filters.to} onChange={(event) => setFilters({ ...filters, to: event.target.value })} />
              {invalidRange && <p className="filter-error" role="alert">End date must be on or after start date.</p>}
            </fieldset>
            <fieldset className="results-filter-group">
              <legend>Event categories</legend>
              {EVENT_TAGS.map((tag) => (
                <label className="results-checkbox" key={tag}>
                  <input
                    type="checkbox"
                    checked={filters.tags.includes(tag)}
                    onChange={() => setFilters({
                      ...filters,
                      tags: filters.tags.includes(tag)
                        ? filters.tags.filter((value) => value !== tag)
                        : [...filters.tags, tag],
                    })}
                  />
                  <span>{tag}</span><small>{tagCounts[tag]}</small>
                </label>
              ))}
            </fieldset>
            <button className="text-button results-reset" type="button" onClick={resetFilters}>Reset all filters</button>
          </aside>

          <section className="results-content" aria-label="Event search results">
            <div className="results-toolbar">
              <p><strong>{sortedEvents.length} {sortedEvents.length === 1 ? "event" : "events"}</strong> <span>at University of Florida</span></p>
              <label>Sort by:
                <select value={sortOrder} onChange={(event) => setSortOrder(event.target.value as "soonest" | "latest")}>
                  <option value="soonest">Soonest first</option>
                  <option value="latest">Latest first</option>
                </select>
              </label>
            </div>
            {(filters.from || filters.to || filters.tags.length > 0) && (
              <div className="results-active-filters">
                {filters.from && <span className="tag">{dateFormatter.format(new Date(`${filters.from}T00:00:00`))}</span>}
                {filters.to && <span className="tag">{dateFormatter.format(new Date(`${filters.to}T00:00:00`))}</span>}
                {filters.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
                <button className="text-button" type="button" onClick={resetFilters}>Clear filters</button>
              </div>
            )}
            {sortedEvents.length ? (
              <div className="results-grid">
                {sortedEvents.map((event) => {
                  const date = new Date(event.timestamp);
                  return (
                    <article className="results-card" key={event.id}>
                      <div className="results-card-main">
                        <time className="results-date-badge" dateTime={event.timestamp}>
                          <span>{new Intl.DateTimeFormat(undefined, { month: "short" }).format(date)}</span>
                          <strong>{new Intl.DateTimeFormat(undefined, { day: "2-digit" }).format(date)}</strong>
                        </time>
                        <div className="results-card-title">
                          <h2>{event.title}</h2>
                          <div className="tags">{event.payload.tags?.map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div>
                        </div>
                      </div>
                      <p className="results-card-description">{event.description || "No description provided."}</p>
                      <div className="results-card-footer">
                        <span>{dateFormatter.format(date)} · {timeFormatter.format(date)}</span>
                        <span>{event.address || "On campus"}</span>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="results-empty">
                <h2>No events found</h2>
                <p>Try another search or clear some filters to see more events.</p>
                <button className="outline-button" type="button" onClick={resetFilters}>Clear filters</button>
              </div>
            )}
            {sortedEvents.length > 0 && <p className="results-endnote">You&apos;ve seen all {sortedEvents.length} matches. Your next event could be here.</p>}
          </section>
        </div>
      </main>
    </div>
  );
}
