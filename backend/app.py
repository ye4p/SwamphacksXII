"""Swamphacks backend — FastAPI application.

Authentication
--------------
* Auth0 (OpenID Connect Authorization Code flow with PKCE)
* Regular email + password logins (bcrypt-hashed passwords)

Every data access goes through `core.tigerdata.TigerData`. Session state is a
signed JWT stored in an HttpOnly, SameSite=lax cookie (readable via the
`Authorization: Bearer <token>` header as well).

Required environment variables:
  CONNECTION          asyncpg PostgreSQL DSN (used by TigerData)
  SECRET_KEY          signing key for app session JWTs
  AUTH0_DOMAIN        e.g. example.us.auth0.com
  AUTH0_CLIENT_ID     Auth0 application client id
  AUTH0_CLIENT_SECRET Auth0 application client secret (Post/Basic methods)
  AUTH0_TOKEN_ENDPOINT_AUTH_METHOD client_secret_post (default),
                      client_secret_basic, or none; must match Auth0 settings
  AUTH0_CALLBACK_URL  redirect URL registered in Auth0, e.g.
                      https://api.example.com/auth/auth0/callback
  FRONTEND_URL        origin users are sent to after login/logout
  COOKIE_SECURE       "true" to mark session cookies Secure (required in prod)
  CORS_ORIGINS        comma-separated list of allowed CORS origins
"""

import base64
import hashlib
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional
from urllib.parse import quote, urlencode, urlparse

from dotenv import load_dotenv
from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import bcrypt

load_dotenv()

logger = logging.getLogger(__name__)

from core.tigerdata import TigerData

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN")
AUTH0_CLIENT_ID = os.getenv("AUTH0_CLIENT_ID")
AUTH0_CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET")
AUTH0_TOKEN_ENDPOINT_AUTH_METHOD = os.getenv(
    "AUTH0_TOKEN_ENDPOINT_AUTH_METHOD", "client_secret_post"
).strip().lower()
AUTH0_CALLBACK_URL = os.getenv(
    "AUTH0_CALLBACK_URL", "http://localhost:8000/auth/auth0/callback"
)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

COOKIE_NAME = os.getenv("COOKIE_NAME", "session_token")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")
_CORS_DEFAULT = f"{FRONTEND_URL},http://localhost:3000,http://localhost:5173"
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", _CORS_DEFAULT).split(",") if o.strip()]

ISSUER = f"https://{AUTH0_DOMAIN}/" if AUTH0_DOMAIN else ""


def _validate_auth0_config() -> None:
    if not AUTH0_DOMAIN or not AUTH0_CLIENT_ID:
        raise HTTPException(500, "Auth0 domain and client ID must be configured on the backend")
    if AUTH0_TOKEN_ENDPOINT_AUTH_METHOD not in {"client_secret_post", "client_secret_basic", "none"}:
        raise HTTPException(500, "Invalid AUTH0_TOKEN_ENDPOINT_AUTH_METHOD configuration")
    if AUTH0_TOKEN_ENDPOINT_AUTH_METHOD != "none" and not AUTH0_CLIENT_SECRET:
        raise HTTPException(500, "AUTH0_CLIENT_SECRET is missing from the backend environment")


def _auth0_token_request(code: str, code_verifier: str) -> dict:
    _validate_auth0_config()
    payload = {
        "grant_type": "authorization_code",
        "client_id": AUTH0_CLIENT_ID,
        "code": code,
        "redirect_uri": AUTH0_CALLBACK_URL,
        "code_verifier": code_verifier,
    }
    options = {"json": payload}
    if AUTH0_TOKEN_ENDPOINT_AUTH_METHOD == "client_secret_post":
        payload["client_secret"] = AUTH0_CLIENT_SECRET
    elif AUTH0_TOKEN_ENDPOINT_AUTH_METHOD == "client_secret_basic":
        options["auth"] = httpx.BasicAuth(AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET)
    # Public PKCE clients explicitly use "none". Never downgrade or retry a
    # rejected confidential-client exchange without authentication.
    return options

# -----------------------------------------------------------------------------
# Security helpers
# -----------------------------------------------------------------------------

