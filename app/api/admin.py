"""
Administration API Router.
Handles enterprise administration including companies, staff accounts, service areas,
hardware stations, shifts, display pairing, audit trails, and reporting metrics.
"""

import logging
import random
import string
import secrets
import csv
import io
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Response
from app.repositories.db_repository import DBRepository
from app.core.deps import get_repository, get_current_user, require_role
from app.services.auth_service import AuthService
from app.schemas.pydantic_models import (
    CompanyCreate,
    CompanyOut,
    RegisterCompanyRequest,
    UpdateProfileRequest,
    UpdateUsernameRequest,
    UserCreate,
    UserOut,
    AreaCreate,
    AreaOut,
    AuditLogOut,
    MetricsSummaryOut,
    TicketOut,
    ScreenPairRequest,
    DisplayScreenOut,
    DisplayScreenCreate,
    StationCreate,
    StationUpdate,
    StationOut,
    UserUpdate,
    UserPreferencesUpdate,
    UserPreferencesOut  
)
from app.websockets.manager import ws_manager
from fastapi.responses import StreamingResponse
from datetime import datetime

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/admin", tags=["Administration"])

@router.post("/setup/company", response_model=CompanyOut)
async def setup_company(payload: CompanyCreate, repo: DBRepository = Depends(get_repository)):
    """Registers a new company tenant with a unique short code."""
    existing = await repo.get_company_by_short_code(payload.short_code)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Company short code '{payload.short_code}' is already registered"
        )
    company = await repo.create_company(payload.name, payload.short_code)
    await repo.create_audit_log(
        company["id"], None, "COMPANY_CREATED", f"Company {payload.name} ({payload.short_code}) registered"
    )
    return company

@router.post("/register", response_model=dict)
async def register_company_and_admin(payload: RegisterCompanyRequest, repo: DBRepository = Depends(get_repository)):
    """Registers a new company along with its primary administrator account."""
    short_code = None
    for _ in range(50):
        candidate = "".join(random.choices(string.ascii_uppercase, k=2))
        existing_candidate = await repo.get_company_by_short_code(candidate)
        if not existing_candidate:
            short_code = candidate
            break
    if not short_code:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate a unique short code"
        )
    existing_user = await repo.get_user_by_username(payload.admin_username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username '{payload.admin_username}' is already taken"
        )
    company = await repo.create_company(payload.company_name, short_code)
    password_hash = AuthService.hash_password(payload.admin_password)
    user = await repo.create_user(
        company_id=company["id"], 
        username=payload.admin_username, 
        password_hash=password_hash, 
        role="admin", 
        fullname="Main Administrator", 
        area_id=None
    )
    await repo.create_audit_log(
        company["id"], user["id"], "COMPANY_REGISTERED", f"Company {company['name']} and admin {user['username']} created"
    )
    return {
        "message": "Company and administrator created successfully",
        "company": company,
        "admin": user
    }

@router.post("/setup/user", response_model=UserOut)
async def setup_user(payload: UserCreate, repo: DBRepository = Depends(get_repository)):
    """Sets up an initial operator staff member associated with an area."""
    company = await repo.get_company_by_id(payload.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company does not exist")
    existing_user = await repo.get_user_by_username(payload.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username '{payload.username}' is already taken"
        )
    assigned_role = 'operator'
    if not payload.area_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Staff operators must be assigned to a department area"
        )
    password_hash = AuthService.hash_password(payload.password)
    user = await repo.create_user(
        company_id=payload.company_id,
        username=payload.username,
        password_hash=password_hash,
        role=assigned_role,
        fullname=payload.fullname or "Staff Member",
        area_id=payload.area_id
    )
    await repo.create_audit_log(
        payload.company_id, user["id"], "USER_CREATED", f"Staff account '{payload.username}' created as operator"
    )
    return user

