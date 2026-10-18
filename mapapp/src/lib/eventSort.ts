import type { Event } from "../types";
import type { EventDistance } from "../hooks/useEventDistances";

export type EventSort = "time" | "distance" | "alphabetical";

export function sortEvents(events: Event[], sort: EventSort, distances: EventDistance[]): Event[] {
  const byId = new Map(distances.map(({ eventId, distance }) => [eventId, Number.isFinite(distance) ? distance : Infinity]));
  return [...events].sort((a, b) => {
    const chronological = Date.parse(a.timestamp) - Date.parse(b.timestamp) || a.id - b.id;
    if (sort === "alphabetical") return a.title.localeCompare(b.title, undefined, { sensitivity: "base" }) || chronological;
    if (sort === "distance") return ((byId.get(a.id) ?? Infinity) - (byId.get(b.id) ?? Infinity)) || chronological;
    return chronological;
  });
}
