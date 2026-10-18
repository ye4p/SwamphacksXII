import { useState, useEffect } from "react";
import type { Event } from "../types";
import { api } from "../lib/api";

export function useEvents() {
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    console.log('trying to make api call')
    let cancelled = false;
    api.get("/getEventsDay" + "?date=2026-10-17")
      .then((res) => {
        if (!cancelled) {
          console.log("data collected");
          setEvents(res.data.events ?? []);
          setLoading(false);
        }
      })
      .catch((cause: any) => {
        if (!cancelled) {
          console.log("fail data collection");
          setError(cause?.response?.data?.detail || "Unable to load events.");
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, []);

  return { events, setEvents, loading, error };
}
