import { api } from "./api";

export interface FavoriteOrganization {
  id: number;
  name: string;
  description: string | null;
  metadata: Record<string, unknown> | null;
  updated_at: string | null;
  role: "member" | "officer" | "president";
  joined_at: string | null;
}

export async function getFavorites(signal?: AbortSignal): Promise<FavoriteOrganization[]> {
  const { data } = await api.get<{ organizations: FavoriteOrganization[] }>(
    "/api/fetchFavorites", { signal },
  );
  if (!Array.isArray(data?.organizations)) {
    throw new Error("The backend returned an invalid favorites response.");
  }
  return data.organizations;
}

export async function setFavorite(id: number, favorite: boolean): Promise<FavoriteOrganization[]> {
  const { data } = await api.request<{ organizations: FavoriteOrganization[] }>({
    url: `/api/favorites/${id}`, method: favorite ? "POST" : "DELETE",
  });
  if (!Array.isArray(data?.organizations)) throw new Error("Invalid favorites response.");
  return data.organizations;
}
