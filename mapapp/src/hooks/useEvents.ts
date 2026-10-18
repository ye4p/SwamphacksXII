import { useState, useEffect } from "react";
import type { Event } from "../types";
import { apiErrorMessage } from "../lib/api";
import { getEvents } from "../lib/events";
import type { EventDays } from "../lib/eventRanges";

export function useEvents(days: EventDays) {
  const [result, setResult] = useState<{ days: EventDays; events: Event[]; error: string | null } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setResult(null);
    getEvents(days, controller.signal).then((events) => {
      if (!controller.signal.aborted) setResult({ days, events, error: null });
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) {
        setResult({ days, events: [], error: apiErrorMessage(cause, "Unable to load events.") });
      }
    });
    return () => controller.abort();
  }, [days]);

  const current = result?.days === days ? result : null;
  return { events: current?.events ?? [], loading: current === null, error: current?.error ?? null };
}
