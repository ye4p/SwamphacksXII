import { useState, useEffect } from "react";
import type { Event } from "../types.ts";
import { calculate_distances } from "./useEventDistances.ts"
// export interface EventDistance {
//   eventId: number;
//   distance: number;
// }

export function useEventDistances() {
  const [events, setEvents] = useState<Event[]>([]);

  useEffect(() => {

  }, [events])

  return { events, setEvents };
}
