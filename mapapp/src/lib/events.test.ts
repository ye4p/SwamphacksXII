import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api";
import { getEvents } from "./events";
import { EVENT_DAY_RANGES } from "./eventRanges";

afterEach(() => vi.restoreAllMocks());

it.each(EVENT_DAY_RANGES)("requests a numeric %i-day range without a date parameter", async (days) => {
  const get = vi.spyOn(api, "get").mockResolvedValue({ data: { events: [] } });
  const controller = new AbortController();
  expect(await getEvents(days, controller.signal)).toEqual([]);
  expect(get).toHaveBeenCalledWith("/api/getEventsFromDay", {
    params: { days }, signal: controller.signal,
  });
});

it("rejects malformed responses instead of showing an empty successful result", async () => {
  vi.spyOn(api, "get").mockResolvedValue({ data: "<!doctype html>" });
  await expect(getEvents(7)).rejects.toThrow("Invalid events response");
});

it("propagates API failures for the loading error state", async () => {
  const error = new Error("Unavailable");
  vi.spyOn(api, "get").mockRejectedValue(error);
  await expect(getEvents(14)).rejects.toBe(error);
});
