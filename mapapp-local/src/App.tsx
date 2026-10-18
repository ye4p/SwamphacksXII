import { useEffect, useState } from "react";
import "./index.css";
import type { Event } from "./types";
import { useEvents } from "./hooks/useEvents";
import { useEventFilters } from "./hooks/useEventFilters";
import Header from "./components/layout/Header";
import EventMap from "./components/events/EventMap";
import EventSidebar from "./components/events/EventSidebar";
import SearchResults from "./components/events/SearchResults";
import OrganizationResults from "./components/events/OrganizationResults";
import ProfilePage from "./components/layout/ProfilePage";
import OfficerEventsPage from "./components/layout/OfficerEventsPage";

type SearchMode = "events" | "organizations";
const THEME_STORAGE_KEY = "swampsearch-theme";

export default function App() {
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem(THEME_STORAGE_KEY) === "dark");
  const [userPosition, setUserPosition] = useState<[number, number] | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<Event | null>(null);
  const [location, setLocation] = useState(() => ({
    pathname: window.location.pathname,
    search: window.location.search,
  }));
  const [profileReturnUrl, setProfileReturnUrl] = useState("/");
  const { events, setEvents, loading, error } = useEvents();
  const { filters, setFilters, filteredEvents, resetFilters } = useEventFilters(events);

  useEffect(() => {
    const syncLocation = () => setLocation({
      pathname: window.location.pathname,
      search: window.location.search,
    });
    window.addEventListener("popstate", syncLocation);
    return () => window.removeEventListener("popstate", syncLocation);
  }, []);
  useEffect(() => { navigator.geolocation?.getCurrentPosition(({ coords }) => setUserPosition([coords.latitude, coords.longitude]), () => {}); }, []);
  useEffect(() => {
    localStorage.setItem(THEME_STORAGE_KEY, darkMode ? "dark" : "light");
  }, [darkMode]);

  const search = (query: string, mode: SearchMode = "events") => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (mode === "organizations") params.set("type", mode);
    const nextUrl = `/search${params.size ? `?${params.toString()}` : ""}`;
    window.history.pushState(null, "", nextUrl);
    setLocation({ pathname: "/search", search: window.location.search });
  };
  const openProfile = () => {
    setProfileReturnUrl(`${location.pathname}${location.search}`);
    window.history.pushState(null, "", "/profile");
    setLocation({ pathname: "/profile", search: "" });
  };
  const closeProfile = () => {
    window.history.pushState(null, "", profileReturnUrl);
    setLocation({ pathname: window.location.pathname, search: window.location.search });
  };
  const openOfficerEvents = () => {
    window.history.pushState(null, "", "/officer-events");
    setLocation({ pathname: "/officer-events", search: "" });
  };
  const closeOfficerEvents = () => {
    window.history.pushState(null, "", "/profile");
    setLocation({ pathname: "/profile", search: "" });
  };

  if (location.pathname === "/search") {
    const params = new URLSearchParams(location.search);
    const query = params.get("q") ?? "";
    const mode: SearchMode = params.get("type") === "organizations" ? "organizations" : "events";
    return (
      <div className={`app-shell results-app-shell${darkMode ? " theme-dark" : ""}`}>
        <Header
          query={query}
          onAdvancedSearch={(nextQuery) => search(nextQuery, "organizations")}
          onProfileClick={openProfile}
        />
        {mode === "organizations"
          ? <OrganizationResults query={query} onModeChange={(nextMode) => search(query, nextMode)} />
          : <SearchResults events={events} query={query} onModeChange={(nextMode) => search(query, nextMode)} />}
      </div>
    );
  }

  if (location.pathname === "/profile") {
    return (
      <div className={`app-shell results-app-shell${darkMode ? " theme-dark" : ""}`}>
        <Header query="" onAdvancedSearch={(query) => search(query, "organizations")} onProfileClick={openProfile} />
        <ProfilePage
          events={events}
          onBack={closeProfile}
          onExploreOrganizations={() => search("", "organizations")}
          onOpenOfficerEvents={openOfficerEvents}
          darkMode={darkMode}
          onToggleTheme={() => setDarkMode((current) => !current)}
        />
      </div>
    );
  }

  if (location.pathname === "/officer-events") {
    return (
      <div className={`app-shell results-app-shell${darkMode ? " theme-dark" : ""}`}>
        <Header query="" onAdvancedSearch={(query) => search(query, "organizations")} onProfileClick={openProfile} />
        <OfficerEventsPage onBack={closeOfficerEvents} />
      </div>
    );
  }

  return <div className={`app-shell${darkMode ? " theme-dark" : ""}`}>
    <Header
      query={filters.query}
      onAdvancedSearch={(query) => search(query, "organizations")}
      onProfileClick={openProfile}
    />
    <main className="map-layout">
      <section className="map-region" aria-label="Map of events"><EventMap events={filteredEvents} userPosition={userPosition} selectedEvent={selectedEvent} /></section>
      <EventSidebar events={filteredEvents} filters={filters} onChange={setFilters} onReset={resetFilters} onSelect={(event) => setSelectedEvent({ ...event })} />
    </main>
  </div>;
}
