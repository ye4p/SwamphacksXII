import asyncio
import json
import math
from datetime import date, datetime, timedelta
import asyncpg
import os
from typing import Optional, Dict, Any, Union, List
from dotenv import load_dotenv


load_dotenv()
CONNECTION = os.getenv("CONNECTION")


def require_coordinates(longitude, latitude):
    if not all(type(value) in (int, float) and math.isfinite(value)
               and -bound <= value <= bound
               for value, bound in ((longitude, 180), (latitude, 90))):
        raise ValueError("Events require finite, in-range longitude and latitude")

class TigerData:
    def __init__(self, dsn: str = CONNECTION):
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Initialize the connection pool and register automatic JSON codecs."""
        if not self.pool:
            async def init_connection(conn):
                await conn.set_type_codec(
                    'jsonb',
                    encoder=json.dumps,
                    decoder=json.loads,
                    schema='pg_catalog'
                )
                await conn.set_type_codec(
                    'json',
                    encoder=json.dumps,
                    decoder=json.loads,
                    schema='pg_catalog'
                )

            self.pool = await asyncpg.create_pool(dsn=self.dsn, init=init_connection)

    async def close(self):
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def init_db(self):
        """Automatically create tables and safely patch any missing columns."""
        async with self.pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

            # 1. Users table base creation
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL
                );
            """)
            # Safe column additions (prevents errors if table already existed)
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS auth0_id TEXT UNIQUE;")
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;")
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT;")
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS picture TEXT;")
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS system_role TEXT CHECK (system_role IN ('user', 'mod', 'admin')) NOT NULL DEFAULT 'user';")
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS data JSONB DEFAULT '{}'::jsonb;")
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();")

            await conn.execute("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;")

            # 2. Organizations table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS organizations (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    metadata JSONB DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            await conn.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS handle TEXT;")
            await conn.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS conurl TEXT;")
            await conn.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();")

            # 3. Club Memberships table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS club_memberships (
                    id SERIAL PRIMARY KEY,
                    user_id INT REFERENCES users(id) ON DELETE CASCADE,
                    organization_id INT REFERENCES organizations(id) ON DELETE CASCADE,
                    role TEXT CHECK (role IN ('member', 'officer', 'president')) NOT NULL DEFAULT 'member',
                    joined_at TIMESTAMPTZ DEFAULT NOW(),
                    CONSTRAINT unique_user_club UNIQUE (user_id, organization_id)
                );
            """)

            # 4. Events table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id SERIAL PRIMARY KEY,
                    organization_id INT REFERENCES organizations(id) ON DELETE SET NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    address TEXT,
                    location GEOMETRY(Point, 4326),
                    payload JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            await conn.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS address TEXT;")
            await conn.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS description TEXT NOT NULL;")
            await conn.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                                   WHERE conname = 'events_valid_coordinates'
                                     AND conrelid = 'events'::regclass) THEN
                        ALTER TABLE events ADD CONSTRAINT events_valid_coordinates CHECK (
                            location IS NOT NULL AND NOT ST_IsEmpty(location)
                            AND ST_X(location) IS NOT NULL AND ST_Y(location) IS NOT NULL
                            AND ST_X(location) BETWEEN -180 AND 180
                            AND ST_Y(location) BETWEEN -90 AND 90
                        );
                    END IF;
                END $$;
            """)

            # Performance Indexes
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_auth0 ON users(auth0_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_club_memberships_user ON club_memberships(user_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_club_memberships_org ON club_memberships(organization_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_org ON events(organization_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);")

    async def wipe_database(self):
        """Wipes all data and resets IDs back to 1."""
        async with self.pool.acquire() as conn:
            await conn.execute("TRUNCATE TABLE users, organizations, club_memberships, events RESTART IDENTITY CASCADE;")

    # ==================== USERS & AUTH0 ====================
    async def create_local_user(
        self, 
        email: str, 
        password_hash: str, 
        system_role: str = "user", 
        initial_data: Optional[Dict[str, Any]] = None
    ) -> int:
        
        # If asyncpg doesn't have a JSON codec registered, use json.dumps():
        data_json = json.dumps(initial_data or {})

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, system_role, data) 
                VALUES ($1, $2, $3, $4::jsonb) 
                RETURNING id;
                """,
                email, password_hash, system_role, data_json
            )
            return row["id"]

    async def upsert_auth0_user(self, auth0_id: str, email: str, name: Optional[str] = None, picture: Optional[str] = None) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (auth0_id, email, name, picture)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (email) 
                DO UPDATE SET auth0_id = EXCLUDED.auth0_id,
                              name = COALESCE(EXCLUDED.name, users.name),
                              picture = COALESCE(EXCLUDED.picture, users.picture)
                RETURNING id;
                """,
                auth0_id, email, name, picture
            )
            return row["id"]

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id, auth0_id, email, name, picture, system_role, data, created_at FROM users WHERE id = $1;", user_id)
            return dict(row) if row else None

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Look up a user by email, including the password hash for local login verification."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, auth0_id, email, name, picture, system_role, password_hash, data, created_at FROM users WHERE email = $1;",
                email,
            )
            return dict(row) if row else None

    async def update_user_data(self, user_id: int, new_data: Dict[str, Any]):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET data = data || $1::jsonb WHERE id = $2;",
                new_data, user_id
            )

    async def delete_user(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM users WHERE id = $1;", user_id)

    # ==================== ORGANIZATIONS & MEMBERSHIPS ====================
    async def upsert_organization(self, name: str, description: str, metadata: Optional[Dict[str, Any]] = None, handle: Optional[str] = None, conURL: Optional[str] = None) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO organizations (name, description, metadata, handle, conurl, updated_at)
                VALUES ($1, $2, $3::jsonb, $4, $5, NOW())
                ON CONFLICT (name) 
                DO UPDATE SET description = EXCLUDED.description, 
                              metadata = EXCLUDED.metadata, 
                              handle = COALESCE(EXCLUDED.handle, organizations.handle),
                              conurl = COALESCE(EXCLUDED.conurl, organizations.conurl),
                              updated_at = NOW()
                RETURNING id;
                """,
                name, description, metadata or {}, handle, conURL
            )
            return row["id"]

    async def delete_organization(self, organization_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM organizations WHERE id = $1;", organization_id)

    async def assign_membership(self, user_id: int, organization_id: int, role: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO club_memberships (user_id, organization_id, role)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, organization_id)
                DO UPDATE SET role = EXCLUDED.role;
                """,
                user_id, organization_id, role
            )

    async def remove_membership(self, user_id: int, organization_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM club_memberships WHERE user_id = $1 AND organization_id = $2;",
                user_id, organization_id
            )

    async def get_user_club_role(self, user_id: int, organization_id: int) -> Optional[str]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT role FROM club_memberships WHERE user_id = $1 AND organization_id = $2;",
                user_id, organization_id
            )
            return row["role"] if row else None

    async def transfer_presidency(self, organization_id: int, current_president_id: int, new_president_id: int):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE club_memberships SET role = 'officer' WHERE user_id = $1 AND organization_id = $2 AND role = 'president';",
                    current_president_id, organization_id
                )
                await conn.execute(
                    """
                    INSERT INTO club_memberships (user_id, organization_id, role) VALUES ($1, $2, 'president') 
                    ON CONFLICT (user_id, organization_id) DO UPDATE SET role = 'president';
                    """,
                    new_president_id, organization_id
                )

    # ==================== EVENTS ====================
    async def import_gatorconnect_events(self, events: List[Dict[str, Any]]) -> int:
        """Atomically insert/update mappable public events using stable source IDs.

        Serialize imports across workers. Existing organization metadata is never
        replaced by the sparse listing. PostgreSQL allocates all local IDs.
        """
        for event in events:
            require_coordinates(event.get("longitude"), event.get("latitude"))
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(71620261018)")
                names = sorted({e["organization_name"] for e in events if e.get("organization_name")})
                await conn.executemany("""
                    INSERT INTO organizations (name) VALUES ($1)
                    ON CONFLICT (name) DO NOTHING
                """, [(name,) for name in names])
                organizations = {r["name"]: r["id"] for r in await conn.fetch(
                    "SELECT id, name FROM organizations WHERE name=ANY($1::text[])", names)}
                # One snapshot under the import lock avoids thousands of remote
                # SELECT round trips. Recognize the old Source note format too.
                by_source, by_note = {}, {}
                for row in await conn.fetch("SELECT id, payload FROM events ORDER BY id"):
                    payload = row["payload"] or {}
                    if payload.get("source") == "gatorconnect":
                        by_source.setdefault(payload.get("source_event_id"), row["id"])
                    for line in (payload.get("notes") or "").splitlines():
                        by_note.setdefault(line, row["id"])
                inserts, updates, seen = [], [], set()
                for event in events:
                    payload = event["payload"]
                    identity = payload["source_event_id"]
                    if identity in seen:
                        raise ValueError("Duplicate source ID in import batch")
                    seen.add(identity)
                    existing_id = by_source.get(identity) or by_note.get("Source: " + payload["source_url"])
                    values = (organizations.get(event.get("organization_name")),
                              datetime.fromisoformat(event["timestamp"]),
                              event["title"], event["description"], event["address"],
                              event["longitude"], event["latitude"], payload)
                    if existing_id is None:
                        inserts.append(values)
                    else:
                        updates.append((*values, existing_id))
                await conn.executemany("""
                    INSERT INTO events
                        (organization_id, timestamp, title, description, address, location, payload)
                    VALUES ($1,$2,$3,$4,$5,ST_SetSRID(ST_MakePoint($6,$7),4326),$8::jsonb)
                """, inserts)
                await conn.executemany("""
                    UPDATE events SET organization_id=$1, timestamp=$2, title=$3,
                        description=$4, address=$5,
                        location=ST_SetSRID(ST_MakePoint($6,$7),4326),
                        payload=COALESCE(payload, '{}'::jsonb) || $8::jsonb
                    WHERE id=$9
                """, updates)
        return len(events)

    async def add_event(self, timestamp: Union[str, datetime], title: str, description: str, address: str, longitude: float, latitude: float, organization_id: Optional[int] = None, payload: Optional[Dict[str, Any]] = None) -> int:
        require_coordinates(longitude, latitude)
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO events (organization_id, timestamp, title, description, address, location, payload) 
                VALUES ($1, $2, $3, $4, $5, ST_SetSRID(ST_MakePoint($6, $7), 4326), $8::jsonb) 
                RETURNING id;
                """,
                organization_id, timestamp, title, description, address, longitude, latitude, payload or {}
            )
            return row["id"]

    async def delete_event(self, event_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM events WHERE id = $1;", event_id)

    async def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, organization_id, timestamp, title, description, address,
                       ST_X(location::geometry) AS longitude,
                       ST_Y(location::geometry) AS latitude,
                       payload
                FROM events
                WHERE id = $1;
            """, event_id)
            return dict(row) if row else None



    async def get_current_events(self) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, organization_id, timestamp, title, description, address,
                       ST_X(location::geometry) AS longitude,
                       ST_Y(location::geometry) AS latitude,
                       payload
                FROM events
                ORDER BY timestamp ASC;
            """)
            return [dict(row) for row in rows]

    # ==================== DATE-BASED EVENT QUERIES ====================
    async def get_events_on_day(self, target_date: date) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, organization_id, timestamp, title, description, address,
                       ST_X(location::geometry) AS longitude,
                       ST_Y(location::geometry) AS latitude,
                       payload
                FROM events
                WHERE timestamp::date = $1
                ORDER BY timestamp ASC;
            """, target_date)
            return [dict(row) for row in rows]

    async def get_events_from_day(
        self, start_date: date, cap_months: int = 7
    ) -> List[Dict[str, Any]]:
        end_date = start_date + timedelta(days=cap_months * 30)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, organization_id, timestamp, title, description, address,
                       ST_X(location::geometry) AS longitude,
                       ST_Y(location::geometry) AS latitude,
                       payload
                FROM events
                WHERE timestamp >= $1 AND timestamp <= $2
                ORDER BY timestamp ASC;
            """, start_date, end_date)
            return [dict(row) for row in rows]

    async def get_events_from_start_for_days(
        self, start_date: date, num_days: int
    ) -> List[Dict[str, Any]]:
        if num_days < 0:
            num_days = 0
        end_date = start_date + timedelta(days=num_days - 1) if num_days > 0 else start_date
        if num_days <= 0:
            end_date = start_date
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, organization_id, timestamp, title, description, address,
                       ST_X(location::geometry) AS longitude,
                       ST_Y(location::geometry) AS latitude,
                       payload
                FROM events
                WHERE timestamp::date >= $1 AND timestamp::date <= $2
                ORDER BY timestamp ASC;
            """, start_date, end_date)
            return [dict(row) for row in rows]



    # ==================== ORGANIZATION MEMBERSHIP (FAVORITES) ====================
    async def get_organization(self, organization_id: int) -> Optional[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id, name, description, metadata, handle, conurl, created_at, updated_at FROM organizations WHERE id = $1;", organization_id)
            return dict(row) if row else None
    async def get_all_organizations(self) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, name, description, metadata, handle, conurl, created_at, updated_at FROM organizations ORDER BY id ASC;")
            return [dict(row) for row in rows]


    async def get_user_organizations(self, user_id: int) -> List[Dict[str, Any]]:
        """Return all organizations the user is a member of (their 'favorites')."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT o.id, o.name, o.description, o.metadata, o.handle, o.conurl, o.created_at, o.updated_at,
                       cm.role, cm.joined_at
                FROM organizations o
                JOIN club_memberships cm ON cm.organization_id = o.id
                WHERE cm.user_id = $1
                ORDER BY o.name ASC;
            """, user_id)
            return [dict(row) for row in rows]



    async def get_all_users(self) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, auth0_id, email, name, picture, system_role, data, created_at FROM users ORDER BY id ASC;")
            return [dict(row) for row in rows]

