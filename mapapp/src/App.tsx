import { useEffect, useState } from "react";
import "./index.css";
import type { Event } from "./types";
import { useEvents } from "./hooks/useEvents";
import { useEventFilters } from "./hooks/useEventFilters";
import Header from "./components/layout/Header";
import EventMap from "./components/events/EventMap";
import EventSidebar from "./components/events/EventSidebar";
export default function App() {
  const [userPosition, setUserPosition] = useState<[number, number] | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<Event | null>(null);
  const { events, setEvents, loading, error } = useEvents();
  const { filters, setFilters, filteredEvents, invalidRange, resetFilters } = useEventFilters(events);
  useEffect(() => { navigator.geolocation?.getCurrentPosition(({ coords }) => setUserPosition([coords.latitude, coords.longitude]), () => {}); }, []);
  return <div className="app-shell">
    <Header query={filters.query} onSearch={(query) => setFilters({ ...filters, query })} />
    <main className="map-layout">
      <section className="map-region" aria-label="Map of events"><EventMap events={filteredEvents} userPosition={userPosition} selectedEvent={selectedEvent} /></section>
      <EventSidebar events={filteredEvents} filters={filters} onChange={setFilters} onReset={resetFilters} invalidRange={invalidRange} onSelect={(event) => setSelectedEvent({ ...event })} />
    </main>
  </div>;
}
