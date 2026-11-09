"""
Authentication and Authorization Service (AuthService).
Handles password hashing, JWT token generation/verification, and user credential validation.
"""

import time
import secrets
import jwt
import bcrypt
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from app.repositories.db_repository import DBRepository

JWT_SECRET_KEY = "SUPER_SECRET_TICKETING_KEY_CHANGE_IN_PRODUCTION"
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 60 * 60 * 8  # 8 hours

class AuthService:
    """Provides methods for password cryptography, token handling, and user authentication."""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hashes a plain text password using bcrypt and a secure salt."""
        pwd_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verifies a plain text password against a stored bcrypt hash."""
        try:
            pwd_bytes = plain_password.encode('utf-8')
            hash_bytes = hashed_password.encode('utf-8')
            return bcrypt.checkpw(pwd_bytes, hash_bytes)
        except Exception:
            return False

    @staticmethod
    def create_access_token(data: dict, expires_delta_seconds: int = ACCESS_TOKEN_EXPIRE_SECONDS) -> str:
        """Generates a JSON Web Token (JWT) containing session and user claims."""
        to_encode = data.copy()
        expire = int(time.time()) + expires_delta_seconds
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    @staticmethod
    def decode_access_token(token: str) -> Optional[dict]:
        """Decodes and validates a JSON Web Token (JWT)."""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            return payload
        except (jwt.PyJWTError, Exception):
            return None

    @classmethod
    async def authenticate_user(cls, repo: DBRepository, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticates a user by username and password.
        Enforces concurrent session limits for operators and clears sessions for admins.
        """
        user = await repo.get_user_by_username(username)
        if not user:
            return None
        if not user.get("is_active", 0):
            return None
        if not cls.verify_password(password, user["password_hash"]):
            return None
            
        user_role = user.get("role")
        user_id = user["id"]
        
        if user_role == "operator":
            active_count = await repo.get_active_sessions_count(user_id)
            if active_count > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ya tienes una sesión activa en otro dispositivo. No puedes iniciar sesión simultáneamente."
                )
                
        if user_role == "admin":
            await repo.delete_active_sessions_by_user(user_id)
            
        session_id = secrets.token_hex(24)
        expires_at = int(time.time()) + ACCESS_TOKEN_EXPIRE_SECONDS
        await repo.create_active_session(session_id, user_id, user["company_id"], expires_at)
        await repo.create_audit_log(user["company_id"], user_id, "USER_LOGIN", f"User {username} logged in")
        
        token_payload = {
            "sub": str(user_id),
            "session_id": session_id,
            "username": user["username"],
            "role": user_role,
            "company_id": user["company_id"]
        }
        token = cls.create_access_token(token_payload)
        
        return {
            "token": token,
            "user": user
        }