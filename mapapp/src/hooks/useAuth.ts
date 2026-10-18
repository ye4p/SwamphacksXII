import { createContext, useContext } from "react";
import type { User } from "../lib/auth";
import type { FavoriteOrganization } from "../lib/favorites";
export type { User } from "../lib/auth";

export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  favorites: FavoriteOrganization[];
  favoritesLoading: boolean;
  favoritesError: string | null;
  login: () => void;
  logout: () => Promise<void>;
  refetch: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth must be used inside AuthProvider.");
  return auth;
}
