import type { EventSort } from "../../lib/eventSort";
import { useEventTags } from "../../hooks/useEventTags";
import EventTagsStatus from "./EventTagsStatus";
import { useState } from "react";
import { type EventFilters as Filters } from "../../hooks/useEventFilters";

import EventRangeSelect from "./EventRangeSelect";
import { DEFAULT_EVENT_DAYS } from "../../lib/eventRanges";

interface Props {
  filters: Filters;
  sort: EventSort;
  onSortChange: (sort: EventSort) => void;
  onChange: (filters: Filters) => void;
  onReset: () => void;
}
export default function EventFilters({ filters, onChange, onReset, sort, onSortChange }: Props) {
  const { tags } = useEventTags();
  const [tagsOpen, setTagsOpen] = useState(false);
  const active = filters.query || filters.days !== DEFAULT_EVENT_DAYS || filters.tags.length > 0;
  return (
    <div className="event-filters">
      <div className="filter-search-row">
        <label className="sr-only" htmlFor="event-search">Search event names and descriptions</label>
        <input id="event-search" type="search" placeholder="Search events…" value={filters.query} onChange={(event) => onChange({ ...filters, query: event.target.value })} />
        <button className="outline-button tags-toggle" aria-expanded={tagsOpen} aria-controls="tag-options" onClick={() => setTagsOpen(!tagsOpen)}>Tags {filters.tags.length > 0 && `(${filters.tags.length})`} <span aria-hidden="true">{tagsOpen ? "−" : "+"}</span></button>
      </div>
      <div className="sidebar-filter-row">
        <EventRangeSelect id="event-time-range" days={filters.days} onChange={(days) => onChange({ ...filters, days })} />
        <div className="date-filters">
          <label htmlFor="sidebar-sort">Sort by
            <select id="sidebar-sort" value={sort} onChange={(event) => onSortChange(event.target.value as EventSort)}>
              <option value="time">Time (earliest)</option>
              <option value="distance">Distance (nearest)</option>
              <option value="alphabetical">Alphabetical</option>
            </select>
          </label>
        </div>
      </div>
      {active && <div className="filter-actions"><button className="text-button" onClick={onReset}>Clear filters</button></div>}
      <div id="tag-options" hidden={!tagsOpen}>
        <p className="tag-hint">Match any selected tag</p>
        <EventTagsStatus />
        <div className="tag-options">{tags.map((tag) => (
          <button key={tag} className="tag tag-option" aria-pressed={filters.tags.includes(tag)} onClick={() => onChange({ ...filters, tags: filters.tags.includes(tag) ? filters.tags.filter((value) => value !== tag) : [...filters.tags, tag] })}>{tag}</button>
        ))}</div>
      </div>
    </div>
  );
}
