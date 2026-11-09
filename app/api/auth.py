"""
Authentication API Router.
Manages login endpoints, token validation, user profile fetching, and secure logout.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from app.repositories.db_repository import DBRepository
from app.core.deps import get_repository, get_current_user
from app.services.auth_service import AuthService
from app.schemas.pydantic_models import LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, repo: DBRepository = Depends(get_repository)):
    """Authenticates user credentials and returns a bearer access token."""
    result = await AuthService.authenticate_user(repo, credentials.username, credentials.password)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    return {
        "access_token": result["token"],
        "token_type": "bearer",
        "user": result["user"]
    }

@router.get("/me", response_model=UserOut)
async def me(current_user: dict = Depends(get_current_user)):
    """Returns the profile data of the currently authenticated user."""
    return current_user

@router.post("/logout")
async def logout(
    current_user: dict = Depends(get_current_user),
    repo: DBRepository = Depends(get_repository)
):
    """Terminates active sessions and station bindings for the logging-out user."""
    user_id = current_user["id"]
    user_role = current_user.get("role")
    print(user_id, user_role, "ESTAMOS EN EL ENDPOINT DE LOGOUT")
    await repo.delete_active_sessions_by_user(user_id)
    if user_role == "operator":
        print("EL USUARIO ES operator")
        await repo.close_station_sessions_by_user(user_id)
    await repo.create_audit_log(current_user["company_id"], user_id, "USER_LOGOUT", f"User {current_user['username']} logged out")
    print("LOGOUT EJECUTADO SATISFACTORIAMENTE")
    return {"message": "Successfully logged out"}