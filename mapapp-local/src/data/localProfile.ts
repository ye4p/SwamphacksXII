export interface LocalProfile {
  name: string;
  email: string;
  major: string;
  classYear: string;
  interests: string[];
}

export const PROFILE_STORAGE_KEY = "swampsearch-local-profile";
export const FAVORITES_STORAGE_KEY = "swampsearch-favorite-organizations";
export const PROFILE_UPDATED_EVENT = "swampsearch-local-profile-updated";

export const DEFAULT_PROFILE: LocalProfile = {
  name: "John Doe",
  email: "johndoe@ufl.edu",
  major: "Computer Science",
  classYear: "Class of 2028",
  interests: ["Programming"],
};

export const DEFAULT_FAVORITE_IDS = [1, 2];

export function loadLocalProfile(): LocalProfile {
  const saved = localStorage.getItem(PROFILE_STORAGE_KEY);
  if (!saved) return DEFAULT_PROFILE;

  try {
    const parsed: unknown = JSON.parse(saved);
    if (typeof parsed === "object" && parsed !== null
      && "name" in parsed && typeof parsed.name === "string"
      && (("email" in parsed && typeof parsed.email === "string")
        || ("handle" in parsed && typeof parsed.handle === "string"))
      && "major" in parsed && typeof parsed.major === "string"
      && "classYear" in parsed && typeof parsed.classYear === "string"
      && "interests" in parsed && Array.isArray(parsed.interests)
      && parsed.interests.every((interest) => typeof interest === "string")) {
      const legacyHandle = "handle" in parsed && typeof parsed.handle === "string"
        ? parsed.handle
        : "johndoe";
      return {
        name: parsed.name,
        email: "email" in parsed && typeof parsed.email === "string"
          ? parsed.email
          : `${legacyHandle.replace(/@?ufl\.edu$/i, "")}@ufl.edu`,
        major: parsed.major,
        classYear: parsed.classYear,
        interests: parsed.interests,
      };
    }
  } catch {
    return DEFAULT_PROFILE;
  }

  return DEFAULT_PROFILE;
}

export function loadFavoriteIds(): number[] {
  const saved = localStorage.getItem(FAVORITES_STORAGE_KEY);
  if (!saved) return DEFAULT_FAVORITE_IDS;

  try {
    const parsed: unknown = JSON.parse(saved);
    if (Array.isArray(parsed) && parsed.every((id) => Number.isInteger(id))) {
      return parsed;
    }
  } catch {
    return DEFAULT_FAVORITE_IDS;
  }

  return DEFAULT_FAVORITE_IDS;
}
