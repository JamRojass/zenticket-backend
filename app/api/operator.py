"""
Operator API Router.
Handles operator-specific workflows including workstation sessions and station-based ticket calls.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from pydantic import BaseModel
from app.repositories.db_repository import DBRepository
from app.core.deps import get_repository, get_current_user, require_role
from app.websockets.manager import ws_manager

router = APIRouter(prefix="/operator", tags=["operators"])
logger = logging.getLogger("uvicorn.error")

class operatorSessionRequest(BaseModel):
    station_id: int

class StationOut(BaseModel):
    id: int
    company_id: int
    area_id: int
    name: str
    is_active: int

@router.get("/available-stations", response_model=List[StationOut])
async def get_operator_stations(
    current_user: dict = Depends(get_current_user),
    repo: DBRepository = Depends(get_repository)
):
    """Retrieves available unassigned active stations for the operator's department area."""
    if not current_user.get("area_id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="User has no assigned area or is an administrator"
        )
    stations = await repo.get_stations_by_area(current_user["area_id"])
    return stations

@router.post("/call_next_ticket_by_station")
async def call_next_ticket_by_station(
    payload: operatorSessionRequest,
    current_user: dict = Depends(get_current_user),
    repo: DBRepository = Depends(get_repository)
):
    """Calls the next ticket in line specifically mapped to the operator's active station."""
    station = await repo.get_station_by_id(payload.station_id)
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Station not found"
        )
    if station["area_id"] != current_user.get("area_id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Station does not belong to your assigned area"
        )
    ticket = await repo.get_next_waiting_ticket_by_area(current_user["company_id"], station["area_id"])
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="No waiting tickets in this area"
        )
    updated_ticket = await repo.update_ticket_status(
        ticket["id"], "CALLED", user_id=current_user["id"]
    )
    await ws_manager.broadcast_to_company(current_user["company_id"], {
        "event": "TICKET_CALLED",
        "data": updated_ticket
    })
    return updated_ticket

@router.post("/tickets/create_session_station")
async def create_session_station(
    payload: operatorSessionRequest,
    current_user: dict = Depends(get_current_user),
    repo: DBRepository = Depends(get_repository)
):
    """Initializes a working station session for the authenticated operator."""
    try:
        company_id = current_user.get("company_id")
        user_id = current_user.get("id")
        station_id = payload.station_id
        if not company_id or not user_id or not station_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required identification parameters"
            )
        session_id = await repo.create_station_session(
            company_id=company_id,
            station_id=station_id,
            user_id=user_id
        )
        return {
            "status": "success",
            "message": "Station session created successfully",
            "session_id": session_id
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while creating the station session: {str(e)}"
        )

@router.get("/shifts/active")
async def get_active_shift_for_device(
    company_code: str,
    repo: DBRepository = Depends(get_repository)
):
    """Checks if there is an active shift open for a company by its short code."""
    company = await repo.get_company_by_short_code(company_code)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    shift = await repo.get_active_shift(company["id"])
    return {"active_shift": shift}