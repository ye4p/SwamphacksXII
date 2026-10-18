import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { AuthContext } from "../../hooks/useAuth";
import { apiErrorMessage, apiUrl } from "../../lib/api";
import { endSession, getCurrentUser, type User } from "../../lib/auth";
import { getFavorites, type FavoriteOrganization } from "../../lib/favorites";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const request = useRef(0);
  const [favoritesState, setFavoritesState] = useState<{
    userId: number;
    favorites: FavoriteOrganization[];
    error: string | null;
  } | null>(null);
  const userId = user?.id;

  useEffect(() => {
    setFavoritesState(null);
    if (userId === undefined) return;

    const controller = new AbortController();
    getFavorites(controller.signal).then((favorites) => {
      if (!controller.signal.aborted) {
        setFavoritesState({ userId, favorites, error: null });
      }
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) {
        setFavoritesState({
          userId, favorites: [],
          error: apiErrorMessage(cause, "Unable to load favorites."),
        });
      }
    });
    return () => controller.abort();
  }, [userId]);

  // Never expose a previous account's data while a new request is starting.
  const currentFavorites = favoritesState?.userId === userId ? favoritesState : null;

  const refetch = useCallback(async () => {
    const current = ++request.current;
    setIsLoading(true);
    setError(null);
    try {
      const account = await getCurrentUser();
      if (current === request.current) setUser(account);
    } catch (cause) {
      if (current === request.current) {
        setUser(null);
        setError(apiErrorMessage(cause, "Unable to load account. Please retry."));
      }
    } finally {
      if (current === request.current) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refetch();
    return () => { ++request.current; };
  }, [refetch]);

  const login = useCallback(() => {
    // FastAPI owns PKCE, the callback, and the HttpOnly application cookie.
    // Its callback returns to FRONTEND_URL; redirect_to on login is ignored.
    window.location.assign(apiUrl("/auth/auth0/login"));
  }, []);

  const logout = useCallback(async () => {
    ++request.current; // A pending /me response must not restore a logged-out user.
    setIsLoading(true);
    setError(null);
    try {
      await endSession();
      setUser(null);
      // Clear the application session first, then end the Auth0 SSO session.
      if (user?.auth0_id) window.location.assign(apiUrl("/auth/auth0/logout"));
    } catch (cause) {
      const message = apiErrorMessage(cause, "Unable to log out. Please try again.");
      setError(message);
      throw new Error(message);
    } finally {
      setIsLoading(false);
    }
  }, [user]);

  return <AuthContext.Provider value={{
    user, isAuthenticated: user !== null, isLoading, error, login, logout, refetch,
    favorites: currentFavorites?.favorites ?? [],
    favoritesLoading: user !== null && currentFavorites === null,
    favoritesError: currentFavorites?.error ?? null,
  }}>
    {children}
  </AuthContext.Provider>;
}
