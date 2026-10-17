import { useState, useEffect } from "react";
import type { Event } from "../types.ts";

export interface EventDistance {
  eventId: number;
  distance: number;
}

export function calculate_distances() {
    
}

export function useEventDistances() {
  const [distances, setDistances] = useState<EventDistance[]>([]);

  

  return { distances, setDistances };
}
