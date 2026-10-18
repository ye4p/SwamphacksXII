import { useMemo, useState } from "react";
import { ArrowRight, ArrowUpRight, CalendarDays, Check, Clock3, Heart, MapPin, UserRound } from "lucide-react";
import type { FavoriteOrganization as Organization } from "../../lib/favorites";
import type { Event } from "../../types";
import { useAuth } from "../../hooks/useAuth";
import { apiErrorMessage } from "../../lib/api";

type UpcomingEvent = Event & {
  organization: Organization;
};

function eventDate(timestamp: string) {
  const date = new Date(timestamp);
  return {
    day: new Intl.DateTimeFormat("en-US", { day: "2-digit" }).format(date),
    weekday: new Intl.DateTimeFormat("en-US", { weekday: "short" }).format(date).toUpperCase(),
    month: new Intl.DateTimeFormat("en-US", { month: "short" }).format(date).toUpperCase(),
    time: new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(date),
  };
}

export default function ProfilePage({ events, onBack, onExploreOrganizations, onSelectEvent }: {
  events: Event[]; onBack: () => void; onExploreOrganizations: () => void; onSelectEvent: (event: Event) => void;
}) {
  const { user, isLoading, isAuthenticated, login, logout, favorites: favoriteOrganizations, favoritesLoading, favoritesError, error, refetch, updateFavorite } = useAuth();
  const [selectedOrganization, setSelectedOrganization] = useState("all");
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  async function perform(action: () => Promise<void>) {
    setPending(true); setActionError(null);
    try { await action(); } catch (cause) { setActionError(apiErrorMessage(cause, "Unable to save changes. Please try again.")); }
    finally { setPending(false); }
  }
  const upcomingEvents = useMemo<UpcomingEvent[]>(() => favoriteOrganizations
    .flatMap((organization) => events
      .filter((event) => event.organization_id === organization.id && Date.parse(event.timestamp) >= Date.now())
      .map((event) => ({ ...event, organization })))
    .sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp)),
  [events, favoriteOrganizations]);
  const visibleEvents = selectedOrganization === "all"
    ? upcomingEvents
    : upcomingEvents.filter((event) => String(event.organization.id) === selectedOrganization);

  if (isLoading) return <main className="page-status" role="status">Loading profile…</main>;
  if (!isAuthenticated || !user) return <main className="profile-page"><h1>Your profile</h1>{error && <p role="alert">{error} <button onClick={() => void refetch()}>Retry</button></p>}<p>Log in to see your favorite organizations and upcoming events.</p><button className="primary-button" onClick={login}>Log in / Sign up</button></main>;

  return (
    <main className="profile-page">
      <section className="profile-page-intro">
        <div>
          <h1>Your campus, in one place.</h1>
          <p>Stay connected to the organizations and events you care about.</p>
        </div>
        <div className="profile-page-actions">
          <button className="outline-button" disabled={pending} onClick={() => void perform(logout)}>Log out</button>
          <button className="profile-explore-button" onClick={onBack}><ArrowUpRight size={15} /> Explore events</button>
        </div>
      </section>

      {(actionError || favoritesError) && <p role="alert">{actionError || favoritesError}</p>}
      {favoritesLoading && <p role="status">Loading favorites…</p>}
      <section className="profile-summary">
        <div className="profile-summary-person">
          <span className="profile-avatar">{user.picture ? <img src={user.picture} alt="Your profile" /> : <UserRound size={26} />}</span>
          <div className="profile-summary-identity">
            <div className="profile-name-line"><h2>{user.name || "Your account"}</h2><span>{user.email}</span></div>
          </div>
        </div>
        <div className="profile-summary-stats">
          <div><strong>{favoriteOrganizations.length}</strong><span>Favorite organizations</span></div>
          <div><strong>{upcomingEvents.length}</strong><span>Upcoming events</span></div>
        </div>
      </section>

      <div className="profile-dashboard">
        <section className="profile-favorites-section">
          <div className="profile-section-heading">
            <div><h2>Favorite organizations <span>{favoriteOrganizations.length}</span></h2><p>Your people. Your interests.</p></div>
          </div>
          {favoriteOrganizations.length ? <div className="profile-favorite-list">
            {favoriteOrganizations.map((organization) => <FavoriteOrganizationCard
              key={organization.id}
              organization={organization}
              events={upcomingEvents.filter((event) => event.organization.id === organization.id)}
              pending={pending}
              onRemove={() => void perform(() => updateFavorite(organization.id, false))}
            />)}
          </div> : <div className="profile-empty-favorites">
            <Heart size={20} />
            <p>Favorite an organization to keep up with its events.</p>
          </div>}
          <div className="profile-discover-card">
            <p>Make campus feel a little more like you. Find your next community.</p>
            <button onClick={onExploreOrganizations}><span aria-hidden="true">＋</span> Discover organizations</button>
          </div>
        </section>

        <section className="profile-upcoming-section" id="upcoming-events">
          <div className="profile-section-heading profile-upcoming-heading">
            <div><h2>Upcoming events</h2><p>The next 30 days from your favorite organizations.</p></div>
            <span className="profile-month"><CalendarDays size={13} /> {new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" }).format(new Date())}</span>
          </div>
          {favoriteOrganizations.length > 0 && <div className="profile-event-filters" aria-label="Filter events by organization">
            <button className={selectedOrganization === "all" ? "is-active" : ""} onClick={() => setSelectedOrganization("all")}>All favorites <span>{upcomingEvents.length}</span></button>
            {favoriteOrganizations.map((organization) => (
              <button key={organization.id} className={selectedOrganization === String(organization.id) ? "is-active" : ""} onClick={() => setSelectedOrganization(String(organization.id))}>
                {organization.name} <span>{upcomingEvents.filter((event) => event.organization.id === organization.id).length}</span>
              </button>
            ))}
          </div>}
          {visibleEvents.length ? <div className="profile-upcoming-list">
            {visibleEvents.map((event) => <UpcomingEventRow key={event.id} event={event} onSelect={() => onSelectEvent(event)} />)}
          </div> : <div className="profile-empty-events">
            <CalendarDays size={20} />
            <p>{favoriteOrganizations.length ? "No upcoming events from this organization yet." : "Favorite an organization to see its upcoming events here."}</p>
          </div>}
          {visibleEvents.length > 0 && <p className="profile-caught-up"><Check size={14} /> You&apos;re all caught up with your favorites.</p>}
        </section>
      </div>
    </main>
  );
}

