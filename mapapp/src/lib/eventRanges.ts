export const EVENT_DAY_RANGES = [1, 7, 14, 30] as const;
export type EventDays = typeof EVENT_DAY_RANGES[number];
export const DEFAULT_EVENT_DAYS: EventDays = 1;
export function eventRangeLabel(days: EventDays): string {
  return `Within ${days} ${days === 1 ? "day" : "days"}`;
}
