# Auth0 configuration

Set these in the deployed backend's environment, not in mapapp's Vite env:


Match `AUTH0_TOKEN_ENDPOINT_AUTH_METHOD` to the application's **Token Endpoint
Authentication Method** under Auth0 Applications → My App → Credentials → Authentication Methods:

| Auth0 setting | Backend environment value | Client secret |
| --- | --- | --- |
| Post | `client_secret_post` (default) | Required |
| Basic | `client_secret_basic` | Required |
| None (public PKCE application) | `none` | Not sent |

For a Single Page Application using None, Auth0 may hide the Credentials tab.
Check the Application Type on the Settings tab; do not infer the method from
a missing tab alone.

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

To isolate token endpoint rejection from the browser, database, and callback
handler, run this with the backend's Python environment:

```sh
python backend/diagnose_auth0.py
```

The diagnostic loads dotenv using the same discovery and environment precedence
as the backend. It prints the selected file and names of existing environment
overrides, never the secret. It sends three requests to the configured tenant:
JSON and form requests with configured credentials, and a JSON control with a
deliberately wrong secret (the control is skipped for `none`). All use invalid
codes, so failed-exchange entries in Auth0 are expected. It does not change
application settings or create sessions. `invalid_grant` with the configured
credentials but `access_denied`/`invalid_client` with the control suggests client
authentication passed; identical failures do not establish the precise cause.
This diagnostic cannot verify a real authorization code or PKCE exchange.

Run offline regression tests from this directory with dependencies installed:

```sh
python -m unittest test_auth -v
```
