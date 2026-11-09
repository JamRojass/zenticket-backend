"""
Database Repository Layer (DBRepository).
Encapsulates all asynchronous database interactions and queries using aiosqlite.
"""

from typing import Optional, List, Dict, Any
import logging
import time
import aiosqlite

logger = logging.getLogger("uvicorn.error")

class DBRepository:
    """Handles data persistence operations across SQLite tables."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def create_company(self, name: str, short_code: str) -> Dict[str, Any]:
        """Inserts a new company record into the database."""
        now = int(time.time())
        cursor = await self.db.execute(
            "INSERT INTO companies (name, short_code, is_active, created_at) VALUES (?, ?, 1, ?)",
            (name, short_code.upper(), now)
        )
        await self.db.commit()
        return await self.get_company_by_id(cursor.lastrowid)

    async def get_company_by_id(self, company_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a company by its unique primary key ID."""
        async with self.db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_company_by_short_code(self, short_code: str) -> Optional[Dict[str, Any]]:
        """Retrieves a company by its short code (case-insensitive)."""
        async with self.db.execute("SELECT * FROM companies WHERE UPPER(short_code) = UPPER(?)", (short_code,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_companies(self) -> List[Dict[str, Any]]:
        """Lists all active companies."""
        async with self.db.execute("SELECT * FROM companies WHERE is_active = 1 ORDER BY id DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def create_user(self, company_id: int, username: str, password_hash: str, role: str, fullname: str = "Administrator", area_id: Optional[int] = None) -> dict:
        """Creates a new user account."""
        now = int(time.time())
        async with self.db.execute(
            "INSERT INTO users (company_id, username, fullname, password_hash, role, area_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (company_id, username, fullname, password_hash, role, area_id, now)
        ) as cursor:
            user_id = cursor.lastrowid
            await self.db.commit()
            return {
                "id": user_id, 
                "company_id": company_id, 
                "username": username, 
                "fullname": fullname, 
                "role": role, 
                "area_id": area_id, 
                "is_active": 1,
                "created_at": now
            }

    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a user by ID along with company short code details."""
        async with self.db.execute(
            """SELECT u.*, c.short_code AS company_short_code 
               FROM users u 
               LEFT JOIN companies c ON u.company_id = c.id 
               WHERE u.id = ?""", 
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Retrieves a user by username along with company short code details."""
        async with self.db.execute(
            """SELECT u.*, c.short_code AS company_short_code 
               FROM users u 
               LEFT JOIN companies c ON u.company_id = c.id 
               WHERE u.username = ?""", 
            (username,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def count_users_by_company(
        self, 
        company_id: int, 
        area_id: int | None = None,
        username: str | None = None
    ) -> int:
        """Counts users belonging to a company with optional filters."""
        query = """
            SELECT COUNT(*) AS total 
            FROM users u 
            WHERE u.company_id = ? AND u.is_active = 1
        """
        params = [company_id]
        if area_id is not None:
            query += " AND u.area_id = ?"
            params.append(area_id)
        if username:
            query += " AND u.username LIKE ?"
            params.append(f"%{username}%")
        async with self.db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return row["total"] if row else 0

    async def list_users_by_company(
            self, 
            company_id: int, 
            limit: int = 100, 
            offset: int = 0,
            area_id: int | None = None,
            username: str | None = None
        ) -> List[Dict[str, Any]]:
            """Lists users belonging to a company with pagination and filters."""
            query = """
                SELECT u.id, u.company_id, c.short_code AS company_short_code, u.username, u.fullname, u.role, u.area_id, u.is_active, u.created_at, a.name AS area_name 
                FROM users u 
                LEFT JOIN areas a ON u.area_id = a.id 
                LEFT JOIN companies c ON u.company_id = c.id
                WHERE u.company_id = ? AND u.is_active = 1
            """
            params = [company_id]
            if area_id is not None:
                query += " AND u.area_id = ?"
                params.append(area_id)
            if username:
                query += " AND u.username LIKE ?"
                params.append(f"%{username}%")
            query += " ORDER BY u.id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            async with self.db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def update_user_profile(self, user_id: int, username: Optional[str] = None, password_hash: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Updates user profile credentials."""
        if username and password_hash:
            await self.db.execute(
                "UPDATE users SET username = ?, password_hash = ? WHERE id = ?",
                (username, password_hash, user_id)
            )
        elif username:
            await self.db.execute(
                "UPDATE users SET username = ? WHERE id = ?",
                (username, user_id)
            )
        elif password_hash:
            await self.db.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user_id)
            )
        await self.db.commit()
        return await self.get_user_by_id(user_id)

    async def update_username(self, user_id: int, company_id: int, username: str) -> Optional[Dict[str, Any]]:
        """Updates a user's username within a specific company."""
        await self.db.execute(
            "UPDATE users SET username = ? WHERE id = ? AND company_id = ?",
            (username, user_id, company_id)
        )
        await self.db.commit()
        async with self.db.execute("SELECT * FROM users WHERE id = ? AND company_id = ?", (user_id, company_id)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def update_user_details(self, user_id: int, company_id: int, fullname: Optional[str] = None, area_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Updates user details like full name and assigned area."""
        await self.db.execute(
            "UPDATE users SET fullname = COALESCE(?, fullname), area_id = ? WHERE id = ? AND company_id = ?",
            (fullname, area_id, user_id, company_id)
        )
        await self.db.commit()
        async with self.db.execute(
            """SELECT u.id, u.company_id, c.short_code AS company_short_code, u.username, u.fullname, u.role, u.area_id, u.is_active, u.created_at, a.name AS area_name 
               FROM users u 
               LEFT JOIN areas a ON u.area_id = a.id 
               LEFT JOIN companies c ON u.company_id = c.id
               WHERE u.id = ? AND u.company_id = ?""",
            (user_id, company_id)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def update_user_password_hashed(self, user_id: int, company_id: int, hashed_password: str) -> bool:
        """Updates a user's hashed password."""
        cursor = await self.db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ? AND company_id = ?",
            (hashed_password, user_id, company_id)
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def create_active_session(self, session_id: str, user_id: int, company_id: int, expires_at: int) -> None:
        """Registers a new active user session."""
        await self.db.execute(
            "INSERT INTO active_sessions (id, user_id, company_id, expires_at) VALUES (?, ?, ?, ?)",
            (session_id, user_id, company_id, expires_at)
        )
        await self.db.commit()

    async def get_active_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves an active session by session ID."""
        async with self.db.execute("SELECT * FROM active_sessions WHERE id = ?", (session_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def delete_active_session(self, session_id: str) -> None:
        """Deletes an active session record."""
        await self.db.execute("DELETE FROM active_sessions WHERE id = ?", (session_id,))
        await self.db.commit()

    async def get_user_active_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """Retrieves all active sessions for a user."""
        async with self.db.execute("SELECT * FROM active_sessions WHERE user_id = ?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def delete_active_sessions_by_user(self, user_id: int) -> None:
        """Deletes all active sessions associated with a user ID."""
        await self.db.execute("DELETE FROM active_sessions WHERE user_id = ?", (user_id,))
        await self.db.commit()

    async def get_user_station_session(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves an active station working session for a user."""
        async with self.db.execute("SELECT * FROM station_sessions WHERE user_id = ? AND (is_active = 1 OR ended_at IS NULL)", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def close_station_sessions_by_user(self, user_id: int) -> None:
        """Closes all active station sessions for a user."""
        now = int(time.time())
        await self.db.execute(
            "UPDATE station_sessions SET is_active = 0, ended_at = ? WHERE user_id = ? AND (is_active = 1 OR ended_at IS NULL)",
            (now, user_id)
        )
        await self.db.commit()

    async def handle_operator_orphan_tickets(self, user_id: int) -> None:
        """Reassigns or cleans up tickets left in progress by a disconnected operator."""
        await self.db.execute(
            "UPDATE tickets SET status = 'WAITING', assigned_user_id = NULL WHERE assigned_user_id = ? AND status = 'CALLED'",
            (user_id,)
        )
        now = int(time.time())
        await self.db.execute(
            "UPDATE tickets SET status = 'COMPLETED', completed_at = ? WHERE assigned_user_id = ? AND status = 'CALLED'",
            (user_id, now)
        )
        await self.db.commit()

    async def soft_delete_user(self, user_id: int, company_id: int) -> bool:
        """Performs a soft delete on a staff user account."""
        user = await self.get_user_by_id(user_id)
        if not user or user["company_id"] != company_id:
            return False
        if user["role"] == "admin":
            raise ValueError("Administrator accounts cannot be deleted.")
        await self.delete_active_sessions_by_user(user_id)
        await self.close_station_sessions_by_user(user_id)
        await self.handle_operator_orphan_tickets(user_id)
        cursor = await self.db.execute(
            "UPDATE users SET is_active = 0 WHERE id = ? AND company_id = ?",
            (user_id, company_id)
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def get_active_sessions_count(self, user_id: int) -> int:
        """Counts valid non-expired active sessions for a user."""
        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM active_sessions WHERE user_id = ? AND expires_at > ?",
            (user_id, int(time.time()))
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def create_area(self, company_id: int, name: str, short_code: str) -> Dict[str, Any]:
        """Creates a new service department area."""
        now = int(time.time())
        cursor = await self.db.execute(
            "INSERT INTO areas (company_id, name, short_code, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
            (company_id, name, short_code.upper(), now)
        )
        await self.db.commit()
        return await self.get_area_by_id(cursor.lastrowid)

    async def get_area_by_id(self, area_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a service area by its ID."""
        async with self.db.execute("SELECT * FROM areas WHERE id = ?", (area_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_areas_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Lists active service areas for a company."""
        async with self.db.execute(
            "SELECT * FROM areas WHERE company_id = ? AND is_active = 1 ORDER BY id ASC",
            (company_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def list_areas(self, company_id: int) -> List[Dict[str, Any]]:
        """Lists active areas for a company."""
        async with self.db.execute(
            "SELECT * FROM areas WHERE company_id = ? AND is_active = 1",
            (company_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def update_area(self, area_id: int, company_id: int, name: str, short_code: str) -> Optional[Dict[str, Any]]:
        """Updates a service area record."""
        await self.db.execute(
            "UPDATE areas SET name = ?, short_code = ? WHERE id = ? AND company_id = ?",
            (name, short_code, area_id, company_id)
        )
        await self.db.commit()
        async with self.db.execute("SELECT * FROM areas WHERE id = ? AND company_id = ?", (area_id, company_id)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def count_active_station_sessions_by_area(self, area_id: int) -> int:
        """Counts active station sessions belonging to an area."""
        query = """
            SELECT COUNT(*) as count 
            FROM station_sessions ss
            JOIN stations s ON ss.station_id = s.id
            WHERE s.area_id = ? AND ss.is_active = 1
        """
        async with self.db.execute(query, (area_id,)) as cursor:
            row = await cursor.fetchone()
            return row["count"] if row else 0

    async def delete_area(self, area_id: int, company_id: int) -> bool:
        """Logically deactivates a service area."""
        cursor = await self.db.execute(
            "UPDATE areas SET is_active = 0 WHERE id = ? AND company_id = ?",
            (area_id, company_id)
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def create_station(self, company_id: int, area_id: int, name: str) -> dict:
        """Creates a new station record."""
        async with self.db.execute(
            "INSERT INTO stations (company_id, area_id, name, created_at) VALUES (?, ?, ?, ?)",
            (company_id, area_id, name, int(time.time()))
        ) as cursor:
            station_id = cursor.lastrowid
            await self.db.commit()
            return {"id": station_id, "company_id": company_id, "area_id": area_id, "name": name, "is_active": 1}

    async def update_station(self, station_id: int, company_id: int, area_id: int, name: str) -> dict:
        """Updates an existing station record."""
        async with self.db.execute(
            "UPDATE stations SET area_id = ?, name = ? WHERE id = ? AND company_id = ?",
            (area_id, name, station_id, company_id)
        ) as cursor:
            await self.db.commit()
            return {
                "id": station_id, 
                "company_id": company_id, 
                "area_id": area_id, 
                "name": name, 
                "is_active": 1
            }

    async def count_stations_by_company(
        self, 
        company_id: int, 
        area_id: int | None = None,
        name: str | None = None
    ) -> int:
        """Counts active stations for a company with optional filters."""
        query = "SELECT COUNT(*) AS total FROM stations WHERE company_id = ? AND is_active = 1"
        params = [company_id]
        if area_id is not None:
            query += " AND area_id = ?"
            params.append(area_id)
        if name:
            query += " AND name LIKE ?"
            params.append(f"%{name}%")
        async with self.db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return row["total"] if row else 0

    async def get_stations_by_company(
    self, 
    company_id: int, 
    limit: int = 100, 
    offset: int = 0,
    area_id: int | None = None,
    name: str | None = None
) -> list:
        """Retrieves stations for a company with pagination, filters, and area name."""
        query = """
            SELECT stations.*, areas.name as area_name 
            FROM stations 
            LEFT JOIN areas ON stations.area_id = areas.id 
            WHERE stations.company_id = ? AND stations.is_active = 1
        """
        params = [company_id]
        if area_id is not None:
            query += " AND stations.area_id = ?"
            params.append(area_id)
        if name:
            query += " AND stations.name LIKE ?"
            params.append(f"%{name}%")
        query += " ORDER BY stations.id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_stations_by_area(self, area_id: int) -> list:
        """Retrieves available unassigned active stations for an area."""
        query = """
            SELECT s.* 
            FROM stations s
            WHERE s.area_id = ?
            AND s.is_active = 1 
            AND NOT EXISTS (
                SELECT 1 
                FROM station_sessions ss
                WHERE ss.station_id = s.id
                    AND ss.is_active = 1
            );
        """
        async with self.db.execute(query, (area_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_station_by_id(self, station_id: int) -> Optional[dict]:
        """Retrieves a station by its ID."""
        async with self.db.execute(
            "SELECT * FROM stations WHERE id = ?", (station_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_next_waiting_ticket_by_area(self, company_id: int, area_id: int) -> Optional[dict]:
        """Retrieves the next waiting ticket for a specific area."""
        async with self.db.execute(
            """SELECT * FROM tickets 
               WHERE company_id = ? AND area_id = ? AND status = 'WAITING' 
               ORDER BY created_at ASC, id ASC LIMIT 1""",
            (company_id, area_id)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def count_active_sessions_by_station(self, station_id: int) -> int:
        """Counts active sessions using a specific station."""
        query = "SELECT COUNT(*) as count FROM station_sessions WHERE station_id = ? AND is_active = 1"
        async with self.db.execute(query, (station_id,)) as cursor:
            row = await cursor.fetchone()
            return row["count"] if row else 0

    async def delete_station(self, station_id: int, company_id: int) -> bool:
        """Logically deactivates a station."""
        cursor = await self.db.execute(
            "UPDATE stations SET is_active = 0 WHERE id = ? AND company_id = ?",
            (station_id, company_id)
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def create_station_session(self, company_id: int, station_id: int, user_id: int) -> int:
        """Creates a new active working station session for an operator."""
        query = """
            INSERT INTO station_sessions (company_id, station_id, user_id, is_active, started_at)
            VALUES (?, ?, ?, 1, strftime('%s', 'now'))
        """
        cursor = await self.db.execute(query, (company_id, station_id, user_id))
        await self.db.commit()
        return cursor.lastrowid

    async def create_ticket(self, company_id: int, area_id: int, ticket_code: str) -> Dict[str, Any]:
        """Creates a new waiting ticket."""
        now = int(time.time())
        cursor = await self.db.execute(
            "INSERT INTO tickets (company_id, area_id, ticket_code, status, assigned_user_id, created_at) VALUES (?, ?, ?, 'WAITING', NULL, ?)",
            (company_id, area_id, ticket_code, now)
        )
        await self.db.commit()
        return await self.get_ticket_by_id(cursor.lastrowid)

    async def get_ticket_by_id(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a ticket by ID with area and assigned user details."""
        query = """
            SELECT t.*, a.name AS area_name, u.username AS assigned_username
            FROM tickets t
            LEFT JOIN areas a ON t.area_id = a.id
            LEFT JOIN users u ON t.assigned_user_id = u.id
            WHERE t.id = ?
        """
        async with self.db.execute(query, (ticket_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_next_waiting_ticket(self, company_id: int, area_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Retrieves the next waiting ticket globally or for a specific area."""
        if area_id:
            query = """
                SELECT * FROM tickets
                WHERE company_id = ? AND area_id = ? AND status = 'WAITING'
                ORDER BY created_at ASC, id ASC LIMIT 1
            """
            params = (company_id, area_id)
        else:
            query = """
                SELECT * FROM tickets
                WHERE company_id = ? AND status = 'WAITING'
                ORDER BY created_at ASC, id ASC LIMIT 1
            """
            params = (company_id,)
        async with self.db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_active_ticket_for_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves the active ticket currently being served by a user."""
        query = """
            SELECT t.*, a.name AS area_name, u.username AS assigned_username
            FROM tickets t
            LEFT JOIN areas a ON t.area_id = a.id
            LEFT JOIN users u ON t.assigned_user_id = u.id
            WHERE t.assigned_user_id = ? AND t.status = 'CALLED'
            ORDER BY t.called_at DESC LIMIT 1
        """
        async with self.db.execute(query, (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_ticket_status(self, ticket_id: int, status: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Updates ticket status and writes a transaction log entry."""
        current_ticket = await self.get_ticket_by_id(ticket_id)
        if not current_ticket:
            return None
        previous_status = current_ticket["status"]
        area_id = current_ticket["area_id"]
        now = int(time.time())
        if status == 'CALLED':
            await self.db.execute(
                "UPDATE tickets SET status = ?, assigned_user_id = ?, called_at = ? WHERE id = ?",
                (status, user_id, now, ticket_id)
            )
        elif status in ('COMPLETED', 'CANCELLED'):
            await self.db.execute(
                "UPDATE tickets SET status = ?, completed_at = ? WHERE id = ?",
                (status, now, ticket_id)
            )
        elif status == 'WAITING':
            await self.db.execute(
                "UPDATE tickets SET status = ?, assigned_user_id = NULL, called_at = NULL WHERE id = ?",
                (status, ticket_id)
            )
        else:
            await self.db.execute(
                "UPDATE tickets SET status = ? WHERE id = ?",
                (status, ticket_id)
            )
        await self.db.execute(
            """
            INSERT INTO ticket_logs (ticket_id, previous_status, new_status, user_id, area_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ticket_id, previous_status, status, user_id, area_id, now)
        )
        await self.db.commit()
        return await self.get_ticket_by_id(ticket_id)

    async def derive_ticket(self, ticket_id: int, target_area_id: int) -> Optional[Dict[str, Any]]:
        """Derives a ticket to a new area, resetting it to waiting status."""
        await self.db.execute(
            "UPDATE tickets SET area_id = ?, status = 'WAITING', assigned_user_id = NULL WHERE id = ?",
            (target_area_id, ticket_id)
        )
        await self.db.commit()
        return await self.get_ticket_by_id(ticket_id)

    async def list_recent_called_tickets(self, company_id: int, limit: int = 6) -> List[Dict[str, Any]]:
        """Lists recently called tickets during the active shift, including station details."""
        query = """
            SELECT t.*, a.name AS area_name, u.username AS assigned_username, s.name AS station_name
            FROM tickets t
            LEFT JOIN areas a ON t.area_id = a.id
            LEFT JOIN users u ON t.assigned_user_id = u.id
            LEFT JOIN station_sessions ss ON ss.user_id = u.id AND ss.is_active = 1
            LEFT JOIN stations s ON ss.station_id = s.id
            WHERE t.company_id = ? AND t.status = 'CALLED'
            AND t.created_at >= COALESCE(
                (SELECT opened_at FROM shifts WHERE company_id = ? AND status = 'OPEN' ORDER BY id DESC LIMIT 1),
                0
            )
            ORDER BY t.called_at DESC, t.id DESC LIMIT ?
        """
        async with self.db.execute(query, (company_id, company_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def list_waiting_tickets(self, company_id: int) -> List[Dict[str, Any]]:
        """Lists waiting tickets for the active shift, including station details."""
        query = """
            SELECT t.*, a.name AS area_name, u.username AS assigned_username, s.name AS station_name
            FROM tickets t
            LEFT JOIN areas a ON t.area_id = a.id
            LEFT JOIN users u ON t.assigned_user_id = u.id
            LEFT JOIN station_sessions ss ON ss.user_id = u.id AND ss.is_active = 1
            LEFT JOIN stations s ON ss.station_id = s.id
            WHERE t.company_id = ? AND t.status = 'WAITING'
            AND t.created_at >= COALESCE(
                (SELECT opened_at FROM shifts WHERE company_id = ? AND status = 'OPEN' ORDER BY id DESC LIMIT 1),
                0
            )
            ORDER BY t.created_at ASC, t.id ASC
        """
        async with self.db.execute(query, (company_id, company_id)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def count_tickets_history(
        self, 
        company_id: int, 
        area_id: int | None = None,
        status: str | None = None,
        start_date: int | None = None,
        end_date: int | None = None
    ) -> int:
        """Counts historical tickets with optional filters."""
        query = """
            SELECT COUNT(t.id) AS total
            FROM tickets t
            WHERE t.company_id = ?
        """
        params = [company_id]
        if area_id is not None:
            query += " AND t.area_id = ?"
            params.append(area_id)
        if status:
            query += " AND t.status = ?"
            params.append(status)
        if start_date is not None:
            query += " AND t.created_at >= ?"
            params.append(start_date)
        if end_date is not None:
            query += " AND t.created_at <= ?"
            params.append(end_date)
        async with self.db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return row["total"] if row else 0

    async def list_tickets_history(
        self, 
        company_id: int, 
        limit: int = 100, 
        offset: int = 0,
        area_id: int | None = None,
        status: str | None = None,
        start_date: int | None = None,
        end_date: int | None = None
    ) -> List[Dict[str, Any]]:
        """Lists historical tickets with pagination and filters."""
        query = """
            SELECT t.*, a.name AS area_name, u.username AS assigned_username
            FROM tickets t
            LEFT JOIN areas a ON t.area_id = a.id
            LEFT JOIN users u ON t.assigned_user_id = u.id
            WHERE t.company_id = ?
        """
        params = [company_id]
        if area_id is not None:
            query += " AND t.area_id = ?"
            params.append(area_id)
        if status:
            query += " AND t.status = ?"
            params.append(status)
        if start_date is not None:
            query += " AND t.created_at >= ?"
            params.append(start_date)
        if end_date is not None:
            query += " AND t.created_at <= ?"
            params.append(end_date)
        query += " ORDER BY t.created_at DESC, t.id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_max_ticket_number_for_area(self, company_id: int, area_code: str) -> int:
        """Gets the maximum ticket sequence number for an area during the active shift."""
        active_shift = await self.get_active_shift(company_id)
        min_opened_at = active_shift["opened_at"] if active_shift else 0
        query = """
            SELECT ticket_code FROM tickets
            WHERE company_id = ? AND ticket_code LIKE ? AND created_at >= ?
            ORDER BY id DESC LIMIT 50
        """
        prefix = f"{area_code}-%"
        max_num = 0
        async with self.db.execute(query, (company_id, prefix, min_opened_at)) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                code = row["ticket_code"]
                try:
                    num = int(code.split("-")[-1])
                    if num > max_num:
                        max_num = num
                except (ValueError, IndexError):
                    continue
        return max_num

    async def create_audit_log(self, company_id: int, user_id: Optional[int], action: str, details: str = "") -> None:
        """Inserts an audit log record."""
        now = int(time.time())
        await self.db.execute(
            "INSERT INTO audit_logs (company_id, user_id, action, details, created_at) VALUES (?, ?, ?, ?, ?)",
            (company_id, user_id, action, details, now)
        )
        await self.db.commit()

    async def count_audit_logs(
        self, 
        company_id: int, 
        start_date: int | None = None, 
        end_date: int | None = None, 
        user_id: int | None = None
    ) -> int:
        """Counts audit logs with filtering."""
        query = """
            SELECT COUNT(*) AS total 
            FROM audit_logs al
            WHERE al.company_id = ?
        """
        params = [company_id]
        if start_date is not None:
            query += " AND al.created_at >= ?"
            params.append(start_date)
        if end_date is not None:
            query += " AND al.created_at <= ?"
            params.append(end_date)
        if user_id is not None:
            query += " AND al.user_id = ?"
            params.append(user_id)
        async with self.db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return row["total"] if row else 0

    async def list_audit_logs(
        self, 
        company_id: int, 
        limit: int = 50, 
        offset: int = 0,
        start_date: int | None = None, 
        end_date: int | None = None, 
        user_id: int | None = None
    ) -> List[Dict[str, Any]]:
        """Lists audit logs with pagination and filters."""
        query = """
            SELECT al.*, u.username
            FROM audit_logs al
            LEFT JOIN users u ON al.user_id = u.id
            WHERE al.company_id = ?
        """
        params = [company_id]
        if start_date is not None:
            query += " AND al.created_at >= ?"
            params.append(start_date)
        if end_date is not None:
            query += " AND al.created_at <= ?"
            params.append(end_date)
        if user_id is not None:
            query += " AND al.user_id = ?"
            params.append(user_id)
        query += " ORDER BY al.created_at DESC, al.id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_metrics_summary(self, company_id: int) -> Dict[str, Any]:
        """Calculates operational metrics summary for a company."""
        query = """
            SELECT
                COUNT(*) as total_tickets,
                SUM(CASE WHEN status = 'WAITING' THEN 1 ELSE 0 END) as waiting_count,
                SUM(CASE WHEN status = 'CALLED' THEN 1 ELSE 0 END) as called_count,
                SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_count,
                SUM(CASE WHEN status = 'DERIVED' THEN 1 ELSE 0 END) as derived_count,
                SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) as cancelled_count,
                AVG(CASE WHEN status = 'COMPLETED' AND completed_at IS NOT NULL AND called_at IS NOT NULL
                         THEN (completed_at - called_at) ELSE NULL END) as avg_duration
            FROM tickets
            WHERE company_id = ?
        """
        async with self.db.execute(query, (company_id,)) as cursor:
            row = await cursor.fetchone()
            return {
                "total_tickets_today": row["total_tickets"] or 0,
                "waiting_tickets": row["waiting_count"] or 0,
                "in_service_tickets": row["called_count"] or 0,
                "completed_tickets": row["completed_count"] or 0,
                "derived_tickets": row["derived_count"] or 0,
                "cancelled_tickets": row["cancelled_count"] or 0,
                "avg_service_time_seconds": round(float(row["avg_duration"] or 0.0), 2)
            }

    async def count_display_screens(
        self, 
        company_id: int, 
        name: str | None = None, 
        device_type: str | None = None
    ) -> int:
        """Counts display screens with filters."""
        query = "SELECT COUNT(*) AS total FROM display_screens WHERE company_id = ?"
        params = [company_id]
        if name:
            query += " AND name LIKE ?"
            params.append(f"%{name}%")
        if device_type:
            query += " AND type = ?"
            params.append(device_type)
        async with self.db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return row["total"] if row else 0

    async def list_display_screens(
        self, 
        company_id: int, 
        limit: int = 100, 
        offset: int = 0, 
        name: str | None = None, 
        device_type: str | None = None
    ) -> List[Dict[str, Any]]:
        """Lists display screens with pagination and filters."""
        query = "SELECT id, company_id, name, type, pairing_code, is_active, created_at FROM display_screens WHERE company_id = ? and is_deleted = 0"
        params = [company_id]
        if name:
            query += " AND name LIKE ?"
            params.append(f"%{name}%")
        if device_type:
            query += " AND type = ?"
            params.append(device_type)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def create_display_screen(self, company_id: int, name: str, pairing_code: str, device_type: str = "tv") -> Dict[str, Any]:
        """Creates a new display screen record."""
        now = int(time.time())
        cursor = await self.db.execute(
            "INSERT INTO display_screens (company_id, name, type, pairing_code, is_active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
            (company_id, name, device_type, pairing_code, now)
        )
        await self.db.commit()
        async with self.db.execute("SELECT id, company_id, name, type, pairing_code, is_active, created_at FROM display_screens WHERE id = ?", (cursor.lastrowid,)) as cur:
            row = await cur.fetchone()
            return dict(row)

    async def update_display_screen(self, display_id: int, company_id: int, name: str, device_type: str) -> Dict[str, Any]:
        """Updates a display screen record."""
        async with self.db.execute(
            "UPDATE display_screens SET name = ?, type = ? WHERE id = ? AND company_id = ?",
            (name, device_type, display_id, company_id)
        ) as cursor:
            await self.db.commit()
        async with self.db.execute(
            "SELECT id, company_id, name, type, pairing_code, is_active, created_at FROM display_screens WHERE id = ? AND company_id = ?",
            (display_id, company_id)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else {}

    async def update_display_screen_status(self, screen_id: int, company_id: int, is_active: int) -> Optional[Dict[str, Any]]:
        """Updates display screen active status."""
        await self.db.execute(
            "UPDATE display_screens SET is_active = ? WHERE id = ? AND company_id = ?",
            (is_active, screen_id, company_id)
        )
        await self.db.commit()
        async with self.db.execute("SELECT * FROM display_screens WHERE id = ? AND company_id = ?", (screen_id, company_id)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def delete_display_screen(self, screen_id: int, company_id: int) -> bool:
        """Deletes a display screen record."""
        cursor = await self.db.execute(
            "DELETE FROM display_screens WHERE id = ? AND company_id = ?",
            (screen_id, company_id)
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def validate_screen_pairing(self, company_id: int, pairing_code: str, expected_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Validates a display pairing code."""
        query = "SELECT * FROM display_screens WHERE company_id = ? AND pairing_code = ? AND is_active = 1"
        params = [company_id, pairing_code]
        if expected_type:
            query += " AND type = ?"
            params.append(expected_type)
        async with self.db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def regenerate_display_code(self, display_id: int, company_id: int, new_code: str) -> bool:
        """Regenerates pairing code for a display."""
        query = "UPDATE display_screens SET pairing_code = ? WHERE id = ? AND company_id = ? AND is_active = 1"
        cursor = await self.db.execute(query, (new_code, display_id, company_id))
        await self.db.commit()
        return cursor.rowcount > 0

    async def get_display_by_id(self, display_id: int, company_id: int):
        """Retrieves a display screen by ID."""
        query = "SELECT * FROM display_screens WHERE id = ? AND company_id = ? AND is_active = 1"
        async with self.db.execute(query, (display_id, company_id)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def check_display_usage(self, display_id: int) -> bool:
        """Checks if a display is currently in use by any station."""
        query = "SELECT COUNT(*) as count FROM stations WHERE display_id = ?"
        async with self.db.execute(query, (display_id,)) as cursor:
            row = await cursor.fetchone()
            return row["count"] > 0 if row else False

    """
    async def soft_delete_display(self, display_id: int, company_id: int) -> bool:
        if await self.check_display_usage(display_id):
            raise ValueError("Display is currently in use and cannot be deleted.")
        query = "UPDATE display_screens SET is_active = 0 WHERE id = ? AND company_id = ?"
        cursor = await self.db.execute(query, (display_id, company_id))
        await self.db.commit()
        return cursor.rowcount > 0
    """
    async def soft_delete_display(self, display_id: int, company_id: int) -> bool:
        """Soft-deletes a display screen."""
        query = "UPDATE display_screens SET is_deleted = 1 WHERE id = ? AND company_id = ?"
        cursor = await self.db.execute(query, (display_id, company_id))
        await self.db.commit()
        return cursor.rowcount > 0

    async def get_active_shift(self, company_id: int):
        """Retrieves the currently open shift for a company."""
        query = "SELECT * FROM shifts WHERE company_id = ? AND status = 'OPEN'"
        async with self.db.execute(query, (company_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def open_shift(self, company_id: int, user_id: int) -> int:
        """Opens a new working shift."""
        active = await self.get_active_shift(company_id)
        if active:
            raise ValueError("A shift is already open.")
        now = int(time.time())
        cursor = await self.db.execute(
            "INSERT INTO shifts (company_id, opened_by_user_id, opened_at, status, last_ticket_number) VALUES (?, ?, ?, 'OPEN', 0)",
            (company_id, user_id, now)
        )
        await self.db.commit()
        return cursor.lastrowid

    async def close_shift(self, shift_id: int, user_id: int) -> bool:
        """Closes an open working shift."""
        now = int(time.time())
        cursor = await self.db.execute(
            "UPDATE shifts SET status = 'CLOSED', closed_by_user_id = ?, closed_at = ? WHERE id = ? AND status = 'OPEN'",
            (user_id, now, shift_id)
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def get_next_ticket_number(self, shift_id: int) -> int:
        """Increments and returns the next ticket sequence number for a shift."""
        await self.db.execute(
            "UPDATE shifts SET last_ticket_number = last_ticket_number + 1 WHERE id = ?",
            (shift_id,)
        )
        await self.db.commit()
        async with self.db.execute("SELECT last_ticket_number FROM shifts WHERE id = ?", (shift_id,)) as cursor:
            row = await cursor.fetchone()
            return row["last_ticket_number"] if row else 1

    async def get_user_preferences(self, user_id: int) -> dict:
        """Retrieves user UI preferences."""
        cursor = self.db.cursor()
        cursor.execute(
            "SELECT per_page, font_size, font_family FROM user_preferences WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "per_page": row[0],
                "font_size": row[1],
                "font_family": row[2]
            }
        return {
            "per_page": 10,
            "font_size": "text-xs",
            "font_family": "font-sans"
        }

    async def save_user_preferences(self, user_id: int, per_page: int, font_size: str, font_family: str) -> bool:
        """Saves or updates user UI preferences."""
        cursor = self.db.cursor()
        now = int(time.time())
        cursor.execute("""
            INSERT INTO user_preferences (user_id, per_page, font_size, font_family, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                per_page = excluded.per_page,
                font_size = excluded.font_size,
                font_family = excluded.font_family,
                updated_at = excluded.updated_at
        """, (user_id, per_page, font_size, font_family, now))
        self.db.commit()
        return True