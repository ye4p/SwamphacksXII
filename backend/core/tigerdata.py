import asyncio
import json
from datetime import datetime
import asyncpg
import os
from typing import Optional, Dict, Any, Union, List
from dotenv import load_dotenv


load_dotenv()
CONNECTION = os.getenv("CONNECTION")

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
                    location GEOMETRY(Point, 4326),
                    payload JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
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
    async def create_local_user(self, email: str, password_hash: str, system_role: str = "user", initial_data: Optional[Dict[str, Any]] = None) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, system_role, data) 
                VALUES ($1, $2, $3, $4::jsonb) 
                RETURNING id;
                """,
                email, password_hash, system_role, initial_data or {}
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
    async def upsert_organization(self, name: str, description: str, metadata: Optional[Dict[str, Any]] = None) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO organizations (name, description, metadata, updated_at)
                VALUES ($1, $2, $3::jsonb, NOW())
                ON CONFLICT (name) 
                DO UPDATE SET description = EXCLUDED.description, 
                              metadata = EXCLUDED.metadata, 
                              updated_at = NOW()
                RETURNING id;
                """,
                name, description, metadata or {}
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
    async def add_event(self, timestamp: Union[str, datetime], title: str, longitude: float, latitude: float, organization_id: Optional[int] = None, payload: Optional[Dict[str, Any]] = None) -> int:
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO events (organization_id, timestamp, title, location, payload) 
                VALUES ($1, $2, $3, ST_SetSRID(ST_MakePoint($4, $5), 4326), $6::jsonb) 
                RETURNING id;
                """,
                organization_id, timestamp, title, longitude, latitude, payload or {}
            )
            return row["id"]

    async def delete_event(self, event_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM events WHERE id = $1;", event_id)

    async def get_current_events(self) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, organization_id, timestamp, title, 
                       ST_X(location::geometry) AS longitude, 
                       ST_Y(location::geometry) AS latitude, 
                       payload 
                FROM events 
                ORDER BY timestamp ASC;
            """)
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