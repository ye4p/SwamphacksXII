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
          console.log(res.data);
          // setEvents(res.data.events ?? [])
          const temp: Event[] = [];
          
          for (let i = 0; i < res.data.events.length; i++ ) {
            temp.push(res.data.events[i]);
          }

          setEvents(temp);

          console.log("data parsed successfully");
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

  useEffect(() => {
    console.log(events);
  }, [events])

  return { events, setEvents, loading, error };
}
