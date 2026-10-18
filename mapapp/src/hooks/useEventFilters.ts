import { useMemo, useState } from "react";
import type { Event } from "../types";

export const EVENT_TAGS = ["programming", "educational", "food", "sports", "run club", "ai"];
export interface EventFilters {
  query: string;
  from: string;
  to: string;
  tags: string[];
}
const emptyFilters: EventFilters = { query: "", from: "", to: "", tags: [] };

export function useEventFilters(events: Event[]) {
  const [filters, setFilters] = useState<EventFilters>(emptyFilters);
  const invalidRange = Boolean(filters.from && filters.to && filters.from > filters.to);
  const filteredEvents = useMemo(() => {
    const query = filters.query.trim().toLowerCase();
    return events.filter((event) => {
      const start = new Date(event.timestamp).getTime();
      return !invalidRange &&
        (!query || `${event.title} ${event.description}`.toLowerCase().includes(query)) &&
        (!filters.from || start >= new Date(filters.from).getTime()) &&
        (!filters.to || start <= new Date(filters.to).getTime()) &&
        (!filters.tags.length || filters.tags.some((tag) => event.payload?.tags?.includes(tag)));
    }).sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
  }, [events, filters, invalidRange]);
  return { filters, setFilters, filteredEvents, invalidRange, resetFilters: () => setFilters(emptyFilters) };
}