_jwks_cache: Dict[str, Dict[str, Any]] = {}

db = TigerData()


def _b64url_uint(data: str) -> int:
    padded = data + "=" * (-len(data) % 4)
    return int.from_bytes(base64.urlsafe_b64decode(padded), "big")


async def _get_signing_key_pem(kid: str) -> str:
    now = time.time()
    entry = _jwks_cache.get(kid)
    if entry and entry["expires_at"] > now:
        return entry["pem"]

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"https://{AUTH0_DOMAIN}/.well-known/jwks.json")
    resp.raise_for_status()
    jwks = resp.json()

    for key in jwks.get("keys", []):
        if key.get("kid") != kid or key.get("kty") != "RSA":
            continue
        n = _b64url_uint(key["n"])
        e = _b64url_uint(key["e"])
        public_key = rsa.RSAPublicNumbers(e, n).public_key()
        pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        _jwks_cache[kid] = {"pem": pem, "expires_at": now + 3600}
        return pem

    raise HTTPException(
        status.HTTP_502_BAD_GATEWAY, "Auth0 signing key not found"
    )


async def verify_auth0_id_token(id_token: str) -> Dict[str, Any]:
    try:
        unverified = jwt.get_unverified_header(id_token)
    except JWTError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Invalid Auth0 id_token"
        ) from exc

    kid = unverified.get("kid")
    if not kid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Auth0 id_token missing key id"
        )

    pem = await _get_signing_key_pem(kid)
    try:
        claims = jwt.decode(
            id_token,
            pem,
            algorithms=["RS256"],
            # ID tokens identify this application, not a custom API resource.
            audience=AUTH0_CLIENT_ID,
            issuer=ISSUER,
        )
    except JWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Auth0 id_token verification failed"
        ) from exc
    return claims


def create_app_token(user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# -----------------------------------------------------------------------------
# Cookie helpers
# -----------------------------------------------------------------------------
def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def _clear_auth0_cookies(response: Response) -> None:
    response.delete_cookie("auth0_state", path="/")
    response.delete_cookie("auth0_code_verifier", path="/")
    response.delete_cookie("auth0_redirect_to", path="/")


def _auth0_exchange_failure(token_response: httpx.Response) -> JSONResponse:
    # Never log the request payload, raw response, code, verifier, or secret.
    # Only expose known OAuth error identifiers and our own diagnostic text.
    messages = {
        "invalid_client": "Check the backend Auth0 client ID and secret, and ensure AUTH0_TOKEN_ENDPOINT_AUTH_METHOD matches the Auth0 application setting.",
        "unauthorized_client": "Check that the Auth0 application allows the Authorization Code grant and that AUTH0_TOKEN_ENDPOINT_AUTH_METHOD matches its setting.",
        "access_denied": "Check the backend Auth0 client credentials and the application's Token Endpoint Authentication Method (must match AUTH0_TOKEN_ENDPOINT_AUTH_METHOD).",
        "invalid_grant": "Start a fresh login. If this persists, check the callback URL and PKCE configuration; authorization codes expire and can only be used once.",
        "invalid_request": "Check the Auth0 callback URL and token exchange configuration.",
    }
    try:
        body = token_response.json()
        error = body.get("error") if isinstance(body, dict) else None
    except ValueError:
        error = None
    error = error if isinstance(error, str) and error in messages else "unknown_error"
    logger.warning("Auth0 token exchange rejected: status=%s error=%s", token_response.status_code, error)
    response = JSONResponse(
        {
            "detail": "Auth0 token exchange failed",
            "auth0_error": error,
            "auth_method": AUTH0_TOKEN_ENDPOINT_AUTH_METHOD,
            "hint": messages.get(error, "Check the Auth0 tenant logs for the failed code exchange."),
        },
        status_code=status.HTTP_400_BAD_REQUEST,
    )
    _clear_auth0_cookies(response)
    return response


# -----------------------------------------------------------------------------
# Pydantic models
# -----------------------------------------------------------------------------
class UserOut(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    system_role: Optional[str] = None
    auth0_id: Optional[str] = None


class EventIn(BaseModel):
    timestamp: str
    title: str
    longitude: float
    latitude: float
    organization_id: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None


# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.connect()
    await db.init_db()
    yield
    await db.close()


app = FastAPI(title="Swamphacks Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# Auth dependencies
# -----------------------------------------------------------------------------
async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    token: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    else:
        cookie_name = COOKIE_NAME
        session_token = request.cookies.get(cookie_name) if cookie_name else None
        if session_token:
            token = session_token

    if not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Not authenticated"
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, ValueError, KeyError) as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid or expired token"
        ) from exc

    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "User not found"
        )
    return user


