"""
API Dependencies Module.
Provides dependency injection functions for database sessions, current user authentication, and RBAC role checks.
"""

import time
import aiosqlite
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.database import get_db_connection
from app.repositories.db_repository import DBRepository
from app.services.auth_service import AuthService

security = HTTPBearer(auto_error=True)

async def get_repository() -> DBRepository:
    """Dependency injector that yields a database repository instance with an open DB connection."""
    db = await get_db_connection()
    try:
        yield DBRepository(db)
    finally:
        await db.close()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    repo: DBRepository = Depends(get_repository)
) -> dict:
    """Validates the bearer token, checks session activity in database, and returns the current user dictionary."""
    token = credentials.credentials
    payload = AuthService.decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    session_id = payload.get("session_id")
    user_id = int(payload.get("sub", 0))
    active_session = await repo.get_active_session(session_id)
    if not active_session or active_session["expires_at"] < int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or was revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await repo.get_user_by_id(user_id)
    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def require_role(required_role: str):
    """Factory dependency that restricts endpoint access to users possessing a specific role."""
    async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["role"] != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires '{required_role}' privileges"
            )
        return current_user
    return role_checker