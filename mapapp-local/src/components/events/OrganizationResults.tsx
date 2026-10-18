import { useEffect, useMemo, useState } from "react";
import { ArrowRight, CalendarDays, ExternalLink, Heart, SlidersHorizontal } from "lucide-react";
import organizations from "../../data/organizations";
import type { Organization } from "../../data/organizations";
import { FAVORITES_STORAGE_KEY, loadFavoriteIds } from "../../data/localProfile";

const interestOptions = ["Programming", "Hackathons", "Artificial intelligence", "Cybersecurity"];

function displayDate(timestamp: string) {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(timestamp));
}

export default function OrganizationResults({
  query,
  onModeChange,
}: {
  query: string;
  onModeChange: (mode: "events" | "organizations") => void;
}) {
  const [category, setCategory] = useState("All categories");
  const [interests, setInterests] = useState<string[]>([]);
  const [upcomingWindow, setUpcomingWindow] = useState("any");
  const [beginnerFriendly, setBeginnerFriendly] = useState(false);
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [sortOrder, setSortOrder] = useState("match");
  const [favorites, setFavorites] = useState<number[]>(loadFavoriteIds);
  const [expandedOrganization, setExpandedOrganization] = useState<number | null>(null);

  useEffect(() => {
    localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(favorites));
  }, [favorites]);

  useEffect(() => {
    localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(favorites));
  }, [favorites]);

  const matchingOrganizations = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    const cutoff = upcomingWindow === "week"
      ? Date.now() + 7 * 24 * 60 * 60 * 1000
      : upcomingWindow === "month"
        ? Date.now() + 30 * 24 * 60 * 60 * 1000
        : Number.POSITIVE_INFINITY;

    return organizations.filter((organization) => {
      const searchableText = [
        organization.name,
        organization.category,
        organization.description,
        ...organization.interests,
        ...organization.events.map((event) => event.title),
      ].join(" ").toLocaleLowerCase();
      const hasUpcomingEvent = organization.events.some((event) => {
        const timestamp = Date.parse(event.timestamp);
        return timestamp >= Date.now() && timestamp <= cutoff;
      });
      return (!needle || searchableText.includes(needle))
        && (category === "All categories" || organization.category === category)
        && (!interests.length || interests.some((interest) => organization.interests.includes(interest)))
        && (upcomingWindow === "any" || hasUpcomingEvent)
        && (!beginnerFriendly || organization.beginnerFriendly)
        && (!favoritesOnly || favorites.includes(organization.id));
    }).sort((left, right) => sortOrder === "name"
      ? left.name.localeCompare(right.name)
      : sortOrder === "events"
        ? right.events.length - left.events.length
        : scoreMatch(right, needle) - scoreMatch(left, needle));
  }, [query, category, interests, upcomingWindow, beginnerFriendly, favoritesOnly, favorites, sortOrder]);

  const clearFilters = () => {
    setCategory("All categories");
    setInterests([]);
    setUpcomingWindow("any");
    setBeginnerFriendly(false);
    setFavoritesOnly(false);
  };

  const toggleInterest = (interest: string) => {
    setInterests((current) => current.includes(interest)
      ? current.filter((item) => item !== interest)
      : [...current, interest]);
  };

  const toggleFavorite = (organizationId: number) => {
    setFavorites((current) => current.includes(organizationId)
      ? current.filter((id) => id !== organizationId)
      : [...current, organizationId]);
  };

  const countForInterest = (interest: string) => organizations.filter((organization) => organization.interests.includes(interest)).length;
  const countForCategory = (categoryName: string) => organizations.filter((organization) => organization.category === categoryName).length;

  return (
    <main className="search-results-page organization-results-page">
      <div className="results-breadcrumb"><a href="/">Explore campus</a><span>/</span><span>Organizations</span></div>
      <nav className="search-mode-tabs" aria-label="Search type">
        <button type="button" className="search-mode-tab" onClick={() => onModeChange("events")}>Events</button>
        <button type="button" className="search-mode-tab is-active" aria-current="page">Organizations</button>
      </nav>
      <section className="results-intro">
        <div>
          <h1>{query ? `Organizations for "${query}"` : "All Organizations"}</h1>
          <p>Find your people at UF. Explore communities that code, build, and learn together.</p>
        </div>
        <button className={`outline-button favorite-organizations${favoritesOnly ? " is-favorite" : ""}`} onClick={() => setFavoritesOnly(!favoritesOnly)}>
          <Heart size={16} fill={favoritesOnly ? "currentColor" : "none"} /> {favoritesOnly ? "Showing favorites" : "Favorite organizations"}
        </button>
      </section>

      <div className="results-layout">
        <aside className="results-filters organization-filters" aria-label="Filter organizations">
          <div className="results-filter-heading"><strong>Filter organizations</strong><SlidersHorizontal size={16} /></div>
          <section className="results-filter-group">
            <h2>Category</h2>
            <label className="organization-select">
              <span className="sr-only">Organization category</span>
              <select value={category} onChange={(event) => setCategory(event.target.value)}>
                <option>All categories</option>
                <option>Technology</option>
                <option>Arts &amp; culture</option>
                <option>Academic</option>
                <option>Sports</option>
              </select>
            </label>
            {category !== "All categories" && <small className="organization-filter-count">{countForCategory(category)} organizations</small>}
          </section>
          <section className="results-filter-group">
            <h2>Interests</h2>
            {interestOptions.map((interest) => (
              <label className="results-checkbox" key={interest}>
                <input type="checkbox" checked={interests.includes(interest)} onChange={() => toggleInterest(interest)} />
                <span>{interest}</span><small>{countForInterest(interest)}</small>
              </label>
            ))}
          </section>
          <section className="results-filter-group">
            <h2>Upcoming events</h2>
            <label className="organization-select">
              <span className="sr-only">Upcoming event time</span>
              <select value={upcomingWindow} onChange={(event) => setUpcomingWindow(event.target.value)}>
                <option value="any">Any time</option>
                <option value="week">Next 7 days</option>
                <option value="month">Next 30 days</option>
              </select>
            </label>
          </section>
          <section className="results-filter-group organization-checkbox-group">
            <label className="results-checkbox">
              <input type="checkbox" checked={beginnerFriendly} onChange={(event) => setBeginnerFriendly(event.target.checked)} />
              <span>Beginner friendly</span>
            </label>
            <label className="results-checkbox">
              <input type="checkbox" checked={favoritesOnly} onChange={(event) => setFavoritesOnly(event.target.checked)} />
              <span>My favorites only</span>
            </label>
          </section>
          <button className="clear-filters-button" onClick={clearFilters}>Reset all filters</button>
          <aside className="favorite-prompt">
            <Heart size={18} />
            <strong>Keep your people close.</strong>
            <p>Favorite an organization to see its upcoming events on your profile.</p>
          </aside>
        </aside>

        <section className="results-content" aria-label="Organization search results">
          <div className="results-toolbar">
            <div><strong>{matchingOrganizations.length} {matchingOrganizations.length === 1 ? "organization" : "organizations"}</strong><span>at University of Florida</span></div>
            <label className="sort-control">Sort by:
              <select aria-label="Sort organizations" value={sortOrder} onChange={(event) => setSortOrder(event.target.value)}>
                <option value="match">Best match</option>
                <option value="events">Most upcoming events</option>
                <option value="name">Organization name</option>
              </select>
            </label>
          </div>
          {(query || category !== "All categories" || interests.length > 0 || upcomingWindow !== "any" || beginnerFriendly || favoritesOnly) && (
            <div className="active-filters" aria-label="Active filters">
              {query && <span className="filter-chip">{query}</span>}
              {category !== "All categories" && <button className="filter-chip" onClick={() => setCategory("All categories")}>{category}<span aria-hidden="true">×</span></button>}
              {interests.map((interest) => <button className="filter-chip" key={interest} onClick={() => toggleInterest(interest)}>{interest}<span aria-hidden="true">×</span></button>)}
              {upcomingWindow !== "any" && <button className="filter-chip" onClick={() => setUpcomingWindow("any")}>{upcomingWindow === "week" ? "Next 7 days" : "Next 30 days"}<span aria-hidden="true">×</span></button>}
              {beginnerFriendly && <button className="filter-chip" onClick={() => setBeginnerFriendly(false)}>Beginner friendly<span aria-hidden="true">×</span></button>}
              {favoritesOnly && <button className="filter-chip" onClick={() => setFavoritesOnly(false)}>My favorites<span aria-hidden="true">×</span></button>}
              <button className="clear-chip" onClick={clearFilters}>Clear filters</button>
            </div>
          )}
          {matchingOrganizations.length ? (
            <div className="organization-grid">
              {matchingOrganizations.map((organization) => (
                <OrganizationCard
                  key={organization.id}
                  organization={organization}
                  favorite={favorites.includes(organization.id)}
                  expanded={expandedOrganization === organization.id}
                  onFavorite={() => toggleFavorite(organization.id)}
                  onExpand={() => setExpandedOrganization((current) => current === organization.id ? null : organization.id)}
                />
              ))}
            </div>
          ) : (
            <div className="results-empty">
              <div className="results-empty-icon"><SlidersHorizontal size={22} /></div>
              <h2>No organizations match these filters</h2>
              <p>Try a different search or clear some filters to find your community.</p>
              <button className="outline-button" onClick={clearFilters}>Clear filters</button>
            </div>
          )}
          {matchingOrganizations.length > 0 && <p className="results-footer-note"><span aria-hidden="true">✓</span> You&apos;ve seen all {matchingOrganizations.length} matches.</p>}
        </section>
      </div>
    </main>
  );
}