@router.post("/users", response_model=UserOut)
async def create_user_endpoint(
    payload: UserCreate, 
    admin_user: dict = Depends(require_role("admin")), 
    repo: DBRepository = Depends(get_repository)
):
    """Creates a new operator user account under the administrator's company."""
    company_id = admin_user["company_id"]
    if payload.role != "operator":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 'operator' accounts can be created through this staff interface."
        )
    if not payload.area_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Operators must be assigned to a department area"
        )
    existing_user = await repo.get_user_by_username(payload.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username '{payload.username}' is already taken"
        )
    password_hash = AuthService.hash_password(payload.password)
    user = await repo.create_user(
        company_id=company_id,
        username=payload.username,
        password_hash=password_hash,
        role="operator",
        fullname=payload.fullname or "Staff Member",
        area_id=payload.area_id
    )
    await repo.create_audit_log(
        company_id, user["id"], "USER_CREATED", f"Staff account '{payload.username}' created"
    )
    return user

@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Updates staff user details such as full name or area assignment."""
    updated = await repo.update_user_details(user_id, admin_user["company_id"], payload.fullname, payload.area_id)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    await repo.create_audit_log(
        admin_user["company_id"], admin_user["id"], "USER_UPDATED", 
        f"Staff user ID #{user_id} details updated"
    )
    return updated

@router.put("/users/{user_id}/password")
async def update_user_password(
    user_id: int,
    payload: dict,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Updates the login password of a specific staff user."""
    new_password = payload.get("password")
    if not new_password:
        raise HTTPException(status_code=400, detail="Password is required")
    hashed_password = AuthService.hash_password(new_password)
    updated = await repo.update_user_password_hashed(user_id, admin_user["company_id"], hashed_password)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    await repo.create_audit_log(
        admin_user["company_id"], admin_user["id"], "PASSWORD_CHANGED", 
        f"Password changed for staff user ID #{user_id}"
    )
    return {"message": "Password updated successfully"}

