import { useState } from "react";
import { DATE_RANGES, EVENT_TAGS, type EventFilters as Filters } from "../../hooks/useEventFilters";

interface Props {
  filters: Filters;
  onChange: (filters: Filters) => void;
  onReset: () => void;
}
export default function EventFilters({ filters, onChange, onReset }: Props) {
  const [tagsOpen, setTagsOpen] = useState(false);
  const active = filters.query || filters.dateRange > 0 || filters.tags.length > 0;
  return (
    <div className="event-filters">
      <div className="filter-search-row">
        <label className="sr-only" htmlFor="event-search">Search event names and descriptions</label>
        <input id="event-search" type="search" placeholder="Search events…" value={filters.query} onChange={(event) => onChange({ ...filters, query: event.target.value })} />
      </div>
      <div className="date-filters">
        <label htmlFor="date-range">Date range</label>
        <select id="date-range" value={filters.dateRange} onChange={(event) => onChange({ ...filters, dateRange: Number(event.target.value) })}>
          {DATE_RANGES.map(({ label, days }) => <option key={days} value={days}>{label}</option>)}
        </select>
        <button className="outline-button tags-toggle" aria-expanded={tagsOpen} aria-controls="tag-options" onClick={() => setTagsOpen(!tagsOpen)}>Tags {filters.tags.length > 0 && `(${filters.tags.length})`} <span aria-hidden="true">{tagsOpen ? "−" : "+"}</span></button>
      </div>
      {active && <div className="filter-actions"><button className="text-button" onClick={onReset}>Clear filters</button></div>}
      <div id="tag-options" hidden={!tagsOpen}>
        <div className="tag-options">{EVENT_TAGS.map((tag) => (
          <button key={tag} className="tag tag-option" aria-pressed={filters.tags.includes(tag)} onClick={() => onChange({ ...filters, tags: filters.tags.includes(tag) ? filters.tags.filter((value) => value !== tag) : [...filters.tags, tag] })}>{tag}</button>
        ))}</div>
      </div>
    </div>
  );
}
