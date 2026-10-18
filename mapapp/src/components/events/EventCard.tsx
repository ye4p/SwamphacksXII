import type { Event } from "../../types";
import { formatEventDate } from "../../utils/eventDate";

export default function EventCard({ event, onSelect }: { event: Event; onSelect: (event: Event) => void }) {
  return (
    <article className="event-card">
      <time dateTime={event.timestamp}>{formatEventDate(event.timestamp)}</time>
      <h3><button onClick={() => onSelect(event)}>{event.title}<span aria-hidden="true"> ↗</span></button></h3>
      {event.address && <div className="meta">{event.address}</div>}
      <p>{event.description}</p>
      <div className="tags">{(event.payload?.tags ?? []).map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div>
    </article>
  );
}