@router.post("/users/{user_id}/disconnect")
async def disconnect_staff_user(
    user_id: int,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Forces immediate session termination and WebSocket disconnection for a staff user."""
    user = await repo.get_user_by_id(user_id)
    if not user or user["company_id"] != admin_user["company_id"]:
        raise HTTPException(status_code=404, detail="User not found")
    if user["role"] == "admin":
        raise HTTPException(status_code=400, detail="Cannot force disconnect an administrator account.")
    await repo.delete_active_sessions_by_user(user_id)
    await repo.close_station_sessions_by_user(user_id)
    await repo.handle_operator_orphan_tickets(user_id)
    await ws_manager.force_disconnect_user(user_id)
    await repo.create_audit_log(
        admin_user["company_id"], admin_user["id"], "USER_DISCONNECTED",
        f"Staff user '{user['username']}' was forcefully disconnected and station released."
    )
    return {"message": f"Staff user {user['username']} disconnected successfully"}

@router.delete("/users/{user_id}")
async def delete_staff_user(
    user_id: int,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Performs a soft deletion on a staff user account."""
    try:
        success = await repo.soft_delete_user(user_id, admin_user["company_id"])
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        await ws_manager.force_disconnect_user(user_id)
        await repo.create_audit_log(
            admin_user["company_id"], admin_user["id"], "USER_DELETED",
            f"Staff user ID #{user_id} soft-deleted successfully."
        )
        return {"message": "Staff user soft-deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/companies", response_model=List[CompanyOut])
async def list_companies(
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Lists all registered active companies."""
    return await repo.list_companies()

@router.get("/users")
async def list_company_users(
    limit: int = 100,
    offset: int = 0,
    area_id: int | None = None,
    username: str | None = None,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Lists users belonging to the administrator's company with optional filters."""
    company_id = admin_user["company_id"]
    users = await repo.list_users_by_company(
        company_id, 
        limit=limit, 
        offset=offset,
        area_id=area_id,
        username=username
    )
    total = await repo.count_users_by_company(
        company_id,
        area_id=area_id,
        username=username
    )
    return {
        "users": users,
        "total": total
    }

@router.post("/stations", response_model=StationOut)
async def create_station(
    payload: StationCreate,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Creates a new attention station."""
    try:
        company_id = admin_user.get("company_id")
        area_id = payload.area_id
        name = payload.name
        if not company_id or not area_id or not name:
            raise HTTPException(status_code=422, detail="Missing required fields")
        station = await repo.create_station(
            company_id=int(company_id), 
            area_id=int(area_id), 
            name=str(name).strip()
        )
        return station
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

@router.put("/stations/{station_id}", response_model=StationOut)
async def update_station(
    station_id: int,
    payload: StationUpdate,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Updates an existing attention station record."""
    company_id = admin_user["company_id"]
    existing = await repo.get_station_by_id(station_id)
    if not existing or existing.get("company_id") != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Station not found or unauthorized"
        )

    updated = await repo.update_station(
        station_id=station_id,
        company_id=company_id,
        name=payload.name,
        area_id=payload.area_id
    )
    await repo.create_audit_log(
        company_id, admin_user["id"], "STATION_UPDATED", f"Station ID {station_id} updated"
    )
    return updated

@router.get("/stations")
async def list_company_stations(
    response: Response,
    limit: int = 100,
    offset: int = 0,
    area_id: int | None = None,
    name: str | None = None,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Lists company stations with pagination and filtering."""
    stations = await repo.get_stations_by_company(
        admin_user["company_id"], 
        limit=limit, 
        offset=offset,
        area_id=area_id,
        name=name
    )
    total = await repo.count_stations_by_company(
        admin_user["company_id"],
        area_id=area_id,
        name=name
    )
    response.headers["X-Total-Count"] = str(total)
    return stations

@router.delete("/stations/{station_id}")
async def delete_station(
    station_id: int,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Logically deactivates a station if not currently in use."""
    company_id = admin_user["company_id"]
    station = await repo.get_station_by_id(station_id)
    if not station or station["company_id"] != company_id or not station["is_active"]:
        raise HTTPException(status_code=404, detail="Station not found")
    active_sessions_count = await repo.count_active_sessions_by_station(station_id)
    if active_sessions_count > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete station because it is currently in use by an active operator session."
        )
    success = await repo.delete_station(station_id, company_id)
    if not success:
        raise HTTPException(status_code=404, detail="Station not found")
    await repo.create_audit_log(
        company_id, admin_user["id"], "STATION_DELETED", 
        f"Station ID #{station_id} logically deactivated"
    )
    return {"message": "Station deactivated successfully"}

@router.post("/areas", response_model=AreaOut)
async def create_area(
    payload: AreaCreate,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Creates a new service department area."""
    existing_areas = await repo.list_areas(admin_user["company_id"])
    if len(existing_areas) >= 3:
        raise HTTPException(
            status_code=400, 
            detail="Limit reached: Maximum of 3 service areas allowed."
        )
    area = await repo.create_area(admin_user["company_id"], payload.name, payload.short_code)
    await repo.create_audit_log(
        admin_user["company_id"], admin_user["id"], "AREA_CREATED", 
        f"Service area '{payload.name}' created with prefix {payload.short_code}"
    )
    return area

@router.put("/areas/{area_id}", response_model=AreaOut)
async def update_area(
    area_id: int,
    payload: AreaCreate,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Updates an existing service area."""
    updated = await repo.update_area(area_id, admin_user["company_id"], payload.name, payload.short_code)
    if not updated:
        raise HTTPException(status_code=404, detail="Area not found")
    return updated

@router.get("/areas", response_model=List[AreaOut])
async def list_areas(
    current_user: dict = Depends(get_current_user),
    repo: DBRepository = Depends(get_repository)
):
    """Lists all active service areas for the company."""
    return await repo.list_areas_by_company(current_user["company_id"])

@router.delete("/areas/{area_id}")
async def delete_area(
    area_id: int,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Logically deactivates a service area."""
    company_id = admin_user["company_id"]
    area = await repo.get_area_by_id(area_id)
    if not area or area["company_id"] != company_id or not area["is_active"]:
        raise HTTPException(status_code=404, detail="Area not found")
    active_sessions_count = await repo.count_active_station_sessions_by_area(area_id)
    if active_sessions_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete area because it contains stations with active working sessions."
        )
    success = await repo.delete_area(area_id, company_id)
    if not success:
        raise HTTPException(status_code=404, detail="Area not found")
    await repo.create_audit_log(
        company_id, admin_user["id"], "AREA_DELETED", 
        f"Service area ID #{area_id} logically deactivated"
    )
    return {"message": "Area deactivated successfully"}

@router.get("/metrics", response_model=MetricsSummaryOut)
async def get_metrics(
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Retrieves operational metrics summary for the company."""
    return await repo.get_metrics_summary(admin_user["company_id"])

@router.get("/audit", response_model=List[AuditLogOut])
async def get_audit_trail(
    response: Response,
    limit: int = 100,
    offset: int = 0,
    start_date: int | None = None,
    end_date: int | None = None,
    user_id: int | None = None,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Retrieves audit logs with pagination and filtering."""
    company_id = admin_user["company_id"]
    logs = await repo.list_audit_logs(
        company_id, 
        limit=limit, 
        offset=offset,
        start_date=start_date, 
        end_date=end_date, 
        user_id=user_id
    )
    total = await repo.count_audit_logs(
        company_id,
        start_date=start_date,
        end_date=end_date,
        user_id=user_id
    )
    response.headers["X-Total-Count"] = str(total)
    return logs

@router.get("/audit/export-csv")
async def export_audit_csv(
    start_date: int | None = None,
    end_date: int | None = None,
    user_id: int | None = None,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Exports audit logs as a downloadable CSV report file."""
    company_id = admin_user["company_id"]
    logs = await repo.list_audit_logs(
        company_id, 
        limit=1000000, 
        offset=0,
        start_date=start_date, 
        end_date=end_date, 
        user_id=user_id
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Username", "Action", "Details", "Timestamp"])
    for log in logs:
        timestamp_str = ""
        ts = log.get("created_at") or log.get("timestamp")
        if ts:
            try:
                timestamp_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                timestamp_str = str(ts)
        writer.writerow([
            log.get("id"),
            log.get("username") or "System / Unknown",
            log.get("action"),
            log.get("details") or log.get("description") or "N/A",
            timestamp_str
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs_report.csv"}
    )

@router.get("/tickets/history", response_model=List[TicketOut])
async def get_tickets_history(
    response: Response,
    limit: int = 100,
    offset: int = 0,
    area_id: int | None = None,
    status: str | None = None,
    start_date: int | None = None,
    end_date: int | None = None,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Retrieves historical ticket records with filters and pagination."""
    tickets = await repo.list_tickets_history(
        admin_user["company_id"], 
        limit=limit, 
        offset=offset,
        area_id=area_id,
        status=status,
        start_date=start_date,
        end_date=end_date
    )
    total = await repo.count_tickets_history(
        admin_user["company_id"],
        area_id=area_id,
        status=status,
        start_date=start_date,
        end_date=end_date
    )
    response.headers["X-Total-Count"] = str(total)
    return tickets

@router.get("/tickets/export-csv")
async def export_tickets_csv(
    area_id: int | None = None,
    status: str | None = None,
    start_date: int | None = None,
    end_date: int | None = None,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Exports ticket history records as a downloadable CSV file."""
    tickets = await repo.list_tickets_history(
        admin_user["company_id"], 
        limit=1000000, 
        offset=0,
        area_id=area_id,
        status=status,
        start_date=start_date,
        end_date=end_date
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Ticket Code", "Area", "Assigned User", "Status", "Created At"])
    for t in tickets:
        created_str = ""
        if t.get("created_at"):
            created_str = datetime.fromtimestamp(t["created_at"]).strftime('%Y-%m-%d %H:%M:%S')
        writer.writerow([
            t.get("id"),
            t.get("ticket_code"),
            t.get("area_name") or "General",
            t.get("assigned_username") or "Unassigned",
            t.get("status"),
            created_str
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tickets_history_report.csv"}
    )

@router.put("/profile", response_model=UserOut)
async def update_admin_profile(
    payload: UpdateProfileRequest,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Updates the administrator user profile credentials."""
    new_username = payload.username
    password_hash = None
    if new_username and new_username != admin_user["username"]:
        existing = await repo.get_user_by_username(new_username)
        if existing and existing["id"] != admin_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Username '{new_username}' is already in use"
            )
    if payload.new_password:
        password_hash = AuthService.hash_password(payload.new_password)
    updated_user = await repo.update_user_profile(
        admin_user["id"],
        username=new_username,
        password_hash=password_hash
    )
    await repo.create_audit_log(
        admin_user["company_id"],
        admin_user["id"],
        "PROFILE_UPDATED",
        f"Admin profile updated for user {admin_user['username']}"
    )
    return updated_user

@router.get("/displays")
async def list_company_displays(
    response: Response,
    limit: int = 100,
    offset: int = 0,
    name: str | None = None,
    type: str | None = None,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Lists display screens and kiosks paired with the company."""
    displays = await repo.list_display_screens(
        admin_user["company_id"], 
        limit=limit, 
        offset=offset, 
        name=name, 
        device_type=type
    )
    total = await repo.count_display_screens(
        admin_user["company_id"],
        name=name,
        device_type=type
    )
    response.headers["X-Total-Count"] = str(total)
    return displays

@router.post("/displays", response_model=DisplayScreenOut)
async def create_display(
    payload: DisplayScreenCreate,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Creates a new display screen or kiosk pairing record."""
    code = f"{random.randint(0, 999999):06d}"
    screen = await repo.create_display_screen(admin_user["company_id"], payload.name, code, device_type=payload.type)
    await repo.create_audit_log(
        admin_user["company_id"], admin_user["id"], "SCREEN_CREATED", 
        f"Display screen '{payload.name}' created with code {code}"
    )
    return screen

@router.put("/displays/{display_id}", response_model=DisplayScreenOut)
async def update_display(
    display_id: int,
    payload: DisplayScreenCreate,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Updates an existing display screen or kiosk record."""
    try:
        company_id = admin_user.get("company_id")
        if not payload.name or not payload.name.strip():
            raise HTTPException(status_code=422, detail="Device name cannot be empty")
        screen = await repo.update_display_screen(
            display_id=int(display_id),
            company_id=int(company_id),
            name=payload.name.strip(),
            device_type=payload.type
        )
        if not screen:
            raise HTTPException(status_code=404, detail="Display screen not found")
        await repo.create_audit_log(
            company_id, admin_user["id"], "SCREEN_UPDATED", 
            f"Display screen ID {display_id} updated to '{payload.name}' ({payload.type})"
        )
        return screen
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"🔥 Critical exception updating display ID {display_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=422, detail=str(e))

@router.put("/displays/{screen_id}/toggle", response_model=DisplayScreenOut)
async def toggle_display(
    screen_id: int,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Toggles the active/inactive status of a display screen."""
    screens = await repo.list_display_screens(admin_user["company_id"])
    target = next((s for s in screens if s["id"] == screen_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Screen not found")
    new_status = 0 if target["is_active"] == 1 else 1
    updated = await repo.update_display_screen_status(screen_id, admin_user["company_id"], new_status)
    return updated

@router.post("/displays/{display_id}/regenerate-code")
async def regenerate_display_code(
    display_id: int,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Regenerates the 6-digit connection pairing code for a display device."""
    new_code = f"{random.randint(0, 999999):06d}"
    success = await repo.regenerate_display_code(display_id, admin_user["company_id"], new_code)
    if not success:
        raise HTTPException(status_code=404, detail="Display not found.")
    await repo.create_audit_log(
        admin_user["company_id"], admin_user["id"], "DISPLAY_CODE_REGENERATED",
        f"Connection code regenerated for display ID #{display_id}"
    )
    return {"message": "Connection code regenerated successfully", "new_connection_code": new_code}

@router.post("/displays/{display_id}/disconnect")
async def disconnect_display(
    display_id: int,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Forces immediate remote logout and disconnection of a display device."""
    display = await repo.get_display_by_id(display_id, admin_user["company_id"])
    if not display:
        raise HTTPException(status_code=404, detail="Display not found.")
    await ws_manager.broadcast_to_company(
        admin_user["company_id"],
        {
            "action": "FORCE_LOGOUT",
            "pairing_code": display.get("pairing_code"),
            "reason": "This device has been disconnected by the administrator."
        }
    )
    await repo.create_audit_log(
        admin_user["company_id"], admin_user["id"], "DISPLAY_DISCONNECTED",
        f"Display ID #{display_id} forcefully disconnected by admin"
    )
    return {"message": "Display disconnected and logged out successfully."}

@router.delete("/displays/{display_id}")
async def delete_display(
    display_id: int,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Soft-deletes a display screen and forces its disconnection."""
    try:
        await repo.soft_delete_display(display_id, admin_user["company_id"])
        await ws_manager.force_disconnect_display(display_id)
        await repo.create_audit_log(
            admin_user["company_id"], admin_user["id"], "DISPLAY_DELETED",
            f"Display ID #{display_id} soft-deleted by admin"
        )
        return {"message": "Display deleted successfully."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/shifts/active")
async def get_active_shift(
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Retrieves the current active shift status for the company."""
    shift = await repo.get_active_shift(admin_user["company_id"])
    return {"active_shift": shift}

@router.post("/shifts/open")
async def open_shift(
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Opens a new working shift for ticket generation and processing."""
    try:
        shift_id = await repo.open_shift(admin_user["company_id"], admin_user["id"])
        await repo.create_audit_log(
            admin_user["company_id"], admin_user["id"], "SHIFT_OPENED",
            f"Shift ID #{shift_id} opened by admin"
        )
        await ws_manager.broadcast_to_company(
            admin_user["company_id"],
            {"action": "SHIFT_OPENED", "shift_id": shift_id}
        )
        return {"message": "Shift opened successfully", "shift_id": shift_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/shifts/close")
async def close_shift(
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Closes the currently active shift."""
    active_shift = await repo.get_active_shift(admin_user["company_id"])
    if not active_shift:
        raise HTTPException(status_code=400, detail="No active shift to close.")
    success = await repo.close_shift(active_shift["id"], admin_user["id"])
    if not success:
        raise HTTPException(status_code=400, detail="Failed to close shift.")
    await repo.create_audit_log(
        admin_user["company_id"], admin_user["id"], "SHIFT_CLOSED",
        f"Shift ID #{active_shift['id']} closed by admin"
    )
    await ws_manager.broadcast_to_company(
            admin_user["company_id"],
            {"action": "SHIFT_CLOSED", "shift_id": active_shift['id'] }
        )
    return {"message": "Shift closed successfully"}

@router.get("/preferences", response_model=UserPreferencesOut)
async def get_preferences(
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Retrieves UI user preferences for the admin user."""
    try:
        prefs = repo.get_user_preferences(admin_user["id"])
        return prefs
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/preferences")
async def update_preferences(
    payload: UserPreferencesUpdate,
    admin_user: dict = Depends(require_role("admin")),
    repo: DBRepository = Depends(get_repository)
):
    """Updates UI user preferences for the admin user."""
    try:
        repo.save_user_preferences(
            admin_user["id"],
            payload.per_page,
            payload.font_size,
            payload.font_family
        )
        return {"message": "Preferences updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))