import axios from "axios";
import { api } from "./api";

export type User = {
  id: number;
  email: string;
  name?: string | null;
  picture?: string | null;
  system_role?: string | null;
  auth0_id?: string | null;
};

export async function getCurrentUser(): Promise<User | null> {
  try {
    // Avoid the scaffold's unrelated /api/auth/* DeepSpace endpoints.
    const { data } = await api.get<User>("/auth/me");
    if (typeof data?.id !== "number" || typeof data?.email !== "string") {
      throw new Error("The backend returned an invalid account response.");
    }
    return data;
  } catch (cause) {
    // An anonymous or expired session is normal, not an account error.
    if (axios.isAxiosError(cause) && cause.response?.status === 401) return null;
    throw cause;
  }
}

export async function endSession(): Promise<void> {
  await api.post("/auth/logout");
}
