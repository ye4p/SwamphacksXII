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
  AUTH0_CLIENT_SECRET Auth0 application client secret
  AUTH0_AUDIENCE      (optional) audience claim expected in Auth0 id_tokens
  AUTH0_CALLBACK_URL  redirect URL registered in Auth0, e.g.
                      https://api.example.com/auth/auth0/callback
  FRONTEND_URL        origin users are sent to after login/logout
  COOKIE_SECURE       "true" to mark session cookies Secure (required in prod)
  CORS_ORIGINS        comma-separated list of allowed CORS origins
"""

import base64
import hashlib
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional
from urllib.parse import quote, urlencode

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
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE") or AUTH0_CLIENT_ID
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
            audience=AUTH0_AUDIENCE,
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
    authorization: Optional[str] = Header(None),
    session_token: Optional[str] = Cookie(None),
) -> Dict[str, Any]:
    token: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif session_token:
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
    if not AUTH0_DOMAIN or not AUTH0_CLIENT_ID:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Auth0 is not configured"
        )

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    response.set_cookie(
        "auth0_state",
        state,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
        max_age=600,
    )
    response.set_cookie(
        "auth0_code_verifier",
        code_verifier,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
        max_age=600,
    )

    params = {
        "response_type": "code",
        "client_id": AUTH0_CLIENT_ID,
        "redirect_uri": AUTH0_CALLBACK_URL,
        "scope": "openid profile email",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if AUTH0_AUDIENCE:
        params["audience"] = AUTH0_AUDIENCE

    authorize_url = f"https://{AUTH0_DOMAIN}/authorize?{urlencode(params)}"
    return RedirectResponse(authorize_url)


@app.get("/auth/auth0/callback")
async def auth0_callback(
    request: Request,
    response: Response,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    redirect_to: Optional[str] = Query(None),
) -> RedirectResponse:
    expected_state = request.cookies.get("auth0_state")
    code_verifier = request.cookies.get("auth0_code_verifier")

    if not code or not state or not expected_state or state != expected_state:
        _clear_auth0_cookies(response)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Invalid Auth0 request state"
        )

    token_payload = {
        "grant_type": "authorization_code",
        "client_id": AUTH0_CLIENT_ID,
        "client_secret": AUTH0_CLIENT_SECRET,
        "code": code,
        "redirect_uri": AUTH0_CALLBACK_URL,
        "code_verifier": code_verifier,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_resp = await client.post(
            f"https://{AUTH0_DOMAIN}/oauth/token", json=token_payload
        )

    if token_resp.status_code >= 400:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Auth0 token exchange failed"
        )

    tokens = token_resp.json()
    id_token = tokens.get("id_token")
    if not id_token:
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

    target = redirect_to or FRONTEND_URL
    if not target.startswith("/") and target != FRONTEND_URL:
        target = FRONTEND_URL

    _set_session_cookie(response, app_token)
    _clear_auth0_cookies(response)
    return RedirectResponse(target)


@app.get("/auth/auth0/logout")
async def auth0_logout(
    response: Response,
    redirect_to: Optional[str] = Query(None),
) -> RedirectResponse:
    _clear_session_cookie(response)
    target = redirect_to or FRONTEND_URL
    if not target.startswith("/") and target != FRONTEND_URL:
        target = FRONTEND_URL
    logout_url = (
        f"https://{AUTH0_DOMAIN}/v2/logout?"
        f"client_id={AUTH0_CLIENT_ID}&returnTo={quote(target)}"
    )
    return RedirectResponse(logout_url)


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
async def get_events_day(date: date) -> Dict[str, Any]:
    events = await db.get_events_on_day(date)
    return {"events": events}


@app.get("/api/getEventsFromDay")
async def get_events_from_day(startdate: date) -> Dict[str, Any]:
    events = await db.get_events_from_day(startdate)
    return {"events": events}


@app.get("/api/fetchFavorites")
async def fetch_favorites(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    orgs = await db.get_user_organizations(current_user["id"])
    return {"organizations": orgs}