function scoreMatch(organization: Organization, query: string) {
  if (!query) return organization.events.length;
  const name = organization.name.toLocaleLowerCase();
  const description = organization.description.toLocaleLowerCase();
  const interests = organization.interests.join(" ").toLocaleLowerCase();
  return (name.includes(query) ? 3 : 0) + (interests.includes(query) ? 2 : 0) + (description.includes(query) ? 1 : 0) + organization.events.length / 10;
}

function OrganizationCard({
  organization,
  favorite,
  expanded,
  onFavorite,
  onExpand,
}: {
  organization: Organization;
  favorite: boolean;
  expanded: boolean;
  onFavorite: () => void;
  onExpand: () => void;
}) {
  const nextEvent = organization.events[0];
  return (
    <article className="organization-card">
      <div className="organization-card-heading">
        <span className="organization-icon" aria-hidden="true">{organization.icon}</span>
        <div className="organization-heading-copy">
          <h2>{organization.name}</h2>
          <p>{organization.category} · {organization.interests.join(" · ")}</p>
        </div>
        <button className={`organization-favorite${favorite ? " is-favorite" : ""}`} onClick={onFavorite} aria-label={`${favorite ? "Unfavorite" : "Favorite"} ${organization.name}`} aria-pressed={favorite}>
          <Heart size={17} fill={favorite ? "currentColor" : "none"} />
        </button>
      </div>
      <a className="organization-gatorconnect-link" href={organization.gatorConnectUrl} target="_blank" rel="noreferrer" aria-label={`Open ${organization.name} on GatorConnect`}>
        GatorConnect <ExternalLink size={12} />
      </a>
      <p className="organization-description">{organization.description}</p>
      <div className="organization-event-summary">
        <strong><CalendarDays size={13} /> {organization.events.length} upcoming {organization.events.length === 1 ? "event" : "events"}</strong>
        {nextEvent && <span>{displayDate(nextEvent.timestamp)}</span>}
      </div>
      {nextEvent && <p className="organization-next-event">Next up · {nextEvent.title}</p>}
      <footer className="organization-card-footer">
        {organization.beginnerFriendly && <span className="beginner-badge">Beginner friendly</span>}
        <button onClick={onExpand}>{expanded ? "Hide details" : "View organization"} <ArrowRight size={14} /></button>
      </footer>
      {expanded && (
        <div className="organization-details">
          <strong>Upcoming events</strong>
          {organization.events.map((event) => <p key={event.title}>{event.title}<time>{displayDate(event.timestamp)}</time></p>)}
        </div>
      )}
    </article>
  );
}
