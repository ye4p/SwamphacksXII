import { useMemo } from "react";
import type { Event } from "../types";

export function useEventsById(events: Event[]) {
  return useMemo(
    () => events.reduce<Record<number, Event>>((acc, event) => {
      acc[event.id] = event;
      return acc;
    }, {}),
    [events]
  );
}
