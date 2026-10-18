import { formatEventDate } from "../utils/eventDate";
import type { Event } from "../types";

interface EventPopupProps {
  event: Event;
}



export default function EventPopup({ event }: EventPopupProps) {

  const is_food: Boolean = event.tags?.includes("food") ?? false

  return (
    <div className="event-popup">
      <h3>{event.title}</h3>
      <div className="meta">{formatEventDate(event.start_time)}</div>
      <div className="meta">{event.description}</div>
      {is_food && <div className={`meta food`}>{"Food provided"}</div>}
      <div className="tags">
        {event.tags.map((t) => (
          <span key={t} className="tag">{t}</span>
        ))}
      </div>
    </div>
  );
}
