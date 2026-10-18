import { EVENT_DAY_RANGES, eventRangeLabel, type EventDays } from "../../lib/eventRanges";

export default function EventRangeSelect({ id, days, onChange }: {
  id: string;
  days: EventDays;
  onChange: (days: EventDays) => void;
}) {
  return <div className="date-filters">
    <label htmlFor={id}>When
      <select id={id} value={days} onChange={(event) => {
        const selected = EVENT_DAY_RANGES.find((value) => value === Number(event.target.value));
        if (selected !== undefined) onChange(selected);
      }}>
        {EVENT_DAY_RANGES.map((value) => <option key={value} value={value}>{eventRangeLabel(value)}</option>)}
      </select>
    </label>
  </div>;
}
