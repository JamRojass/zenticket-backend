"""
Database Core Module.
Handles SQLite database file pathing, schema definition, table creation, and connection configuration.
"""

import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "database.sqlite")

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    short_code TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    username TEXT NOT NULL UNIQUE,
    fullname TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'operator')),
    area_id INTEGER NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    token_version INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
    FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    short_code TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS stations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    area_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
    FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS station_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    station_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    started_at INTEGER NOT NULL,
    ended_at INTEGER NULL,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
    FOREIGN KEY (station_id) REFERENCES stations(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    area_id INTEGER NOT NULL,
    ticket_code TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('WAITING', 'CALLED', 'COMPLETED', 'DERIVED', 'CANCELLED')),
    assigned_user_id INTEGER,
    created_at INTEGER NOT NULL,
    called_at INTEGER,
    completed_at INTEGER,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
    FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE CASCADE,
    FOREIGN KEY (assigned_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS ticket_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    previous_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    user_id INTEGER,
    area_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    opened_by_user_id INTEGER NOT NULL,
    closed_by_user_id INTEGER NULL,
    opened_at INTEGER NOT NULL,
    closed_at INTEGER NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    last_ticket_number INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
    FOREIGN KEY (opened_by_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (closed_by_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS active_sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    company_id INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS display_screens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'tv',
    pairing_code TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    deleted_at INTEGER NULL,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    per_page INTEGER NOT NULL DEFAULT 10,
    font_size TEXT NOT NULL DEFAULT 'text-xs',
    font_family TEXT NOT NULL DEFAULT 'font-sans',
    updated_at INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_users_company ON users(company_id);
CREATE INDEX IF NOT EXISTS idx_users_area ON users(area_id);
CREATE INDEX IF NOT EXISTS idx_areas_company ON areas(company_id);
CREATE INDEX IF NOT EXISTS idx_stations_company ON stations(company_id);
CREATE INDEX IF NOT EXISTS idx_stations_area ON stations(area_id);
CREATE INDEX IF NOT EXISTS idx_tickets_company ON tickets(company_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(company_id, status);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON active_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_company ON audit_logs(company_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_company_user_date ON audit_logs(company_id, user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_displays_company ON display_screens(company_id);
CREATE INDEX IF NOT EXISTS idx_station_sessions_company ON station_sessions(company_id);
CREATE INDEX IF NOT EXISTS idx_station_sessions_station ON station_sessions(station_id, is_active);
CREATE INDEX IF NOT EXISTS idx_station_sessions_user ON station_sessions(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_shifts_company_status ON shifts(company_id, status);
CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences(user_id);

CREATE INDEX IF NOT EXISTS idx_ticket_logs_ticket_id ON ticket_logs(ticket_id);
CREATE INDEX IF NOT EXISTS idx_ticket_logs_user_id ON ticket_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_ticket_logs_area_id ON ticket_logs(area_id);
CREATE INDEX IF NOT EXISTS idx_ticket_logs_created_at ON ticket_logs(created_at);
"""

async def get_db_connection() -> aiosqlite.Connection:
    """Creates and returns an active aiosqlite database connection with row factory enabled."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON;")
    return db

async def init_db() -> None:
    """Initializes the database schema by executing the creation script."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON;")
        await db.executescript(SCHEMA_SQL)
        await db.commit()