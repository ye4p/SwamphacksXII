import { useMemo, useState } from "react";
import { CalendarDays, Check, Heart, MapPin, SlidersHorizontal, X } from "lucide-react";
import type { Event } from "../../types";
import organizations from "../../data/organizations";
import { DATE_RANGES } from "../../hooks/useEventFilters";

const categories = [
  { label: "Career", tags: ["career"], color: "Career" },
  { label: "Arts & culture", tags: ["arts", "culture", "music"], color: "Arts & culture" },
  { label: "Food & drink", tags: ["food"], color: "Food & drink" },
  { label: "Music", tags: ["music"], color: "Music" },
  { label: "Programming", tags: ["programming", "coding", "hackathon"], color: "Programming" },
];

const tagOptions = ["Hackathons", "Networking", "Open source", "Social"];
const eventTags: Record<string, string[]> = {
  Hackathons: ["hackathon", "hackathons"],
  Networking: ["networking"],
  "Open source": ["open source", "open-source"],
  Social: ["social"],
};

function matchesAny(tags: string[], terms: string[]) {
  return terms.some((term) => tags.includes(term));
}

function eventDate(timestamp: string) {
  return new Intl.DateTimeFormat("en-US", { weekday: "long", hour: "numeric", minute: "2-digit" }).format(new Date(timestamp));
}

function eventTime(timestamp: string) {
  return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(new Date(timestamp));
}

function getCategory(tags: string[]) {
  return categories.find((category) => matchesAny(tags, category.tags))?.label ?? "Community";
}

function getHost(event: Event) {
  return organizations.find((organization) => organization.id === event.organization_id)?.name ?? "University of Florida";
}

function getLocation(event: Event) {
  return event.address.split(",")[0] || "University of Florida";
}

