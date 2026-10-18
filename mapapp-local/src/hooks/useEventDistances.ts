import { useState, useEffect } from "react";
import type { Event } from "../types";
import { calculate_distance } from "../utils/distance";

export interface EventDistance {
  eventId: number;
  distance: number;
}

export function useEventDistances(
  events: Event[],
  userPosition: [number, number] | null
) {
  const [distances, setDistances] = useState<EventDistance[]>([]);

  useEffect(() => {
    if (!userPosition || events.length === 0) {
      setDistances([]);
      return;
    }

    const temp: EventDistance[] = [];

    for (let i = 0; i < events.length; i++) {
      const distance: number = calculate_distance(userPosition, events[i]);
      temp.push({ eventId: events[i].id, distance });
    }

    temp.sort((a, b) => a.distance - b.distance);

    setDistances(temp);
  }, [events, userPosition]);

  return { distances };
}
