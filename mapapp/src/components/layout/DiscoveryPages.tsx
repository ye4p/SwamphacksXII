import { useEvents } from "../../hooks/useEvents";
import { useOrganizations } from "../../hooks/useOrganizations";
import type { Event } from "../../types";
import SearchResults from "../events/SearchResults";
import OrganizationResults from "../events/OrganizationResults";
import ProfilePage from "./ProfilePage";

export default function DiscoveryPages({ pathname, search, onSearch, onBack, onSelectEvent }: {
  pathname: string; search: string;
  onSearch: (query: string, mode?: "events" | "organizations") => void;
  onBack: () => void; onSelectEvent: (event: Event) => void;
}) {
  const { events, loading, error } = useEvents(30);
  const { organizations, loading: organizationsLoading, error: organizationsError } = useOrganizations();
  const params = new URLSearchParams(search);
  const query = params.get("q") ?? "";
  if (pathname === "/profile") return <>
    {loading && <p className="page-status" role="status">Loading upcoming events…</p>}
    {error && <p className="page-status" role="alert">{error}</p>}
    <ProfilePage events={events} onBack={onBack} onExploreOrganizations={() => onSearch("", "organizations")} onSelectEvent={onSelectEvent} />
  </>;
  if (loading || organizationsLoading) return <main className="page-status" role="status">Loading search results…</main>;
  if (error || organizationsError) return <main className="page-status" role="alert">{error || organizationsError}<p><button className="outline-button" onClick={() => window.location.reload()}>Retry</button></p></main>;
  const onModeChange = (mode: "events" | "organizations") => onSearch(query, mode);
  return params.get("type") === "organizations"
    ? <OrganizationResults organizations={organizations} events={events} query={query} onModeChange={onModeChange} />
    : <SearchResults organizations={organizations} events={events} query={query} onModeChange={onModeChange} />;
}