function FavoriteOrganizationCard({ organization, events, onRemove, pending }: { organization: Organization; events: UpcomingEvent[]; pending: boolean; onRemove: () => void }) {
  const nextEvent = events[0];
  return (
    <article className="profile-favorite-card">
      <div className="profile-favorite-title">
        <span className="profile-org-icon">{organization.name.slice(0, 2).toUpperCase()}</span>
        <div><h3>{organization.name}</h3><p>{organization.role}</p></div>
        <button disabled={pending} aria-label={`Remove ${organization.name} from favorites`} onClick={onRemove}><Heart size={15} fill="currentColor" /></button>
      </div>
      <p className="profile-favorite-description">{organization.description}</p>
      <strong className="profile-favorite-event-count"><CalendarDays size={13} /> {events.length} upcoming {events.length === 1 ? "event" : "events"}</strong>
      <div className="profile-favorite-next"><span>Next up · {nextEvent ? eventDate(nextEvent.timestamp).month.slice(0, 3) + " " + eventDate(nextEvent.timestamp).day : "Coming soon"}</span><ArrowRight size={14} /></div>
    </article>
  );
}

function UpcomingEventRow({ event, onSelect }: { event: UpcomingEvent; onSelect: () => void }) {
  const date = eventDate(event.timestamp);
  return (
    <article className="profile-upcoming-row">
      <time className="profile-event-date" dateTime={event.timestamp}>
        <span>{date.month}</span><strong>{date.day}</strong><small>{date.weekday}</small>
      </time>
      <div className="profile-upcoming-details">
        <p className="profile-event-org">{event.organization.name} <span>·</span> {event.payload.tags?.[0] ?? "Event"}</p>
        <h3>{event.title}</h3>
        <p className="profile-event-meta"><span><Clock3 size={12} /> {date.time}</span><span><MapPin size={12} /> {event.address.split(",")[0] || "Location TBD"}</span></p>
      </div>
      <div className="profile-event-action"><button className="text-button" onClick={onSelect}>View on map <ArrowRight size={13} /></button><span>{event.payload.notes}</span></div>
    </article>
  );
}