export default function SearchResults({ events, query, onModeChange }: { events: Event[]; query: string; onModeChange: (mode: "events" | "organizations") => void }) {
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedHosts, setSelectedHosts] = useState<string[]>([]);
  const [hostSearch, setHostSearch] = useState("");
  const [selectedLocations, setSelectedLocations] = useState<string[]>([]);
  const [dateRange, setDateRange] = useState(0);
  const [sortOrder, setSortOrder] = useState("soonest");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [favorite, setFavorite] = useState(false);

  const matchingEvents = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    const rangeStart = new Date();
    rangeStart.setHours(0, 0, 0, 0);
    const rangeEnd = new Date(rangeStart);
    rangeEnd.setDate(rangeEnd.getDate() + dateRange);
    return events.filter((event) => {
      const tags = (event.payload?.tags ?? []).map((tag) => tag.toLocaleLowerCase());
      const searchable = [event.title, event.description, event.address, ...tags].join(" ").toLocaleLowerCase();
      const date = new Date(event.timestamp);
      return (!needle || searchable.includes(needle))
        && (!selectedCategories.length || selectedCategories.includes(getCategory(tags)))
        && (!selectedTags.length || selectedTags.some((tag) => matchesAny(tags, eventTags[tag] ?? [])))
        && (!selectedHosts.length || selectedHosts.includes(getHost(event)))
        && (!selectedLocations.length || selectedLocations.includes(getLocation(event)))
        && (!dateRange || (date >= rangeStart && date < rangeEnd))
        && (!favoritesOnly || favorite);
    }).sort((left, right) => sortOrder === "latest"
      ? Date.parse(right.timestamp) - Date.parse(left.timestamp)
      : sortOrder === "title"
        ? left.title.localeCompare(right.title)
        : Date.parse(left.timestamp) - Date.parse(right.timestamp));
  }, [events, query, selectedCategories, selectedTags, selectedHosts, selectedLocations, dateRange, sortOrder, favoritesOnly, favorite]);

  const categoryCounts = (tags: string[]) => events.filter((event) =>
    (!query.trim() || [event.title, event.description, event.address, ...(event.payload?.tags ?? [])].join(" ").toLowerCase().includes(query.trim().toLowerCase()))
      && matchesAny((event.payload?.tags ?? []).map((tag) => tag.toLowerCase()), tags),
  ).length;
  const tagCounts = (label: string) => events.filter((event) => matchesAny(
    (event.payload?.tags ?? []).map((tag) => tag.toLowerCase()),
    eventTags[label] ?? [],
  )).length;
  const hosts = [...new Set(events.map(getHost))];
  const matchingHosts = hosts.filter((host) => host.toLocaleLowerCase().includes(hostSearch.trim().toLocaleLowerCase()));
  const locations = [...new Set(events.map(getLocation))];
  const activeFilterCount = selectedCategories.length + selectedTags.length + selectedHosts.length + selectedLocations.length + Number(dateRange > 0);

  const clearFilters = () => {
    setSelectedCategories([]);
    setSelectedTags([]);
    setSelectedHosts([]);
    setSelectedLocations([]);
    setDateRange(0);
    setFavoritesOnly(false);
  };

  const toggle = (value: string, selected: string[], update: (next: string[]) => void) => {
    update(selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value]);
  };

  const toggleCheckbox = (label: string, count: number, selected: string[], update: (next: string[]) => void) => (
    <label className="results-checkbox" key={label}>
      <input type="checkbox" checked={selected.includes(label)} onChange={() => toggle(label, selected, update)} />
      <span>{label}</span><small>{count}</small>
    </label>
  );

  return (
    <main className="search-results-page">
      <div className="results-breadcrumb"><a href="/">Explore campus</a><span>/</span><span>Events</span></div>
      <nav className="search-mode-tabs" aria-label="Search type">
        <button type="button" className="search-mode-tab is-active" aria-current="page">Events</button>
        <button type="button" className="search-mode-tab" onClick={() => onModeChange("organizations")}>Organizations</button>
      </nav>
      <section className="results-intro">
        <div>
          <h1>{query ? `Events for "${query}"` : "All Events"}</h1>
          <p>Find meetups, workshops, and events happening at the University of Florida.</p>
        </div>
        <button className={`outline-button favorite-organizations${favorite ? " is-favorite" : ""}`} onClick={() => {
          setFavorite(!favorite);
          setFavoritesOnly(!favorite);
        }}>
          <Heart size={16} fill={favorite ? "currentColor" : "none"} /> {favorite ? "Showing favorites" : "Favorite organizations"}
        </button>
      </section>

      <div className="results-layout">
        <aside className="results-filters" aria-label="Filter events">
          <div className="results-filter-heading"><strong>Filter events</strong><SlidersHorizontal size={16} /></div>
          <section className="results-filter-group">
            <h2>Dates</h2>
            <div className="date-range-fields">
              <select aria-label="Filter events by date" value={dateRange} onChange={(event) => setDateRange(Number(event.target.value))}>
                {DATE_RANGES.map(({ label, days }) => <option key={days} value={days}>{label}</option>)}
              </select>
            </div>
          </section>
          <section className="results-filter-group">
            <h2>Event categories</h2>
            {categories.map(({ label, tags }) => toggleCheckbox(label, categoryCounts(tags), selectedCategories, setSelectedCategories))}
          </section>
          <section className="results-filter-group">
            <h2>Tags</h2>
            {tagOptions.map((label) => toggleCheckbox(label, tagCounts(label), selectedTags, setSelectedTags))}
          </section>
          <section className="results-filter-group">
            <h2>Host organizations</h2>
            <input
              className="host-organization-search"
              type="search"
              aria-label="Search host organizations"
              placeholder="Search organizations"
              value={hostSearch}
              onChange={(event) => setHostSearch(event.target.value)}
            />
            {matchingHosts.map((host) => toggleCheckbox(host, events.filter((event) => getHost(event) === host).length, selectedHosts, setSelectedHosts))}
            {!matchingHosts.length && <p className="host-organization-empty">No organizations found.</p>}
          </section>
          <section className="results-filter-group">
            <h2>Location</h2>
            {locations.map((location) => toggleCheckbox(location, events.filter((event) => getLocation(event) === location).length, selectedLocations, setSelectedLocations))}
          </section>
          <button className="clear-filters-button" onClick={clearFilters}>Reset all filters</button>
          <aside className="favorite-prompt">
            <Heart size={18} />
            <strong>Keep your people close.</strong>
            <p>Favorite an organization to see its upcoming events on your profile.</p>
          </aside>
        </aside>

        <section className="results-content" aria-label="Search results">
          <div className="results-toolbar">
            <div><strong>{matchingEvents.length} {matchingEvents.length === 1 ? "event" : "events"}</strong><span>at University of Florida</span></div>
            <label className="sort-control">Sort by:
              <select aria-label="Sort events" value={sortOrder} onChange={(event) => setSortOrder(event.target.value)}>
                <option value="soonest">Soonest first</option>
                <option value="latest">Latest first</option>
                <option value="title">Event name</option>
              </select>
            </label>
          </div>

          {(activeFilterCount > 0 || query) && <div className="active-filters" aria-label="Active filters">
            {query && <span className="filter-chip">{query}</span>}
            {dateRange > 0 && <button className="filter-chip" onClick={() => setDateRange(0)}>{DATE_RANGES.find((range) => range.days === dateRange)?.label}<X size={12} /></button>}
            {selectedCategories.map((item) => <button className="filter-chip" key={item} onClick={() => toggle(item, selectedCategories, setSelectedCategories)}>{item}<X size={12} /></button>)}
            {selectedTags.map((item) => <button className="filter-chip" key={item} onClick={() => toggle(item, selectedTags, setSelectedTags)}>{item}<X size={12} /></button>)}
            {selectedHosts.map((item) => <button className="filter-chip" key={item} onClick={() => toggle(item, selectedHosts, setSelectedHosts)}>{item}<X size={12} /></button>)}
            {selectedLocations.map((item) => <button className="filter-chip" key={item} onClick={() => toggle(item, selectedLocations, setSelectedLocations)}>{item}<X size={12} /></button>)}
            {activeFilterCount > 0 && <button className="clear-chip" onClick={clearFilters}>Clear filters</button>}
          </div>}

          {matchingEvents.length ? <div className="results-event-grid">
            {matchingEvents.map((event) => (
              <article className="results-event-card" key={event.id}>
                <div className="results-card-main">
                  <time className="event-date-badge" dateTime={event.timestamp}>
                    <span>{new Intl.DateTimeFormat("en-US", { month: "short" }).format(new Date(event.timestamp))}</span>
                    <strong>{new Intl.DateTimeFormat("en-US", { day: "2-digit" }).format(new Date(event.timestamp))}</strong>
                  </time>
                  <div className="results-event-info">
                    <span className="host-badge">Hosted by {getHost(event)}</span>
                    <h2>{event.title}</h2>
                    <p className="results-event-meta">{getCategory((event.payload?.tags ?? []).map((tag) => tag.toLowerCase()))} · {event.payload?.tags?.slice(0, 2).join(" · ") || "Community"}</p>
                  </div>
                </div>
                <p className="results-event-description">{event.description || "No description provided."}</p>
                <footer className="results-event-footer">
                  <span><CalendarDays size={14} />{eventDate(event.timestamp)} – {eventTime(event.timestamp)}</span>
                  <span><MapPin size={14} />{getLocation(event)}</span>
                </footer>
              </article>
            ))}
          </div> : <div className="results-empty">
            <div className="results-empty-icon"><Check size={24} /></div>
            <h2>No events match these filters</h2>
            <p>Try a different search or clear some filters to see more events.</p>
            <button className="outline-button" onClick={clearFilters}>Clear filters</button>
          </div>}

          {matchingEvents.length > 0 && <p className="results-footer-note"><Check size={15} /> You&apos;ve seen all {matchingEvents.length} matches. Your next event could be right here.</p>}
        </section>
      </div>
    </main>
  );
}
