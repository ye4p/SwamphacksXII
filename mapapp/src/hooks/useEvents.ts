import { useState } from "react";
import type { Event } from "../types";

export function useEvents() {
  const [events, setEvents] = useState<Event[]>([]);

  return { events, setEvents };
}
