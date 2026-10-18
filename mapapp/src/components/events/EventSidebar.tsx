import { useLayoutEffect, useState } from "react";
import type { CSSProperties } from "react";
import { useSidebarResize } from "../../hooks/useSidebarResize";
import type { Event } from "../../types";
import type { EventFilters as Filters } from "../../hooks/useEventFilters";
import EventFilters from "./EventFilters";
import EventCard from "./EventCard";

interface Props {
  events: Event[];
  filters: Filters;
  onChange: (filters: Filters) => void;
  onReset: () => void;
  loading: boolean;
  error: string | null;
  onSelect: (event: Event) => void;
}
export default function EventSidebar({ events, filters, onChange, onReset, loading, error, onSelect }: Props) {
  const { width, limits, resizing, handleProps } = useSidebarResize();
  const [collapsed, setCollapsed] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 3;
  useLayoutEffect(() => setPage(1), [filters]);
  const pageCount = Math.max(1, Math.ceil(events.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const start = (currentPage - 1) * pageSize;
  return (
    <aside className={`event-sidebar${collapsed ? " is-collapsed" : ""}${resizing ? " is-resizing" : ""}`} style={{ "--sidebar-width": `${width}px` } as CSSProperties} aria-label="Swamp Search">
      {!collapsed && <div
        className="sidebar-resize-handle"
        role="separator"
        tabIndex={0}
        aria-label="Resize events sidebar"
        aria-orientation="vertical"
        aria-controls="sidebar-content"
        aria-valuemin={limits.min}
        aria-valuemax={limits.max}
        aria-valuenow={width}
        aria-valuetext={`${width} pixels wide`}
        title="Drag to resize. Use left and right arrow keys when focused."
        {...handleProps}
      />}
      <button className="sidebar-toggle" aria-expanded={!collapsed} aria-controls="sidebar-content" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? "Expand Swamp Search" : "Collapse Swamp Search"}>
        <span aria-hidden="true">{collapsed ? "‹" : "›"}</span>{collapsed && <span>Swamp Search <span className="count-badge">{events.length}</span></span>}
      </button>
      <div id="sidebar-content" className="sidebar-content" hidden={collapsed}>
        <div className="sidebar-heading"><div><h1>Swamp Search <span className="count-badge">{events.length}</span></h1></div></div>
        <EventFilters filters={filters} onChange={onChange} onReset={onReset} />
        <div className="event-list" aria-busy={loading}>
          {loading && <p role="status">Loading events…</p>}
          {error && <p className="filter-error" role="alert">{error}</p>}
          {events.slice(start, start + pageSize).map((event) => <EventCard key={event.id} event={event} onSelect={onSelect} />)}
          {!loading && !error && !events.length && <div className="empty-state"><h3>No events found</h3><p>Try another search, time range, or tag.</p><button className="outline-button" onClick={onReset}>Clear filters</button></div>}
        </div>
        <nav className="pagination" aria-label="Event pages">
          <span aria-live="polite">{events.length ? `${start + 1}–${Math.min(start + pageSize, events.length)} of ${events.length}` : "0 events"}</span>
          <div><button className="outline-button" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)} aria-label="Previous page">‹</button><span>{currentPage} / {pageCount}</span><button className="outline-button" disabled={currentPage === pageCount} onClick={() => setPage(currentPage + 1)} aria-label="Next page">›</button></div>
        </nav>
      </div>
    </aside>
  );
}