# ==================== FULL TEST SUITE ====================
# async def main():
#     db = TigerData(CONNECTION)
#     await db.connect()
    
#     print("--- 1. Initializing Database & Extensions ---")
#     await db.init_db()

#     await db.wipe_database()

#     print("\n--- 2. Creating Test Users & Admin ---")
#     admin_id = await db.create_user("admin@tiger.com", "fake_hash_1", is_admin=True, initial_data={"name": "Head Admin"})
#     user1_id = await db.create_user("alice@tiger.com", "fake_hash_2", is_admin=False, initial_data={"major": "Computer Science"})
#     user2_id = await db.create_user("bob@tiger.com", "fake_hash_3", is_admin=False, initial_data={"major": "Biology"})
#     print(f"Created Admin ID: {admin_id}, Alice ID: {user1_id}, Bob ID: {user2_id}")

#     print("\n--- 3. Testing User JSON Dynamic Updates (Auto-decoded Dicts) ---")
#     await db.update_user_data(user1_id, {"major": "Computer Engineering", "graduation_year": 2027})
#     updated_alice = await db.get_user(user1_id)
#     print("Updated Alice Data:", updated_alice)

#     print("\n--- 4. Creating Organizations (Clubs) ---")
#     club_id = await db.upsert_organization("Robotics Club", "Building autonomous rovers", {"room": "Lab 3B"})
#     print(f"Created Club ID: {club_id}")

