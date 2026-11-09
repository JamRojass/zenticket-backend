"""
Tickets API Router.
Handles public kiosk endpoints, display boards, operator ticket lifecycle actions, and device pairing validation.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.repositories.db_repository import DBRepository
from app.core.deps import get_repository, get_current_user
from app.services.ticket_service import TicketService
from app.schemas.pydantic_models import (
    TicketCreate,
    TicketOut,
    TicketDeriveRequest,
    AreaOut,
    ScreenPairRequest
)

router = APIRouter(prefix="/tickets", tags=["Tickets"])

@router.get("/kiosk/{company_code}/areas", response_model=List[AreaOut])
async def get_kiosk_areas(company_code: str, repo: DBRepository = Depends(get_repository)):
    """Retrieves active service areas for a public kiosk by company short code."""
    company = await repo.get_company_by_short_code(company_code)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return await repo.list_areas_by_company(company["id"])

@router.post("/kiosk/{company_code}/create", response_model=TicketOut)
async def create_kiosk_ticket(
    company_code: str, 
    payload: TicketCreate, 
    repo: DBRepository = Depends(get_repository)
):
    """Generates a new ticket from a public kiosk."""
    company = await repo.get_company_by_short_code(company_code)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    service = TicketService(repo)
    return await service.create_ticket(company["id"], payload.area_id)

@router.get("/display/{company_code}/called", response_model=List[TicketOut])
async def get_display_called_tickets(
    company_code: str,
    limit: int = Query(6, ge=1, le=20),
    repo: DBRepository = Depends(get_repository)
):
    """Retrieves recently called tickets for TV display boards."""
    company = await repo.get_company_by_short_code(company_code)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return await repo.list_recent_called_tickets(company["id"], limit=limit)

@router.get("/display/{company_code}/board")
async def get_display_board(company_code: str, repo: DBRepository = Depends(get_repository)):
    """Retrieves the complete board state (currently serving and waiting tickets) for TV displays."""
    company = await repo.get_company_by_short_code(company_code)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    serving = await repo.list_recent_called_tickets(company["id"], limit=10)
    waiting = await repo.list_waiting_tickets(company["id"])
    return {
        "company_name": company["name"],
        "serving": serving,
        "waiting": waiting
    }

@router.get("/operator/active", response_model=Optional[TicketOut])
async def get_operator_active_ticket(
    current_user: dict = Depends(get_current_user),
    repo: DBRepository = Depends(get_repository)
):
    """Retrieves the active ticket currently being handled by the authenticated operator."""
    return await repo.get_active_ticket_for_user(current_user["id"])

@router.get("/operator/waiting", response_model=List[TicketOut])
async def get_waiting_tickets(
    current_user: dict = Depends(get_current_user),
    repo: DBRepository = Depends(get_repository)
):
    """Lists all waiting tickets in the company queue."""
    return await repo.list_waiting_tickets(current_user["company_id"])

@router.post("/operator/call-next", response_model=Optional[TicketOut])
async def call_next_ticket(
    area_id: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
    repo: DBRepository = Depends(get_repository)
):
    """Calls the next ticket in the queue for the operator."""
    service = TicketService(repo)
    ticket = await service.call_next_ticket(current_user["company_id"], current_user["id"], area_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="No waiting tickets in queue")
    return ticket

@router.post("/operator/{ticket_id}/complete", response_model=TicketOut)
async def complete_ticket(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
    repo: DBRepository = Depends(get_repository)
):
    """Completes an ongoing ticket being served by the operator."""
    service = TicketService(repo)
    return await service.complete_ticket(current_user["company_id"], current_user["id"], ticket_id)

@router.post("/operator/{ticket_id}/derive", response_model=TicketOut)
async def derive_ticket(
    ticket_id: int,
    payload: TicketDeriveRequest,
    current_user: dict = Depends(get_current_user),
    repo: DBRepository = Depends(get_repository)
):
    """Derives a ticket to a target service area."""
    service = TicketService(repo)
    return await service.derive_ticket(
        current_user["company_id"], current_user["id"], ticket_id, payload.target_area_id
    )

@router.post("/operator/{ticket_id}/return", response_model=TicketOut)
async def return_ticket_to_queue(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
    repo: DBRepository = Depends(get_repository)
):
    """Returns an active ticket back to the waiting queue."""
    service = TicketService(repo)
    return await service.return_ticket_to_queue(current_user["company_id"], current_user["id"], ticket_id)

@router.post("/operator/{ticket_id}/cancel", response_model=TicketOut)
async def cancel_ticket(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
    repo: DBRepository = Depends(get_repository)
):
    """Cancels a ticket."""
    service = TicketService(repo)
    return await service.cancel_ticket(current_user["company_id"], current_user["id"], ticket_id)

@router.post("/display/verify-pairing")
async def verify_screen_pairing(
    payload: ScreenPairRequest,
    repo: DBRepository = Depends(get_repository)
):
    """Validates device pairing code for displays or kiosks."""
    company = await repo.get_company_by_short_code(payload.company_code)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    screen = await repo.validate_screen_pairing(company["id"], payload.pairing_code, payload.device_type)
    if not screen:
        raise HTTPException(status_code=403, detail="Invalid, inactive or mismatched device type pairing code")
    return {"status": "paired", "company_name": company["name"]}