import { useAuth0 } from "@auth0/auth0-react";
import { useState } from "react";

export default function AccountControls() {
  const { isLoading, isAuthenticated, error, loginWithRedirect, logout, user } = useAuth0();
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function authenticate(action: "login" | "signup" | "logout") {
    setPending(true);
    setActionError(null);
    try {
      if (action === "logout") {
        await logout({ logoutParams: { returnTo: window.location.origin } });
      } else {
        await loginWithRedirect({
          authorizationParams: action === "signup" ? { screen_hint: "signup" } : undefined,
        });
      }
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Unable to connect. Please try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="account-controls">
      <nav className="auth-actions" aria-label="Account" aria-busy={isLoading || pending}>
        {isLoading ? <span className="account-status" role="status">Loading account…</span> : isAuthenticated ? <>
          <span className="account-profile" title={user?.email ?? user?.name}>
            <span className="account-avatar" aria-hidden="true">{(user?.name ?? user?.email ?? "U").charAt(0).toUpperCase()}</span>
            <span className="account-identity"><strong>{user?.name ?? "Your account"}</strong>{user?.email && <small>{user.email}</small>}</span>
          </span>
          <button type="button" className="outline-button" disabled={pending} onClick={() => void authenticate("logout")}>Log out</button>
        </> : <>
          <button type="button" className="text-button" disabled={pending} onClick={() => void authenticate("login")}>Log in</button>
          <button type="button" className="outline-button" disabled={pending} onClick={() => void authenticate("signup")}>Sign up</button>
        </>}
      </nav>
      {(actionError || error) && <p className="account-error" role="alert">{actionError ?? error?.message}</p>}
    </div>
  );
}
