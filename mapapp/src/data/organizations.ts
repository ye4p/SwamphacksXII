export interface Organization {
  id: number;
  name: string;
  gatorConnectUrl: string;
  category: string;
  interests: string[];
  description: string;
  icon: string;
  beginnerFriendly: boolean;
  events: { title: string; timestamp: string; kind: string; location: string; note: string }[];
}

const organizations: Organization[] = [
  {
    id: 1,
    name: "C++ Club",
    gatorConnectUrl: "https://gatorconnect.ufl.edu/organization/cppclub",
    category: "Technology",
    interests: ["Programming"],
    description: "Code, learn, and solve problems with fellow campus developers. All experience levels welcome to join coding projects.",
    icon: "C++",
    beginnerFriendly: true,
    events: [
      { title: "Modern C++: from basics to better code", timestamp: "2026-10-20T18:00:00", kind: "Workshop", location: "Engineering Hall · Room 210", note: "Beginner friendly" },
      { title: "Algorithms & pizza", timestamp: "2026-10-27T18:00:00", kind: "Meetup", location: "Engineering Hall · Room 210", note: "Food provided" },
    ],
  },
  {
    id: 2,
    name: "SwampHacks",
    gatorConnectUrl: "https://gatorconnect.ufl.edu/",
    category: "Technology",
    interests: ["Hackathons", "Programming"],
    description: "Build something new with a community of makers and big thinkers. Find a team and bring your coding ideas to life.",
    icon: "</>",
    beginnerFriendly: true,
    events: [
      { title: "Build night: campus edition", timestamp: "2026-10-17T18:30:00", kind: "Social", location: "Student Union · Innovation Lab", note: "Bring your laptop" },
      { title: "Hack night: find your team", timestamp: "2026-10-22T18:30:00", kind: "Social", location: "Student Union · Innovation Lab", note: "All majors welcome" },
    ],
  },
  {
    id: 3,
    name: "UF Open Source Club",
    gatorConnectUrl: "https://gatorconnect.ufl.edu/",
    category: "Technology",
    interests: ["Programming"],
    description: "Make your first contribution, build useful tools, and explore open-source coding with other Gators.",
    icon: "{ }",
    beginnerFriendly: true,
    events: [
      { title: "Your first open-source contribution", timestamp: "2026-10-21T17:30:00", kind: "Workshop", location: "CSE Building · Room 202", note: "Beginner friendly" },
      { title: "Code, coffee, and community", timestamp: "2026-10-23T16:00:00", kind: "Social", location: "The Hub", note: "Community & mentorship" },
      { title: "Open-source project showcase", timestamp: "2026-10-26T18:00:00", kind: "Showcase", location: "Library · Maker Space", note: "Bring your laptop" },
    ],
  },
  {
    id: 4,
    name: "Women in Computer Science",
    gatorConnectUrl: "https://gatorconnect.ufl.edu/",
    category: "Technology",
    interests: ["Programming", "Career"],
    description: "A supportive community for women in computing, with coding workshops, mentorship, and career connections.",
    icon: "WICS",
    beginnerFriendly: true,
    events: [
      { title: "Coding and coffee: community meetup", timestamp: "2026-10-23T16:00:00", kind: "Meetup", location: "The Hub", note: "Community & mentorship" },
      { title: "Portfolio and interview workshop", timestamp: "2026-10-27T17:00:00", kind: "Workshop", location: "Career Connections Center", note: "Career development" },
    ],
  },
  {
    id: 5,
    name: "UF AI Society",
    gatorConnectUrl: "https://gatorconnect.ufl.edu/",
    category: "Technology",
    interests: ["Artificial intelligence", "Programming"],
    description: "Explore machine learning through hands-on coding projects, practical workshops, and conversations about AI.",
    icon: "AI",
    beginnerFriendly: false,
    events: [
      { title: "Build your first machine learning model", timestamp: "2026-10-26T18:00:00", kind: "Workshop", location: "CSE Building · Room 202", note: "Projects & workshops" },
    ],
  },
  {
    id: 6,
    name: "UF InfoSec Team",
    gatorConnectUrl: "https://gatorconnect.ufl.edu/",
    category: "Technology",
    interests: ["Cybersecurity", "Programming"],
    description: "Learn secure coding, tackle capture-the-flag challenges, and sharpen your security skills with a team.",
    icon: ">_",
    beginnerFriendly: true,
    events: [
      { title: "Capture the flag: getting started", timestamp: "2026-10-28T18:30:00", kind: "Workshop", location: "CSE Building · Room 202", note: "Beginner friendly" },
      { title: "Secure coding workshop", timestamp: "2026-10-30T17:30:00", kind: "Workshop", location: "CSE Building · Room 202", note: "Bring your laptop" },
    ],
  },
];

export default organizations;
