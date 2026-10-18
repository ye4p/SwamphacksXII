# Backend authentication

The map entry point (`src/main.tsx`) uses `AuthProvider` and the FastAPI session,
not the Auth0 SPA SDK or the unused DeepSpace scaffold page authentication.
Never send Auth0 access tokens as API bearer tokens: this backend accepts its
own HS256 application token, normally supplied by its HttpOnly session cookie.

Set `VITE_API_BASE` to the FastAPI origin (no `/api` suffix). It defaults to
`http://localhost:8000` in development; production requires an explicit backend
origin or a same-origin proxy for backend routes. Vite settings are build-time
settings, so restart/rebuild after changing them.

Login/signup navigates to `/auth/auth0/login`. The backend handles PKCE and the
Auth0 callback, then returns to its configured `FRONTEND_URL`. Signup is offered
by Auth0 Universal Login when enabled for the connection. The backend does not
forward `screen_hint` or retain the login route's `redirect_to` parameter.
On return, `/auth/me` restores the account. A 401 means signed out. Logout posts
to `/auth/logout` first; Auth0 accounts then visit `/auth/auth0/logout` to end SSO.

Backend/Auth0 configuration must match the actual deployment:

- `FRONTEND_URL` is the map's origin; include it in backend `CORS_ORIGINS`.
- Auth0 Allowed Callback URLs includes the backend `AUTH0_CALLBACK_URL`
  (for example `http://localhost:8000/auth/auth0/callback`).
- Auth0 Allowed Logout URLs includes `FRONTEND_URL`.
- Use HTTPS and secure cookies in production. SameSite=Lax cookies work across
  same-site hosts such as `swamp-search.us` and `api.swamp-search.us`. Unrelated
  frontend/backend sites need appropriate cross-site cookie configuration and
  are subject to browser third-party-cookie restrictions.
- For local development, use `localhost` for both services, with separate ports.

## Existing backend blockers (not changed)

In `backend/app.py`, `/auth/auth0/login`, `/auth/auth0/callback`,
`/auth/auth0/logout`, `/auth/login`, and `/auth/register` mutate the injected
`Response` cookies but return a separate `RedirectResponse` or `JSONResponse`.
Those explicit returned responses do not carry the cookies from the injected
response. Consequently PKCE state/verifier cookies and the application session
cookie are lost. The backend must set/delete cookies on the response it actually
returns. A frontend cannot recover missing HttpOnly cookies or safely manufacture
the backend's signed session. `/auth/logout` returns a dict and does carry the
injected response's cookie deletion, which is why the client calls it first.

If `COOKIE_NAME` is customized, the backend reader still binds the literal
`session_token` cookie; keep the default until backend reading is aligned.

## Verification

Run `npm run validate`, `npm run lint`, and `npm run build` in `mapapp`.
After the backend cookie fix, check in a browser: anonymous load has no account
error; login/signup returns to the map; reload restores the account; logout
removes the account and reload stays signed out. A failed account request should
show Retry, and a failed logout must not falsely show a successful sign-out.
