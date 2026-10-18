import axios from "axios";

// Empty means a same-origin reverse proxy. Development defaults to FastAPI.
export const API_BASE = (import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? "http://localhost:8000" : "")).trim().replace(/\/+$/, "");

export function apiUrl(path: string): string {
  return `${API_BASE}/${path.replace(/^\/+/, "")}`;
}

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
  timeout: 15000,
});

export function apiErrorMessage(cause: unknown, fallback: string): string {
  if (axios.isAxiosError(cause) && typeof cause.response?.data?.detail === "string") {
    return cause.response.data.detail;
  }
  return fallback;
}
