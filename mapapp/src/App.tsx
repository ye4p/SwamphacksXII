import { useEffect, useState } from "react";
import "./index.css";
import "./pages.css";
import DiscoveryPages from "./components/layout/DiscoveryPages";
import type { Event } from "./types";
import { useEventFilters } from "./hooks/useEventFilters";
import Header from "./components/layout/Header";
import EventMap from "./components/events/EventMap";
import EventSidebar from "./components/events/EventSidebar";
export default function App() {
  const [location, setLocation] = useState(() => ({ pathname: window.location.pathname, search: window.location.search }));
  useEffect(() => {
    const sync = () => setLocation({ pathname: window.location.pathname, search: window.location.search });
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);
  const navigate = (url: string) => {
    window.history.pushState(null, "", url);
    setLocation({ pathname: window.location.pathname, search: window.location.search });
  };
  const search = (query: string, mode: "events" | "organizations" = "events") => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (mode === "organizations") params.set("type", mode);
    navigate(`/search${params.size ? `?${params}` : ""}`);
  };
  const isPage = location.pathname === "/search" || location.pathname === "/profile";
  const [userPosition, setUserPosition] = useState<[number, number] | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<Event | null>(null);
  const { filters, setFilters, filteredEvents, loading, error, resetFilters } = useEventFilters();
  useEffect(() => { navigator.geolocation?.getCurrentPosition(({ coords }) => setUserPosition([coords.latitude, coords.longitude]), () => {}); }, []);
  return <div className={`app-shell${isPage ? " results-app-shell" : ""}`}>
    <Header onSearch={search} onProfileClick={() => navigate("/profile")} />
    {isPage ? <DiscoveryPages pathname={location.pathname} search={location.search} onSearch={search} onBack={() => navigate("/")} onSelectEvent={(event) => { setFilters({ query: "", days: 30, tags: [] }); setSelectedEvent({ ...event }); navigate("/"); }} /> : (
    <main className="map-layout">
      <section className="map-region" aria-label="Map of events"><EventMap events={filteredEvents} userPosition={userPosition} selectedEvent={selectedEvent} /></section>
      <EventSidebar events={filteredEvents} filters={filters} onChange={setFilters} onReset={resetFilters} loading={loading} error={error} onSelect={(event) => setSelectedEvent({ ...event })} />
    </main>)}
  </div>;
}
