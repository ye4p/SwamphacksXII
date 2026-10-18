"""Callback regression tests; no database, Auth0 account, or network required.

Run from backend: python -m unittest test_auth
"""
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx

with patch.dict(os.environ, {"SECRET_KEY": "test-only-key", "PYTHON_DOTENV_DISABLED": "1"}):
    import app as backend


class AuthCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        config = patch.multiple(backend, AUTH0_DOMAIN="test.auth0.com", AUTH0_CLIENT_ID="test-client", AUTH0_CLIENT_SECRET="test-secret", AUTH0_TOKEN_ENDPOINT_AUTH_METHOD="client_secret_post")
        config.start()
        self.addCleanup(config.stop)
        # ASGITransport does not run the database lifespan.
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=backend.app), base_url="http://testserver")
        self.client.cookies.set("auth0_state", "test-state")
        self.client.cookies.set("auth0_code_verifier", "test-verifier")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def callback(self):
        return await self.client.get(
            "/auth/auth0/callback", params={"code": "test-code", "state": "test-state"},
            follow_redirects=False,
        )

    async def test_exchange_error_is_actionable_and_does_not_leak_raw_response(self):
        upstream = httpx.Response(401, json={
            "error": "invalid_client", "error_description": "sensitive-upstream-description",
        })
        exchange = AsyncMock()
        exchange.post.return_value = upstream
        with patch.object(backend.httpx, "AsyncClient") as factory, self.assertLogs(backend.logger, level="WARNING") as logs:
            factory.return_value.__aenter__.return_value = exchange
            response = await self.callback()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["auth0_error"], "invalid_client")
        self.assertEqual(response.json()["auth_method"], "client_secret_post")
        self.assertNotIn("sensitive-upstream-description", response.text + str(logs.output))
        self.assertNotIn("test-code", str(logs.output))
        cookies = response.headers.get_list("set-cookie")
        for name in ("auth0_state", "auth0_code_verifier", "auth0_redirect_to"):
            self.assertTrue(any(cookie.startswith(name + "=") and "Max-Age=0" in cookie for cookie in cookies))

    def test_unknown_and_non_json_errors_are_safe(self):
        for upstream in (httpx.Response(500, text="private upstream text"), httpx.Response(400, json={"error": ["unexpected"]})):
            with self.subTest(response=upstream), self.assertLogs(backend.logger, level="WARNING"):
                response = backend._auth0_exchange_failure(upstream)
                self.assertIn(b'"auth0_error":"unknown_error"', response.body)
                self.assertNotIn(b"private upstream text", response.body)

    async def test_missing_verifier_does_not_attempt_exchange(self):
        self.client.cookies.delete("auth0_code_verifier")
        with patch.object(backend.httpx, "AsyncClient") as factory:
            response = await self.callback()
        self.assertEqual(response.status_code, 400)
        self.assertIn("PKCE cookie", response.json()["detail"])
        factory.assert_not_called()

    async def test_mismatched_state_does_not_attempt_exchange(self):
        self.client.cookies.set("auth0_state", "wrong-state")
        with patch.object(backend.httpx, "AsyncClient") as factory:
            response = await self.callback()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Invalid Auth0 request state")
        factory.assert_not_called()

    def test_token_authentication_methods(self):
        for method in ("client_secret_post", "client_secret_basic", "none"):
            with self.subTest(method=method), patch.object(backend, "AUTH0_TOKEN_ENDPOINT_AUTH_METHOD", method):
                options = backend._auth0_token_request("test-code", "test-verifier")
                payload = options["json"]
                self.assertEqual(payload["code_verifier"], "test-verifier")
                self.assertEqual(payload["client_id"], "test-client")
                if method == "client_secret_post":
                    self.assertEqual(payload["client_secret"], "test-secret")
                    self.assertNotIn("auth", options)
                elif method == "client_secret_basic":
                    self.assertNotIn("client_secret", payload)
                    request = httpx.Request("POST", "https://test.auth0.com/oauth/token")
                    authenticated = next(options["auth"].auth_flow(request))
                    import base64
                    credentials = base64.b64decode(authenticated.headers["authorization"].split()[1]).decode()
                    self.assertEqual(credentials, "test-client:test-secret")
                else:
                    self.assertNotIn("client_secret", payload)
                    self.assertNotIn("auth", options)

    async def test_missing_secret_fails_before_redirecting_to_google(self):
        with patch.object(backend, "AUTH0_CLIENT_SECRET", None):
            response = await self.client.get("/auth/auth0/login", follow_redirects=False)
        self.assertEqual(response.status_code, 500)
        self.assertIn("AUTH0_CLIENT_SECRET", response.json()["detail"])
        self.assertNotIn("location", response.headers)

    def test_public_client_requires_explicit_configuration(self):
        with patch.object(backend, "AUTH0_CLIENT_SECRET", None):
            with self.assertRaises(backend.HTTPException):
                backend._auth0_token_request("test-code", "test-verifier")
            with patch.object(backend, "AUTH0_TOKEN_ENDPOINT_AUTH_METHOD", "none"):
                self.assertNotIn("client_secret", backend._auth0_token_request("test-code", "test-verifier")["json"])

    def test_unknown_auth_method_is_rejected(self):
        with patch.object(backend, "AUTH0_TOKEN_ENDPOINT_AUTH_METHOD", "typo"):
            with self.assertRaises(backend.HTTPException):
                backend._auth0_token_request("test-code", "test-verifier")


if __name__ == "__main__":
    unittest.main()
