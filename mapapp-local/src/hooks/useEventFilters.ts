import { useMemo, useState } from "react";
import type { Event } from "../types";

export const EVENT_TAGS = ["programming", "educational", "food", "sports", "run club", "ai"];
export const DATE_RANGES = [
  { label: "Any time", days: 0 },
  { label: "Today", days: 1 },
  { label: "This Week", days: 7 },
  { label: "Within 2 weeks", days: 14 },
  { label: "Within 3 weeks", days: 21 },
  { label: "Within 4 weeks", days: 28 },
] as const;

export interface EventFilters {
  query: string;
  dateRange: number;
  tags: string[];
}
const emptyFilters: EventFilters = { query: "", dateRange: 0, tags: [] };

export function useEventFilters(events: Event[]) {
  const [filters, setFilters] = useState<EventFilters>(emptyFilters);
  const filteredEvents = useMemo(() => {
    const query = filters.query.trim().toLowerCase();
    const rangeStart = new Date();
    rangeStart.setHours(0, 0, 0, 0);
    const rangeEnd = new Date(rangeStart);
    rangeEnd.setDate(rangeEnd.getDate() + filters.dateRange);
    return events.filter((event) => {
      const start = new Date(event.timestamp);
      return (!query || `${event.title} ${event.description}`.toLowerCase().includes(query)) &&
        (!filters.dateRange || (start >= rangeStart && start < rangeEnd)) &&
        (!filters.tags.length || filters.tags.some((tag) => event.payload?.tags?.includes(tag)));
    }).sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
  }, [events, filters]);
  return { filters, setFilters, filteredEvents, resetFilters: () => setFilters(emptyFilters) };
}
