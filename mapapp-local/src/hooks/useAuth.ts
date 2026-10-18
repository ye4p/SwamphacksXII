import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";

export type User = {
  id: number;
  email: string;
  name?: string | null;
  picture?: string | null;
  system_role?: string | null;
  auth0_id?: string | null;
};

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: () => void;
  logout: () => Promise<void>;
  refetch: () => Promise<void>;
}

export function useAuth(): AuthState {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMe = useCallback(async () => {
    setError(null);
    try {
      const res = await api.get("/auth/me");
      setUser(res.data.user);
    } catch (cause: any) {
      setUser(null);
      setError(cause?.response?.data?.detail || "Unable to load account.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  const login = useCallback(() => {
    const redirectTo = encodeURIComponent(window.location.origin);
    window.location.href = `${import.meta.env.VITE_API_BASE}/auth/auth0/login?redirect_to=${redirectTo}`;
  }, []);

  const logout = useCallback(async () => {
    setError(null);
    try {
      await api.post("/auth/logout");
    } catch (cause: any) {
      setError(cause?.response?.data?.detail || "Unable to log out.");
    } finally {
      setUser(null);
      setIsLoading(false);
    }
  }, []);

  return { user, isAuthenticated: !!user, isLoading, error, login, logout, refetch: fetchMe };
}
