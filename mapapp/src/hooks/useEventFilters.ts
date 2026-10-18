import { useMemo, useState } from "react";
import { DEFAULT_EVENT_DAYS, type EventDays } from "../lib/eventRanges";
import { useEvents } from "./useEvents";

export const EVENT_TAGS = ["programming", "educational", "food", "sports", "run club", "ai"];
export interface EventFilters {
  query: string;
  days: EventDays;
  tags: string[];
}
const emptyFilters: EventFilters = { query: "", days: DEFAULT_EVENT_DAYS, tags: [] };

export function useEventFilters(initialQuery = "") {
  const [filters, setFilters] = useState<EventFilters>({ ...emptyFilters, query: initialQuery });
  const { events, loading, error } = useEvents(filters.days);
  const filteredEvents = useMemo(() => {
    const query = filters.query.trim().toLowerCase();
    return events.filter((event) =>
      (!query || `${event.title} ${event.description}`.toLowerCase().includes(query)) &&
      (!filters.tags.length || filters.tags.some((tag) => event.payload?.tags?.includes(tag))),
    ).sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
  }, [events, filters.query, filters.tags]);
  return { events, loading, error, filters, setFilters, filteredEvents, resetFilters: () => setFilters(emptyFilters) };
}
