# Auth0 configuration

Set these in the deployed backend's environment, not in mapapp's Vite env:

```dotenv
AUTH0_DOMAIN=dev-0ay3cwkzlpv8r8di.us.auth0.com
AUTH0_CLIENT_ID=UojIOdEwQB3pqXPYGfA8JimKrrDLEb62
AUTH0_CALLBACK_URL=https://api.swamp-search.us/auth/auth0/callback
FRONTEND_URL=https://swamp-search.us
COOKIE_SECURE=true
AUTH0_TOKEN_ENDPOINT_AUTH_METHOD=client_secret_post
```

Match `AUTH0_TOKEN_ENDPOINT_AUTH_METHOD` to the application's **Token Endpoint
Authentication Method** in Auth0 Settings → Advanced Settings → OAuth:

| Auth0 setting | Backend environment value | Client secret |
| --- | --- | --- |
| Post | `client_secret_post` (default) | Required |
| Basic | `client_secret_basic` | Required |
| None (public PKCE application) | `none` | Not sent |

For Post or Basic, set `AUTH0_CLIENT_SECRET` to the secret from that exact Auth0
application in the backend environment. Do not commit it or put it in Vite.
Do not switch to None to work around incorrect confidential-client credentials.
The backend never retries failed exchanges using another method.

Register the callback URL above in Auth0 Allowed Callback URLs and the frontend
origin in Allowed Logout URLs. Enable the Authorization Code grant. Restart the
backend after updating its environment, and begin a new login rather than
reloading an old callback (codes are single use).

An `access_denied` / `Unauthorized` code-exchange rejection can still occur with
an incorrect client secret or a mismatch between these settings. The callback
response includes the configured `auth_method`; confirm it matches Auth0.
The backend cannot verify the secret locally or recover it from a client ID.

Run offline regression tests from this directory with dependencies installed:

```sh
python -m unittest test_auth -v
```
