import { useEffect, useMemo, useState } from "react";
import { ArrowRight, ArrowUpRight, CalendarDays, Check, Clock3, GraduationCap, Heart, MapPin, Moon, Pencil, Sun, UserRound } from "lucide-react";
import organizations from "../../data/organizations";
import type { Organization } from "../../data/organizations";
import type { Event } from "../../types";
import {
  FAVORITES_STORAGE_KEY,
  PROFILE_UPDATED_EVENT,
  PROFILE_STORAGE_KEY,
  loadFavoriteIds,
  loadLocalProfile,
  type LocalProfile,
} from "../../data/localProfile";

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

export default function ProfilePage({
  events,
  onBack,
  onExploreOrganizations,
  onOpenOfficerEvents,
  darkMode,
  onToggleTheme,
}: {
  events: Event[];
  onBack: () => void;
  onExploreOrganizations: () => void;
  onOpenOfficerEvents: () => void;
  darkMode: boolean;
  onToggleTheme: () => void;
}) {
  const [profile, setProfile] = useState<LocalProfile>(loadLocalProfile);
  const [favorites, setFavorites] = useState<number[]>(loadFavoriteIds);
  const [editing, setEditing] = useState(false);
  const [selectedOrganization, setSelectedOrganization] = useState("all");

  useEffect(() => {
    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profile));
    window.dispatchEvent(new Event(PROFILE_UPDATED_EVENT));
  }, [profile]);

  useEffect(() => {
    localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(favorites));
  }, [favorites]);

  const favoriteOrganizations = useMemo(
    () => organizations.filter((organization) => favorites.includes(organization.id)),
    [favorites],
  );
  const upcomingEvents = useMemo<UpcomingEvent[]>(() => favoriteOrganizations
    .flatMap((organization) => events
      .filter((event) => event.organization_id === organization.id && Date.parse(event.timestamp) >= Date.now())
      .map((event) => ({ ...event, organization })))
    .sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp)),
  [events, favoriteOrganizations]);
  const visibleEvents = selectedOrganization === "all"
    ? upcomingEvents
    : upcomingEvents.filter((event) => String(event.organization.id) === selectedOrganization);

  const toggleFavorite = (id: number) => {
    setFavorites((current) => current.includes(id)
      ? current.filter((favoriteId) => favoriteId !== id)
      : [...current, id]);
  };
  const updateProfile = (field: keyof LocalProfile, value: string) => {
    setProfile((current) => ({ ...current, [field]: value }));
  };

  return (
    <main className="profile-page">
      <section className="profile-page-intro">
        <div>
          <h1>Your campus, in one place.</h1>
          <p>Stay connected to the organizations and events you care about.</p>
        </div>
        <div className="profile-page-actions">
          <button className="profile-theme-button" type="button" onClick={onToggleTheme}>
            {darkMode ? <Sun size={14} /> : <Moon size={14} />}
            Switch to {darkMode ? "light" : "dark"} mode
          </button>
          <button className="profile-officer-button" type="button" onClick={onOpenOfficerEvents}>Officer Event Editor</button>
          <button className="profile-explore-button" onClick={onBack}><ArrowUpRight size={15} /> Explore events</button>
        </div>
      </section>

      <section className="profile-summary">
        <div className="profile-summary-person">
          <span className="profile-avatar">{profile.name.trim().split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase() || <UserRound size={26} />}</span>
          <div className="profile-summary-identity">
            <div className="profile-name-line"><h2>{profile.name}</h2><span>{profile.email}</span></div>
            <p>{profile.major} · {profile.classYear}</p>
            <small><GraduationCap size={13} /> University of Florida</small>
          </div>
        </div>
        <div className="profile-summary-stats">
          <div><strong>{favoriteOrganizations.length}</strong><span>Favorite organizations</span></div>
          <div><strong>{upcomingEvents.length}</strong><span>Upcoming events</span></div>
          <button className="profile-edit-button" onClick={() => setEditing(!editing)}><Pencil size={13} /> {editing ? "Done" : "Edit profile"}</button>
        </div>
      </section>

      {editing && <section className="profile-edit-panel" aria-label="Edit profile">
        <label>Name<input value={profile.name} onChange={(event) => updateProfile("name", event.target.value)} /></label>
        <label>UF email<input type="email" placeholder="johndoe@ufl.edu" value={profile.email} onChange={(event) => updateProfile("email", event.target.value)} /></label>
        <label>Major<input value={profile.major} onChange={(event) => updateProfile("major", event.target.value)} /></label>
        <label>Class year<input value={profile.classYear} onChange={(event) => updateProfile("classYear", event.target.value)} /></label>
        <p><Check size={14} /> Changes save on this device.</p>
      </section>}

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
              onRemove={() => toggleFavorite(organization.id)}
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
            <div><h2>Upcoming events</h2><p>The latest from your favorite organizations.</p></div>
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
            {visibleEvents.map((event) => <UpcomingEventRow key={`${event.organization.id}-${event.title}`} event={event} />)}
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

function FavoriteOrganizationCard({ organization, events, onRemove }: { organization: Organization; events: UpcomingEvent[]; onRemove: () => void }) {
  const nextEvent = events[0];
  return (
    <article className="profile-favorite-card">
      <div className="profile-favorite-title">
        <span className="profile-org-icon">{organization.icon}</span>
        <div><h3>{organization.name}</h3><p>{organization.category} · {organization.interests[0]}</p></div>
        <button aria-label={`Remove ${organization.name} from favorites`} onClick={onRemove}><Heart size={15} fill="currentColor" /></button>
      </div>
      <p className="profile-favorite-description">{organization.description}</p>
      <strong className="profile-favorite-event-count"><CalendarDays size={13} /> {events.length} upcoming {events.length === 1 ? "event" : "events"}</strong>
      <div className="profile-favorite-next"><span>Next up · {nextEvent ? eventDate(nextEvent.timestamp).month.slice(0, 3) + " " + eventDate(nextEvent.timestamp).day : "Coming soon"}</span><ArrowRight size={14} /></div>
    </article>
  );
}

function UpcomingEventRow({ event }: { event: UpcomingEvent }) {
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
      <div className="profile-event-action"><a href="#upcoming-events">View event <ArrowRight size={13} /></a><span>{event.payload.notes}</span></div>
    </article>
  );
}
