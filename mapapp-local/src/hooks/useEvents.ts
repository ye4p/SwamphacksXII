import { useState } from "react";
import type { Event } from "../types";
import events from "../data/events";

export function useEvents() {
  const [localEvents, setEvents] = useState<Event[]>(events);
  return { events: localEvents, setEvents, loading: false, error: null };
}
