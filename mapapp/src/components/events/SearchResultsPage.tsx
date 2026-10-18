import { useMemo, useState } from "react";
import { EVENT_TAGS, useEventFilters } from "../../hooks/useEventFilters";
import EventRangeSelect from "./EventRangeSelect";
import { eventRangeLabel } from "../../lib/eventRanges";
import Header from "../layout/Header";

const dateFormatter = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
const timeFormatter = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });

export default function SearchResultsPage() {
  const query = new URLSearchParams(window.location.search).get("q") ?? "";
  const { filters, setFilters, filteredEvents, events, loading, error, resetFilters } = useEventFilters(query);
  const [sortOrder, setSortOrder] = useState<"soonest" | "latest">("soonest");


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
              <legend>Time range</legend>
              <EventRangeSelect id="results-time-range" days={filters.days} onChange={(days) => setFilters({ ...filters, days })} />
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
            <div className="results-active-filters">
              <span className="tag">{eventRangeLabel(filters.days)}</span>
              {filters.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
              <button className="text-button" type="button" onClick={resetFilters}>Clear filters</button>
            </div>
            {loading ? <p role="status">Loading events…</p> : error ? <p className="filter-error" role="alert">{error}</p> : sortedEvents.length ? (
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
