import type { Event } from "../types";

const events: Event[] = [
  { id: 1, organization_id: 1, timestamp: "2026-10-17T18:00:00Z", title: "Gator Hackers Meetup", description: "Weekly programming club meetup. Bring your laptop.", address: "Reitz Union, Room 3301, Gainesville, FL", longitude: -82.3549, latitude: 29.6436, payload: { notes: "", tags: ["programming", "educational", "food"] } },
  { id: 2, organization_id: 1, timestamp: "2026-10-18T07:00:00Z", title: "Morning Run Club", description: "3-mile run around campus. All paces welcome.", address: "Century Tower, University of Florida, Gainesville, FL", longitude: -82.3436, latitude: 29.6480, payload: { notes: "", tags: ["sports", "run club"] } },
  { id: 3, organization_id: 1, timestamp: "2026-10-19T16:00:00Z", title: "AI Study Group", description: "Discuss recent ML papers. Snacks provided.", address: "CSE Building, Room 202, Gainesville, FL", longitude: -82.3480, latitude: 29.6410, payload: { notes: "", tags: ["programming", "educational", "ai", "food"] } },
  { id: 4, organization_id: 1, timestamp: "2026-10-20T17:30:00Z", title: "UF Soccer Pick-up", description: "Pick-up soccer at the rec fields.", address: "RecFields, Southwest Recreation Center, Gainesville, FL", longitude: -82.3600, latitude: 29.6395, payload: { notes: "", tags: ["sports"] } },
];

export default events;
