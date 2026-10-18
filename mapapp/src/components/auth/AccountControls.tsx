import { useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import { Avatar, AvatarFallback, AvatarImage } from "../ui/Avatar";

export default function AccountControls() {
  const { isLoading, isAuthenticated, error, login, logout, user, refetch } = useAuth();
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function authenticate(action: "login" | "logout") {
    setPending(true);
    setActionError(null);
    try {
      if (action === "logout") {
        await logout();
      } else {
        login();
      }
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Unable to connect. Please try again.");
    } finally {
      setPending(false);
    }
  }

  const initials = (user?.name ?? user?.email ?? "U").charAt(0).toUpperCase();

  return (
    <div className="account-controls">
      <nav className="auth-actions" aria-label="Account" aria-busy={isLoading || pending}>
        {isLoading ? <span className="account-status" role="status">Loading account…</span> : isAuthenticated ? <>
            <span className="account-profile" title={user?.email ?? user?.name ?? undefined}>
            <Avatar className="account-avatar">
              {user?.picture ? <AvatarImage src={user.picture} alt={user?.name ?? user?.email ?? "User avatar"} /> : null}
              <AvatarFallback>{initials}</AvatarFallback>
            </Avatar>
            <span className="account-identity"><strong>{user?.name ?? "Your account"}</strong>{user?.email && <small>{user.email}</small>}</span>
          </span>
          <button type="button" className="outline-button" disabled={pending} onClick={() => void authenticate("logout")}>Log out</button>
        </> : <>
          <button type="button" className="text-button" disabled={pending} onClick={() => void authenticate("login")}>Log in / Sign up</button>
        </>}
      </nav>
      {(actionError || error) && <p className="account-error" role="alert">{actionError ?? error} {error && <button type="button" className="text-button" disabled={pending || isLoading} onClick={() => { setActionError(null); void refetch(); }}>Retry</button>}</p>}
    </div>
  );
}
