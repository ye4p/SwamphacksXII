import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, CalendarDays, Check, Clock3, MapPin, Pencil, Plus, Trash2, X } from "lucide-react";
import organizations from "../../data/organizations";

const STORAGE_KEY = "swampsearch-officer-events";

interface OfficerEvent {
  id: string;
  organizationId: number;
  title: string;
  description: string;
  date: string;
  startTime: string;
  endTime: string;
  location: string;
  room: string;
}

const defaultEvents: OfficerEvent[] = [
  { id: "officer-1", organizationId: 1, title: "Build night", description: "Bring a project, pair up, and build something together.", date: "2026-10-22", startTime: "18:00", endTime: "20:00", location: "Innovation Hall", room: "Project Lab · Room 204" },
  { id: "officer-2", organizationId: 2, title: "Mentor office hours", description: "Get feedback on your idea from experienced mentors.", date: "2026-10-23", startTime: "16:00", endTime: "17:30", location: "Student Union", room: "Collaboration Lounge" },
  { id: "officer-3", organizationId: 1, title: "Modern C++ workshop", description: "Explore smart pointers and write cleaner, safer code.", date: "2026-10-23", startTime: "18:00", endTime: "19:30", location: "Innovation Hall", room: "Computer Lab · Room 202" },
  { id: "officer-4", organizationId: 2, title: "Hackathon project review", description: "Share your demo and get your team ready to present.", date: "2026-10-24", startTime: "14:00", endTime: "16:00", location: "Student Union", room: "Meeting Room 3" },
  { id: "officer-5", organizationId: 1, title: "Coding practice circle", description: "Work through coding challenges with your club.", date: "2026-10-25", startTime: "15:00", endTime: "17:00", location: "Innovation Hall", room: "Project Lab · Room 204" },
];

const blankEvent = (): Omit<OfficerEvent, "id"> => ({
  organizationId: 1,
  title: "",
  description: "",
  date: "",
  startTime: "18:00",
  endTime: "19:00",
  location: "",
  room: "",
});

function loadEvents(): OfficerEvent[] {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (!saved) return defaultEvents;
  try {
    const parsed: unknown = JSON.parse(saved);
    if (Array.isArray(parsed) && parsed.every(isOfficerEvent)) return parsed;
  } catch {
    return defaultEvents;
  }
  return defaultEvents;
}

function isOfficerEvent(value: unknown): value is OfficerEvent {
  if (typeof value !== "object" || value === null) return false;
  const event = value as Record<string, unknown>;
  return typeof event.id === "string"
    && typeof event.organizationId === "number"
    && typeof event.title === "string"
    && typeof event.description === "string"
    && typeof event.date === "string"
    && typeof event.startTime === "string"
    && typeof event.endTime === "string"
    && typeof event.location === "string"
    && typeof event.room === "string";
}

function formatDate(date: string) {
  return new Date(`${date}T12:00:00`).toLocaleDateString("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
}

function formatTime(time: string) {
  const [hourString, minute] = time.split(":");
  const hour = Number(hourString);
  return `${hour % 12 || 12}:${minute} ${hour >= 12 ? "PM" : "AM"}`;
}

function weekRange(date: Date) {
  const start = new Date(date);
  const weekday = (start.getDay() + 6) % 7;
  if (start.getDay() === 0) start.setDate(start.getDate() + 1);
  else start.setDate(start.getDate() - weekday);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 7);
  return { start, end };
}

function formatWeekRange(start: Date, end: Date) {
  const lastDay = new Date(end);
  lastDay.setDate(lastDay.getDate() - 1);
  const month = new Intl.DateTimeFormat("en-US", { month: "short" }).format(start);
  const startDay = new Intl.DateTimeFormat("en-US", { day: "numeric" }).format(start);
  const endDay = new Intl.DateTimeFormat("en-US", { day: "numeric" }).format(lastDay);
  const year = new Intl.DateTimeFormat("en-US", { year: "numeric" }).format(lastDay);
  return `${month} ${startDay}–${endDay}, ${year}`;
}

