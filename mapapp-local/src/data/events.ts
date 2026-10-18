import type { Event } from "../types";
import organizations from "./organizations";

const organizationEvents: Event[] = organizations.flatMap((organization) =>
  organization.events.map((event, index) => {
    const coordinates = organization.id === 1
      ? { longitude: -82.348, latitude: 29.641 }
      : organization.id === 2
        ? { longitude: -82.3476, latitude: 29.6462 }
        : organization.id === 3
          ? { longitude: -82.348, latitude: 29.641 }
          : organization.id === 4
            ? { longitude: -82.3438, latitude: 29.6467 }
            : organization.id === 5 || organization.id === 6
              ? { longitude: -82.348, latitude: 29.641 }
              : { longitude: -82.3476, latitude: 29.6462 };

    return {
      id: 1000 + organization.id * 100 + index,
      organization_id: organization.id,
      timestamp: event.timestamp,
      title: event.title,
      description: `${event.note}. ${organization.description}`,
      address: `${event.location}, Gainesville, FL`,
      ...coordinates,
      payload: {
        notes: event.note,
        tags: [...new Set([
          ...organization.interests.map((interest) => interest.toLowerCase()),
          event.kind.toLowerCase(),
          ...(event.note.toLowerCase().includes("food") ? ["food"] : []),
        ])],
      },
    };
  }),
);

const events: Event[] = [
  { id: 1, organization_id: 1, timestamp: "2026-10-17T18:00:00Z", title: "Gator Hackers Meetup", description: "Weekly programming club meetup. Bring your laptop.", address: "Reitz Union, Room 3301, Gainesville, FL", longitude: -82.3549, latitude: 29.6436, payload: { notes: "", tags: ["programming", "educational", "food"] } },
  { id: 2, organization_id: 1, timestamp: "2026-10-18T07:00:00Z", title: "Morning Run Club", description: "3-mile run around campus. All paces welcome.", address: "Century Tower, University of Florida, Gainesville, FL", longitude: -82.3436, latitude: 29.6480, payload: { notes: "", tags: ["sports", "run club"] } },
  { id: 3, organization_id: 1, timestamp: "2026-10-19T16:00:00Z", title: "AI Study Group", description: "Discuss recent ML papers. Snacks provided.", address: "CSE Building, Room 202, Gainesville, FL", longitude: -82.3480, latitude: 29.6410, payload: { notes: "", tags: ["programming", "educational", "ai", "food"] } },
  { id: 4, organization_id: 1, timestamp: "2026-10-20T17:30:00Z", title: "UF Soccer Pick-up", description: "Pick-up soccer at the rec fields.", address: "RecFields, Southwest Recreation Center, Gainesville, FL", longitude: -82.3600, latitude: 29.6395, payload: { notes: "", tags: ["sports"] } },
  { id: 5, organization_id: 2, timestamp: "2026-10-17T22:00:00Z", title: "Build night: campus edition", description: "Bring an idea and spend the evening coding with other student builders.", address: "Reitz Union, Gainesville, FL", longitude: -82.3476, latitude: 29.6462, payload: { notes: "", tags: ["programming", "hackathon", "social"] } },
  { id: 6, organization_id: 2, timestamp: "2026-10-18T17:00:00Z", title: "Your first open-source contribution", description: "A friendly, hands-on workshop for finding a project and making your first coding contribution.", address: "CSE Building, Gainesville, FL", longitude: -82.3480, latitude: 29.6410, payload: { notes: "", tags: ["programming", "open source", "educational"] } },
  { id: 7, organization_id: 3, timestamp: "2026-10-19T19:00:00Z", title: "Tech careers coffee chat", description: "Meet local developers and talk about internships, portfolios, and getting started in coding.", address: "Innovation Hub, Gainesville, FL", longitude: -82.3442, latitude: 29.6486, payload: { notes: "", tags: ["career", "networking", "coding"] } },
  { id: 8, organization_id: 3, timestamp: "2026-10-20T21:30:00Z", title: "Modern C++ from the ground up", description: "Explore practical coding patterns, safer memory, and modern C++ tools.", address: "CSE Building, Gainesville, FL", longitude: -82.3480, latitude: 29.6410, payload: { notes: "", tags: ["programming", "coding", "educational"] } },
  { id: 9, organization_id: 2, timestamp: "2026-10-21T18:00:00Z", title: "Creative coding and generative art", description: "Make a small interactive artwork while learning the basics of creative coding.", address: "Fine Arts Building, Gainesville, FL", longitude: -82.3410, latitude: 29.6388, payload: { notes: "", tags: ["arts", "culture", "coding"] } },
  { id: 10, organization_id: 1, timestamp: "2026-10-22T16:00:00Z", title: "Code, coffee, and community", description: "A relaxed social meetup for anyone who enjoys coding, sharing projects, or learning together.", address: "The Hub, Gainesville, FL", longitude: -82.3438, latitude: 29.6467, payload: { notes: "", tags: ["programming", "food", "social"] } },
  ...organizationEvents,
];

export default events;