def require_role(*allowed_roles: str):
    async def role_checker(
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        if current_user.get("system_role") not in allowed_roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Insufficient permissions"
            )
        return current_user

    return role_checker


def user_public(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user.get("name"),
        "picture": user.get("picture"),
        "system_role": user.get("system_role"),
        "auth0_id": user.get("auth0_id"),
    }


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    name: Optional[str] = Form(None),
) -> JSONResponse:
    if len(password) < 8:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Password must be at least 8 characters",
        )

    email = email.strip().lower()
    salt = bcrypt.gensalt(rounds=12)
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    from asyncpg.exceptions import UniqueViolationError

    try:
        user_id = await db.create_local_user(
            email, password_hash, "user", {"name": name} if name else {}
        )
    except UniqueViolationError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Email already registered"
        )

    token = create_app_token(user_id, email)
    user = await db.get_user(user_id)
    _set_session_cookie(response, token)
    return JSONResponse({"user": user_public(user), "message": "Registered"})


@app.post("/auth/login")
async def login(
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
) -> JSONResponse:
    email = email.strip().lower()
    user = await db.get_user_by_email(email)

    if (
        not user
        or not user.get("password_hash")
        or not bcrypt.checkpw(password.encode('utf-8'), user["password_hash"].encode('utf-8'))
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid email or password"
        )

    token = create_app_token(user["id"], email)
    _set_session_cookie(response, token)
    return JSONResponse({"user": user_public(user)})


