import type { Event } from "../types";

const events: Event[] = [
  { id: 1, title: "Gator Hackers Meetup", address: "Reitz Union, Room 3301, Gainesville, FL", lat: 29.6436, lng: -82.3549, start_time: "2026-10-17T18:00:00-04:00", description: "Weekly programming club meetup. Bring your laptop.", tags: ["programming", "educational", "food"]},
  { id: 2, title: "Morning Run Club", address: "Century Tower, University of Florida, Gainesville, FL", lat: 29.6480, lng: -82.3436, start_time: "2026-10-18T07:00:00-04:00", description: "3-mile run around campus. All paces welcome.", tags: ["sports", "run club"]},
  { id: 3, title: "AI Study Group", address: "CSE Building, Room 202, Gainesville, FL", lat: 29.6410, lng: -82.3480, start_time: "2026-10-19T16:00:00-04:00", description: "Discuss recent ML papers. Snacks provided.", tags: ["programming", "educational", "ai", "food"]},
  { id: 4, title: "UF Soccer Pick-up", address: "RecFields, Southwest Recreation Center, Gainesville, FL", lat: 29.6395, lng: -82.3600, start_time: "2026-10-20T17:30:00-04:00", description: "Pick-up soccer at the rec fields.", tags: ["sports"]},
];

export default events;
