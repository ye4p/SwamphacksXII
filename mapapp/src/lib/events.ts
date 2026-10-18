import { api } from "./api";
import type { EventDays } from "./eventRanges";
import type { Event } from "../types";

export async function getEvents(numdays: EventDays, signal?: AbortSignal): Promise<Event[]> {
  const { data } = await api.get<{ events: Event[] }>("/api/getEventsFromDay", {
    params: { numdays }, signal,
  });
  if (!Array.isArray(data?.events)) throw new Error("Invalid events response");
  return data.events;
}
