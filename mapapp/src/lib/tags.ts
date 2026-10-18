import { api } from "./api";

export async function getTags(): Promise<string[]> {
  const { data } = await api.get<{ tags?: unknown }>("/api/gettags");
  const tags = (data as { tags?: unknown })?.tags;
  if (!Array.isArray(tags) || !tags.every((tag) => typeof tag === "string")) {
    throw new Error("Invalid tags response.");
  }
  return [...new Set(tags.filter((tag) => tag.trim().length > 0))];
}

// Share the startup request, including React StrictMode's effect replay.
let tagsRequest: Promise<string[]> | undefined;
export function loadTags(): Promise<string[]> {
  return tagsRequest ??= getTags().catch((error: unknown) => {
    tagsRequest = undefined;
    throw error;
  });
}