#     print("\n--- 5. Testing Memberships & Seamless Role Transitions ---")
#     await db.assign_membership(user1_id, club_id, "member")
#     print("Alice's role:", await db.get_user_club_role(user1_id, club_id))

#     await db.assign_membership(user1_id, club_id, "president")
#     print("Alice's upgraded role:", await db.get_user_club_role(user1_id, club_id))

#     await db.assign_membership(user2_id, club_id, "member")
#     await db.assign_membership(user2_id, club_id, "officer")
#     print("Bob's role (Officer):", await db.get_user_club_role(user2_id, club_id))

#     print("\n--- 6. Testing Presidency Transfer ---")
#     await db.transfer_presidency(club_id, current_president_id=user1_id, new_president_id=user2_id)
#     print("New President (Bob):", await db.get_user_club_role(user2_id, club_id))
#     print("Old President Demoted (Alice):", await db.get_user_club_role(user1_id, club_id))

#     print("\n--- 7. Testing PostGIS Event Creation & Retrieval (with String Date Parsing) ---")
#     event_id = await db.add_event(
#         organization_id=club_id,
#         timestamp="2026-05-15 15:30:00+00",  # String date passed directly!
#         title="Rover Test Drive",
#         longitude=-82.3536,
#         latitude=29.6516,
#         payload={"notes": "Bring tools"}
#     )
#     print(f"Created Event ID: {event_id}")
    
#     events = await db.get_current_events()
#     print("All Current Events:", events)

#     print("\n--- 8. Testing Deletions ---")
#     await db.delete_event(event_id)
#     print("Event deleted successfully.")

#     await db.remove_membership(user1_id, club_id)
#     print("Alice removed from club membership.")

#     await db.delete_user(user2_id)
#     print("Bob deleted entirely.")

#     await db.close()
#     print("\n--- All Tests Passed Successfully! ---")

async def main():
    db = TigerData(CONNECTION)
    await db.connect()
    await db.init_db()
    await db.wipe_database()

    print("--- Testing Auth0 Google Login Sync ---")
    google_user_id = await db.upsert_auth0_user(
        auth0_id="google-oauth2|1078510938475",
        email="student@gator.edu",
        name="Albert Gator",
        picture="https://example.com/avatar.jpg"
    )
    user_record = await db.get_user(google_user_id)
    print("Synced Auth0 User:", user_record)

    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