export default function OfficerEventsPage({ onBack }: { onBack: () => void }) {
  const [events, setEvents] = useState<OfficerEvent[]>(loadEvents);
  const [selectedOrganization, setSelectedOrganization] = useState("all");
  const [dateFilter, setDateFilter] = useState("week");
  const [sortOrder, setSortOrder] = useState("soonest");
  const [editingEvent, setEditingEvent] = useState<OfficerEvent | null>(null);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(events));
  }, [events]);

  const range = useMemo(() => weekRange(new Date()), []);
  const visibleEvents = useMemo(() => events
    .filter((event) => selectedOrganization === "all" || String(event.organizationId) === selectedOrganization)
    .filter((event) => {
      const date = new Date(`${event.date}T12:00:00`);
      if (dateFilter === "week") return date >= range.start && date < range.end;
      if (dateFilter === "month") return date.getMonth() === new Date().getMonth() && date.getFullYear() === new Date().getFullYear();
      return date >= new Date(new Date().toDateString());
    })
    .sort((left, right) => sortOrder === "latest"
      ? `${right.date}T${right.startTime}`.localeCompare(`${left.date}T${left.startTime}`)
      : `${left.date}T${left.startTime}`.localeCompare(`${right.date}T${right.startTime}`)),
  [events, selectedOrganization, dateFilter, range, sortOrder]);

  const openAddForm = () => {
    setEditingEvent(null);
    setShowForm(true);
  };
  const openEditForm = (event: OfficerEvent) => {
    setEditingEvent(event);
    setShowForm(true);
  };
  const saveEvent = (event: Omit<OfficerEvent, "id">) => {
    if (editingEvent) {
      setEvents((current) => current.map((item) => item.id === editingEvent.id ? { ...event, id: item.id } : item));
    } else {
      setEvents((current) => [...current, { ...event, id: crypto.randomUUID() }]);
    }
    setShowForm(false);
    setEditingEvent(null);
  };
  const deleteEvent = (eventId: string) => {
    setEvents((current) => current.filter((item) => item.id !== eventId));
    setShowForm(false);
    setEditingEvent(null);
  };

  return (
    <main className="officer-events-page">
      <button className="officer-back-link" onClick={onBack}><ArrowLeft size={14} /> Back to Profile</button>
      <div className="officer-page-title">
        <div><h1>Upcoming events</h1><p>Review and edit upcoming events for the clubs you lead.</p></div>
        <button className="officer-add-button" onClick={openAddForm}><Plus size={15} /> Add Event</button>
      </div>

      <div className="officer-toolbar">
        <div className="officer-club-tabs" aria-label="Filter by club">
          <button className={selectedOrganization === "all" ? "is-active" : ""} onClick={() => setSelectedOrganization("all")}>All clubs <span>{events.length}</span></button>
          {organizations.filter((organization) => [1, 2].includes(organization.id)).map((organization) => (
            <button key={organization.id} className={selectedOrganization === String(organization.id) ? "is-active" : ""} onClick={() => setSelectedOrganization(String(organization.id))}>
              {organization.name} <span>{events.filter((event) => event.organizationId === organization.id).length}</span>
            </button>
          ))}
        </div>
        <label className="officer-date-select"><CalendarDays size={13} />
          <select aria-label="Filter events by date" value={dateFilter} onChange={(event) => setDateFilter(event.target.value)}>
            <option value="week">This week</option>
            <option value="month">This month</option>
            <option value="any">Any time</option>
          </select>
        </label>
      </div>
      <div className="officer-results-meta">
        <span>{visibleEvents.length} upcoming events · {formatWeekRange(range.start, range.end)}</span>
        <label>Sort by
          <select aria-label="Sort upcoming events" value={sortOrder} onChange={(event) => setSortOrder(event.target.value)}>
            <option value="soonest">Soonest first ↓</option>
            <option value="latest">Latest first ↑</option>
          </select>
        </label>
      </div>

      {visibleEvents.length ? <div className="officer-event-list">
        {visibleEvents.map((event) => {
          const organization = organizations.find((item) => item.id === event.organizationId);
          const date = new Date(`${event.date}T12:00:00`);
          return (
            <article className="officer-event-card" key={event.id}>
              <time className="officer-event-date" dateTime={event.date}>
                <span>{date.toLocaleDateString("en-US", { month: "short" }).toUpperCase()}</span>
                <strong>{date.toLocaleDateString("en-US", { day: "2-digit" })}</strong>
              </time>
              <div className="officer-event-info">
                <div className="officer-event-title-line"><h2>{event.title}</h2><span>{organization?.name ?? "Club"}</span></div>
                <p>{event.description}</p>
              </div>
              <div className="officer-event-schedule">
                <span>{formatDate(event.date)}</span>
                <small><Clock3 size={12} /> {formatTime(event.startTime)}–{formatTime(event.endTime)}</small>
              </div>
              <div className="officer-event-location">
                <span><MapPin size={12} /> {event.location || "Location TBD"}</span>
                <small>{event.room}</small>
              </div>
              <button className="officer-edit-button" onClick={() => openEditForm(event)}><Pencil size={13} /> Edit Event</button>
            </article>
          );
        })}
      </div> : <div className="officer-empty-state"><CalendarDays size={22} /><p>No upcoming events in this date range.</p><button onClick={openAddForm}>Add an event</button></div>}

      <p className="officer-caught-up"><Check size={13} /> You&apos;re all caught up.</p>
      {showForm && <EventEditorForm initialEvent={editingEvent} onSave={saveEvent} onDelete={deleteEvent} onClose={() => setShowForm(false)} />}
    </main>
  );
}