@app.get("/auth/auth0/login")
async def auth0_login(
    request: Request,
    response: Response,
    redirect_to: Optional[str] = Query(None),
) -> RedirectResponse:
    _validate_auth0_config()

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    params = {
        "response_type": "code",
        "client_id": AUTH0_CLIENT_ID,
        "redirect_uri": AUTH0_CALLBACK_URL,
        "scope": "openid profile email",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    # This flow only needs an ID token. Requesting a custom API audience can
    # reject login when that resource is not registered in Auth0.

    authorize_url = f"https://{AUTH0_DOMAIN}/authorize?{urlencode(params)}"
    redirect = RedirectResponse(authorize_url)
    redirect.set_cookie(
        "auth0_state",
        state,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
        max_age=600,
    )
    redirect.set_cookie(
        "auth0_code_verifier",
        code_verifier,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
        max_age=600,
    )
    if redirect_to:
        redirect.set_cookie(
            "auth0_redirect_to",
            redirect_to,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
            path="/",
            max_age=600,
        )
    return redirect


@app.get("/auth/auth0/callback")
async def auth0_callback(
    request: Request,
    response: Response,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    redirect_to: Optional[str] = Query(None),
) -> Response:
    expected_state = request.cookies.get("auth0_state")
    code_verifier = request.cookies.get("auth0_code_verifier")

    if not code or not state or not expected_state or state != expected_state:
        redirect = RedirectResponse(FRONTEND_URL)
        _clear_auth0_cookies(redirect)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Invalid Auth0 request state"
        )

    if not code_verifier:
        failure = JSONResponse(
            {"detail": "Auth0 PKCE cookie is missing or expired. Start a fresh login."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
        _clear_auth0_cookies(failure)
        return failure

    token_options = _auth0_token_request(code, code_verifier)

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_resp = await client.post(
            f"https://{AUTH0_DOMAIN}/oauth/token", **token_options
        )

    if token_resp.status_code >= 400:
        return _auth0_exchange_failure(token_resp)

    tokens = token_resp.json()
    id_token = tokens.get("id_token")
    if not id_token:
        redirect = RedirectResponse(FRONTEND_URL)
        _clear_auth0_cookies(redirect)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Auth0 did not return an id_token"
        )

    claims = await verify_auth0_id_token(id_token)
    auth0_id = claims["sub"]
    email = (claims.get("email") or "").strip().lower()
    name = claims.get("name")
    picture = claims.get("picture")

    user_id = await db.upsert_auth0_user(auth0_id, email, name, picture)
    app_token = create_app_token(user_id, email)

    cookie_redirect = request.cookies.get("auth0_redirect_to")
    target = redirect_to or cookie_redirect or FRONTEND_URL
    if target and not (target.startswith("/") or target.startswith("http://") or target.startswith("https://")):
        target = FRONTEND_URL
    if target and (target.startswith("http://") or target.startswith("https://")):
        parsed = urlparse(target)
        fparsed = urlparse(FRONTEND_URL)
        if parsed.scheme != fparsed.scheme or parsed.netloc != fparsed.netloc:
            target = FRONTEND_URL
    if not target:
        target = FRONTEND_URL

    redirect = RedirectResponse(target)
    _set_session_cookie(redirect, app_token)
    _clear_auth0_cookies(redirect)
    return redirect


@app.get("/auth/auth0/logout")
async def auth0_logout(
    response: Response,
    redirect_to: Optional[str] = Query(None),
) -> RedirectResponse:
    target = redirect_to or FRONTEND_URL
    if target and (target.startswith("http://") or target.startswith("https://")):
        parsed = urlparse(target)
        fparsed = urlparse(FRONTEND_URL)
        if parsed.scheme != fparsed.scheme or parsed.netloc != fparsed.netloc:
            target = FRONTEND_URL
    if not target:
        target = FRONTEND_URL
    logout_url = (
        f"https://{AUTH0_DOMAIN}/v2/logout?"
        f"client_id={AUTH0_CLIENT_ID}&returnTo={quote(target)}"
    )
    redirect = RedirectResponse(logout_url)
    _clear_session_cookie(redirect)
    return redirect


@app.post("/auth/logout")
async def logout(response: Response) -> Dict[str, str]:
    _clear_session_cookie(response)
    return {"message": "Logged out"}


@app.get("/auth/me")
async def read_me(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return user_public(current_user)


@app.get("/api/auth/me")
async def read_me_api(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return user_public(current_user)


# -----------------------------------------------------------------------------
# Example protected resources using TigerData
# -----------------------------------------------------------------------------

@app.get("/admin/members")
async def admin_members(
    current_user: Dict[str, Any] = Depends(require_role("mod", "admin")),
) -> Dict[str, Any]:
    return {"message": "admin area", "user": user_public(current_user)}

@app.get("/api/dangerous")
async def dangerous():
    """TEMPORARY DEV-ONLY: wipe the database and seed a default admin user,
    one sample organization, and a few sample events around 2026-10-17."""
    await db.wipe_database()

    # Default admin user (email/password login)
    salt = bcrypt.gensalt(rounds=12) 
    admin_password_hash = bcrypt.hashpw(("admin123").encode('utf-8'), salt).decode('utf-8')
    admin_id = await db.create_local_user(
        "admin@swamphacks.com",
        admin_password_hash,
        "admin",
        {"name": "Default Admin"},
    )

    # Sample organization
    org_id = await db.upsert_organization(
        "Swamphacks Organizing Committee",
        "Main student organizing body for Swamphacks XII",
        {"type": "student_org", "room": "CSE 201"},
    )
    await db.assign_membership(admin_id, org_id, "president")

    # Sample events around 2026-10-17 (today)
    sample_events = [
        ("2026-10-17 10:00:00+00", "Opening Ceremony", "Opening ceremony description wow nice", "test lane 1", -82.3536, 29.6516, {"notes": "Main auditorium", "tags": ["event"]}),
        ("2026-10-17 14:00:00+00", "Kickoff Hackathon", "kickoff hackaton description wow nice", "test lane 2", -82.3540, 29.6520, {"notes": "Bring laptops", "tags": ["event"]}),
        ("2026-10-18 09:00:00+00", "Workshop: Intro to FastAPI", "workshop description wow nice", "test lane 3", -82.3530, 29.6510, {"notes": "Room 101", "tags": ["event"]}),
        ("2026-10-19 16:00:00+00", "Mentor Office Hours", "mentor office hours description wow nice", "test lane 4", -82.3536, 29.6516, {"notes": "Drop-in", "tags": ["event"]}),
        ("2026-10-20 12:00:00+00", "Midpoint Check-in", "midpoint checkin description wow nice", "test lane 5", -82.3540, 29.6520, {"notes": "Pizza provided", "tags": ["event"]}),
    ]
    for ts, title, description, address, lon, lat, payload in sample_events:
        await db.add_event(
            timestamp=ts,
            title=title,
            description=description,
            address=address,
            longitude=lon,
            latitude=lat,
            organization_id=org_id,
            payload=payload,
        )

    return {
        "message": "Database wiped and seeded",
        "admin_user": {"id": admin_id, "email": "admin@swamphacks.com", "system_role": "admin"},
        "organization_id": org_id,
    }


@app.get("/api/getEventsDay")
async def get_events_day(day: date) -> Dict[str, Any]:
    events = await db.get_events_on_day(day)
    return {"events": events}


@app.get("/api/getEventsFromDay")
async def get_events_from_day(numdays: int = 7) -> Dict[str, Any]:
    from datetime import date as _date
    events = await db.get_events_from_start_for_days(_date.today(), numdays)
    return {"events": events}


@app.get("/api/fetchFavorites")
async def fetch_favorites(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    orgs = await db.get_user_organizations(current_user["id"])
    return {"organizations": orgs}


# -----------------------------------------------------------------------------
# Favorite/Unfavorite Organizations (Memberships)
# -----------------------------------------------------------------------------

@app.post("/api/favorites/{organization_id}")
async def favorite_organization(
    organization_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    user_id = current_user["id"]
    org = await db.get_organization(organization_id)
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    await db.assign_membership(user_id, organization_id, "member")
    orgs = await db.get_user_organizations(user_id)
    return {"organizations": orgs}


@app.delete("/api/favorites/{organization_id}")
async def unfavorite_organization(
    organization_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    user_id = current_user["id"]
    await db.remove_membership(user_id, organization_id)
    orgs = await db.get_user_organizations(user_id)
    return {"organizations": orgs}


# -----------------------------------------------------------------------------
# Dev/Test endpoints (REMOVE IN PRODUCTION)
# -----------------------------------------------------------------------------

@app.get("/api/dev/users")
async def dev_list_users() -> Dict[str, Any]:
    users = await db.get_all_users()
    return {"users": users}


@app.get("/api/dev/organizations")
async def dev_list_organizations() -> Dict[str, Any]:
    orgs = await db.get_all_organizations()
    return {"orgs": orgs}


# -----------------------------------------------------------------------------
# Individual get endpoints (no login required)
# -----------------------------------------------------------------------------

@app.get("/api/getEvent/{event_id}")
async def get_event(event_id: int) -> Dict[str, Any]:
    event = await db.get_event(event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    return {"event": event}


@app.get("/api/getOrganization/{organization_id}")
async def get_organization(organization_id: int) -> Dict[str, Any]:
    org = await db.get_organization(organization_id)
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    return {"organization": org}


@app.get("/api/getOrganizations")
async def get_organizations() -> Dict[str, Any]:
    orgs = await db.get_all_organizations()
    orgs_light = [
        {
            "id": o["id"],
            "name": o["name"],
            "description": o["description"],
            "handle": o.get("handle"),
            "conURL": o.get("conURL"),
        }
        for o in orgs
    ]
    return {"organizations": orgs_light}


# -----------------------------------------------------------------------------
# Recommendations (login required)
# -----------------------------------------------------------------------------

@app.get("/api/getRecommendations/events")
async def get_recommendations_events(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    # Placeholder: return empty list until recommendation logic is implemented
    return {"events": []}


@app.get("/api/getRecommendations/organizations")
async def get_recommendations_organizations(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    # Placeholder: return empty list until recommendation logic is implemented
    return {"organizations": []}


@app.get("/api/runscrape")
async def get_recommendations_organizations() -> Dict[str, Any]:
    