"""Probe token exchange without a browser, real code, or database.

Run with the backend's Python environment: python diagnose_auth0.py
Only sends credentials to the configured HTTPS Auth0 tenant. Prints no secrets,
tokens, or raw upstream descriptions. Failed-exchange logs are expected.
"""
import os
import secrets
from pathlib import Path

import httpx
from dotenv import find_dotenv, load_dotenv


def main():
    env_file = find_dotenv()
    keys = ("AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET",
            "AUTH0_TOKEN_ENDPOINT_AUTH_METHOD", "AUTH0_CALLBACK_URL")
    overrides = [key for key in keys if key in os.environ]
    load_dotenv(env_file)
    domain = os.getenv("AUTH0_DOMAIN", "")
    client_id = os.getenv("AUTH0_CLIENT_ID", "")
    secret = os.getenv("AUTH0_CLIENT_SECRET", "")
    method = os.getenv("AUTH0_TOKEN_ENDPOINT_AUTH_METHOD", "client_secret_post").strip().lower()
    callback = os.getenv("AUTH0_CALLBACK_URL", "http://localhost:8000/auth/auth0/callback")
    print("Dotenv file:", str(Path(env_file).resolve()) if env_file else "none found")
    print("Existing process variables taking precedence:", ", ".join(overrides) or "none")
    print("Domain:", domain)
    print("Client ID:", client_id)
    print("Method:", method)
    print("Callback:", callback)
    print("Secret present:", bool(secret))
    if not domain or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for c in domain):
        raise SystemExit("AUTH0_DOMAIN must be a hostname, without https:// or a path.")
    if not client_id or method not in {"client_secret_post", "client_secret_basic", "none"}:
        raise SystemExit("Missing client ID or unsupported authentication method.")
    if method != "none" and not secret:
        raise SystemExit("Missing client secret.")

    def probe(client, label, credential, encoding):
        payload = {
            "grant_type": "authorization_code", "client_id": client_id,
            "redirect_uri": callback, "code": "diagnostic-invalid-" + secrets.token_urlsafe(32),
            "code_verifier": secrets.token_urlsafe(48),
        }
        options = {}
        if method == "client_secret_post":
            payload["client_secret"] = credential
        elif method == "client_secret_basic":
            options["auth"] = httpx.BasicAuth(client_id, credential)
        try:
            response = client.post(f"https://{domain}/oauth/token", **{encoding: payload}, **options)
        except httpx.RequestError as exc:
            print(label + ": network failure (" + type(exc).__name__ + ")")
            return
        try:
            body = response.json()
            error = body.get("error") if isinstance(body, dict) else None
        except ValueError:
            error = None
        known = ("access_denied", "invalid_client", "invalid_grant", "unauthorized_client", "invalid_request")
        safe_error = error if error in known else "other/unknown (raw response suppressed)"
        print(f"{label}: HTTP {response.status_code}, error={safe_error}")

    print("Sending deliberately invalid codes; no successful login is expected.")
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        probe(client, "Configured credentials, JSON (backend format)", secret, "json")
        probe(client, "Configured credentials, form", secret, "data")
        if method != "none":
            probe(client, "Deliberately wrong secret, JSON (control)", secrets.token_urlsafe(48), "json")
    print("invalid_grant with configured credentials but access_denied/invalid_client with the control")
    print("suggests client authentication passed. This does not validate a real login or PKCE exchange.")
    print("Identical failures are inconclusive; compare with the tenant's Failed Exchange logs.")


if __name__ == "__main__":
    main()
