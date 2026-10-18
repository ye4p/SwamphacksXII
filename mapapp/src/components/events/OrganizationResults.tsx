import { useState } from "react";
import { CalendarDays, Heart } from "lucide-react";
import type { Organization } from "../../lib/organizations";
import type { Event } from "../../types";
import { useAuth } from "../../hooks/useAuth";
import { apiErrorMessage } from "../../lib/api";

export default function OrganizationResults({ organizations, events, query, onModeChange }: {
  organizations: Organization[]; events: Event[]; query: string; onModeChange: (mode: "events" | "organizations") => void;
}) {
  const { favorites, favoritesLoading, favoritesError, isAuthenticated, login, updateFavorite } = useAuth();
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [sort, setSort] = useState("name");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const upcoming = (id: number) => events.filter((event) => event.organization_id === id && Date.parse(event.timestamp) >= Date.now()).sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
  const isFavorite = (id: number) => favorites.some((org) => org.id === id);
  const matches = organizations.filter((org) => `${org.name} ${org.description ?? ""}`.toLowerCase().includes(query.trim().toLowerCase()) && (!favoritesOnly || isFavorite(org.id))).sort((a, b) => sort === "events" ? upcoming(b.id).length - upcoming(a.id).length : a.name.localeCompare(b.name));
  async function toggleFavorite(id: number) {
    if (!isAuthenticated) { login(); return; }
    setPending(true); setError(null);
    try { await updateFavorite(id, !isFavorite(id)); }
    catch (cause) { setError(apiErrorMessage(cause, "Unable to update favorites. Please try again.")); }
    finally { setPending(false); }
  }
  return <main className="search-results-page organization-results-page">
    <div className="results-breadcrumb"><a href="/">Explore campus</a><span>/</span><span>Organizations</span></div>
    <nav className="search-mode-tabs" aria-label="Search type"><button className="search-mode-tab" onClick={() => onModeChange("events")}>Events</button><button className="search-mode-tab is-active" aria-current="page">Organizations</button></nav>
    <section className="results-intro"><div><h1>{query ? `Organizations for "${query}"` : "All Organizations"}</h1><p>Find your people at UF. Explore your campus communities.</p></div><button className={`outline-button favorite-organizations${favoritesOnly ? " is-favorite" : ""}`} onClick={() => setFavoritesOnly(!favoritesOnly)}><Heart size={16} />{favoritesOnly ? "Showing favorites" : "Favorite organizations"}</button></section>
    {(error || favoritesError) && <p role="alert">{error || favoritesError}</p>}
    {favoritesLoading && <p role="status">Loading favorites…</p>}
    <div className="results-toolbar"><strong>{matches.length} organizations</strong><label className="sort-control">Sort by: <select value={sort} onChange={(event) => setSort(event.target.value)}><option value="name">Name</option><option value="events">Upcoming events</option></select></label></div>
    <div className="organization-grid">{matches.map((org) => {
      const orgEvents = upcoming(org.id);
      return <article className="organization-card" key={org.id}>
        <div className="organization-card-heading"><span className="organization-icon">{org.name.slice(0, 2).toUpperCase()}</span><div className="organization-heading-copy"><h2>{org.name}</h2></div><button className={`organization-favorite${isFavorite(org.id) ? " is-favorite" : ""}`} disabled={pending || favoritesLoading} aria-label={`${isFavorite(org.id) ? "Unfavorite" : "Favorite"} ${org.name}`} aria-pressed={isFavorite(org.id)} onClick={() => void toggleFavorite(org.id)}><Heart size={17} fill={isFavorite(org.id) ? "currentColor" : "none"} /></button></div>
        <p className="organization-description">{org.description || "No description provided."}</p>
        <div className="organization-event-summary"><strong><CalendarDays size={13} />{orgEvents.length} events in the next 30 days</strong></div>
        <footer className="organization-card-footer"><button onClick={() => setExpanded(expanded === org.id ? null : org.id)}>{expanded === org.id ? "Hide events" : "View events"}</button></footer>
        {expanded === org.id && <div className="organization-details">{orgEvents.length ? orgEvents.map((event) => <p key={event.id}>{event.title}<time dateTime={event.timestamp}>{new Date(event.timestamp).toLocaleDateString()}</time></p>) : <p>No upcoming events in the next 30 days.</p>}</div>}
      </article>;
    })}</div>
    {!matches.length && <div className="results-empty"><h2>No organizations found</h2><p>Try another search or turn off the favorites filter.</p></div>}
  </main>;
}
