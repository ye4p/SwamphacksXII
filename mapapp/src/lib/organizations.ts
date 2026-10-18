import { api } from "./api";
export interface Organization { id: number; name: string; description: string | null }
export async function getOrganizations(signal?: AbortSignal): Promise<Organization[]> {
  const { data } = await api.get<{ organizations: Organization[] }>("/api/getOrganizations", { signal });
  if (!Array.isArray(data?.organizations)) throw new Error("Invalid organizations response.");
  return data.organizations;
}