function EventEditorForm({
  initialEvent,
  onSave,
  onDelete,
  onClose,
}: {
  initialEvent: OfficerEvent | null;
  onSave: (event: Omit<OfficerEvent, "id">) => void;
  onDelete: (eventId: string) => void;
  onClose: () => void;
}) {
  const [form, setForm] = useState<Omit<OfficerEvent, "id">>(initialEvent
    ? {
      organizationId: initialEvent.organizationId,
      title: initialEvent.title,
      description: initialEvent.description,
      date: initialEvent.date,
      startTime: initialEvent.startTime,
      endTime: initialEvent.endTime,
      location: initialEvent.location,
      room: initialEvent.room,
    }
    : blankEvent());

  const update = (field: keyof typeof form, value: string | number) => setForm((current) => ({ ...current, [field]: value }));

  return (
    <div className="officer-modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <form className="officer-event-form" onSubmit={(event) => {
        event.preventDefault();
        onSave(form);
      }}>
        <div className="officer-form-heading"><div><h2>{initialEvent ? "Edit event" : "Add event"}</h2><p>Update event details for your club.</p></div><button type="button" aria-label="Close event form" onClick={onClose}><X size={18} /></button></div>
        <label>Club<select required value={form.organizationId} onChange={(event) => update("organizationId", Number(event.target.value))}>
          {organizations.filter((organization) => [1, 2].includes(organization.id)).map((organization) => <option value={organization.id} key={organization.id}>{organization.name}</option>)}
        </select></label>
        <label>Event name<input required value={form.title} onChange={(event) => update("title", event.target.value)} /></label>
        <label>Description<textarea rows={3} value={form.description} onChange={(event) => update("description", event.target.value)} /></label>
        <div className="officer-form-row">
          <label>Date<input required type="date" value={form.date} onChange={(event) => update("date", event.target.value)} /></label>
          <label>Start time<input required type="time" value={form.startTime} onChange={(event) => update("startTime", event.target.value)} /></label>
          <label>End time<input required type="time" value={form.endTime} onChange={(event) => update("endTime", event.target.value)} /></label>
        </div>
        <label>Location<input required value={form.location} onChange={(event) => update("location", event.target.value)} /></label>
        <label>Room or details<input value={form.room} onChange={(event) => update("room", event.target.value)} /></label>
        <div className="officer-form-actions">
          {initialEvent && <button type="button" className="officer-delete-button" onClick={() => {
            if (window.confirm(`Delete "${initialEvent.title}"? This action cannot be undone.`)) onDelete(initialEvent.id);
          }}><Trash2 size={13} /> Delete Event</button>}
          <div className="officer-form-actions-end"><button type="button" className="officer-cancel-button" onClick={onClose}>Cancel</button><button type="submit" className="officer-add-button">{initialEvent ? "Save changes" : "Add Event"}</button></div>
        </div>
      </form>
    </div>
  );
}
