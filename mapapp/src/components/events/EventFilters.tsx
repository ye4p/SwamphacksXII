import { useState } from "react";
import { EVENT_TAGS, type EventFilters as Filters } from "../../hooks/useEventFilters";

interface Props {
  filters: Filters;
  onChange: (filters: Filters) => void;
  onReset: () => void;
  invalidRange: boolean;
}
export default function EventFilters({ filters, onChange, onReset, invalidRange }: Props) {
  const [tagsOpen, setTagsOpen] = useState(false);
  const active = filters.query || filters.from || filters.to || filters.tags.length > 0;
  return (
    <div className="event-filters">
      <div className="filter-search-row">
        <label className="sr-only" htmlFor="event-search">Search event names and descriptions</label>
        <input id="event-search" type="search" placeholder="Search events…" value={filters.query} onChange={(event) => onChange({ ...filters, query: event.target.value })} />
        <button className="outline-button tags-toggle" aria-expanded={tagsOpen} aria-controls="tag-options" onClick={() => setTagsOpen(!tagsOpen)}>Tags {filters.tags.length > 0 && `(${filters.tags.length})`} <span aria-hidden="true">{tagsOpen ? "−" : "+"}</span></button>
      </div>
      <div className="date-filters">
        <label htmlFor="date-from">From<input id="date-from" type="datetime-local" value={filters.from} max={filters.to || undefined} onChange={(event) => onChange({ ...filters, from: event.target.value })} /></label>
        <label htmlFor="date-to">To<input id="date-to" type="datetime-local" value={filters.to} min={filters.from || undefined} onChange={(event) => onChange({ ...filters, to: event.target.value })} /></label>
      </div>
      {invalidRange && <p className="filter-error" role="alert">End date must be on or after start date.</p>}
      {active && <div className="filter-actions"><button className="text-button" onClick={onReset}>Clear filters</button></div>}
      <div id="tag-options" hidden={!tagsOpen}>
        <p className="tag-hint">Match any selected tag</p>
        <div className="tag-options">{EVENT_TAGS.map((tag) => (
          <button key={tag} className="tag tag-option" aria-pressed={filters.tags.includes(tag)} onClick={() => onChange({ ...filters, tags: filters.tags.includes(tag) ? filters.tags.filter((value) => value !== tag) : [...filters.tags, tag] })}>{tag}</button>
        ))}</div>
      </div>
    </div>
  );
}
