"""
Ticket Management Service (TicketService).
Encapsulates business logic for ticket creation, calling, derivation,
completion, and returning to queue, integrating cache and WebSockets.
"""

from typing import Dict, Any, Optional, List
from fastapi import HTTPException
from app.repositories.db_repository import DBRepository
from app.core.cache import cache
from app.websockets.manager import ws_manager

class TicketService:
    """Implements operational rules for the ticket attention workflow."""
    
    def __init__(self, repo: DBRepository):
        self.repo = repo

    async def create_ticket(self, company_id: int, area_id: int) -> Dict[str, Any]:
        """Creates a new ticket in WAITING status for a specific area, validating active shifts."""
        active_shift = await self.repo.get_active_shift(company_id)
        if not active_shift:
            raise HTTPException(
                status_code=400,
                detail="Cannot generate tickets: No active shift is currently open in the system."
            )
            
        area = await self.repo.get_area_by_id(area_id)
        if not area or area["company_id"] != company_id or not area["is_active"]:
            raise HTTPException(status_code=404, detail="Service area not found or inactive")
            
        area_code = area["short_code"].upper()
        max_num = await self.repo.get_max_ticket_number_for_area(company_id, area_code)
        await cache.set(f"seq:{company_id}:{area_code}", max_num)
        seq = await cache.get_next_sequence(company_id, area_code)
        ticket_code = f"{area_code}-{seq:02d}"
        
        ticket = await self.repo.create_ticket(company_id, area_id, ticket_code)
        await self.repo.create_audit_log(
            company_id, None, "TICKET_CREATED", f"Ticket {ticket_code} created for area {area['name']}"
        )
        
        await ws_manager.broadcast_to_company(company_id, {
            "event": "TICKET_CREATED",
            "data": ticket
        })
        return ticket

    async def call_next_ticket(self, company_id: int, user_id: int, area_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Calls the next waiting ticket to be served by an operator."""
        active_ticket = await self.repo.get_active_ticket_for_user(user_id)
        if active_ticket:
            raise HTTPException(
                status_code=400,
                detail=f"Operator already has an active ticket in progress: {active_ticket['ticket_code']}"
            )
            
        next_ticket = await self.repo.get_next_waiting_ticket(company_id, area_id)
        if not next_ticket:
            return None
            
        updated_ticket = await self.repo.update_ticket_status(next_ticket["id"], "CALLED", user_id=user_id)
        await self.repo.create_audit_log(
            company_id, user_id, "TICKET_CALLED", f"Ticket {updated_ticket['ticket_code']} called by operator ID {user_id}"
        )
        
        await ws_manager.broadcast_to_company(company_id, {
            "event": "TICKET_CALLED",
            "data": updated_ticket
        })
        return updated_ticket

    async def complete_ticket(self, company_id: int, user_id: int, ticket_id: int) -> Dict[str, Any]:
        """Marks an ongoing ticket as successfully completed."""
        ticket = await self.repo.get_ticket_by_id(ticket_id)
        if not ticket or ticket["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if ticket["status"] != "CALLED" or ticket["assigned_user_id"] != user_id:
            raise HTTPException(status_code=400, detail="Ticket is not currently being served by this user")
            
        completed_ticket = await self.repo.update_ticket_status(ticket_id, "COMPLETED")
        await self.repo.create_audit_log(
            company_id, user_id, "TICKET_COMPLETED", f"Ticket {ticket['ticket_code']} completed"
        )
        
        await ws_manager.broadcast_to_company(company_id, {
            "event": "TICKET_COMPLETED",
            "data": completed_ticket
        })
        return completed_ticket

    async def derive_ticket(self, company_id: int, user_id: int, ticket_id: int, target_area_id: int) -> Dict[str, Any]:
        """Derives a ticket to a different target service area."""
        ticket = await self.repo.get_ticket_by_id(ticket_id)
        if not ticket or ticket["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Ticket not found")
            
        target_area = await self.repo.get_area_by_id(target_area_id)
        if not target_area or target_area["company_id"] != company_id or not target_area["is_active"]:
            raise HTTPException(status_code=404, detail="Target area not found or inactive")
            
        await self.repo.create_audit_log(
            company_id, user_id, "TICKET_DERIVED",
            f"Ticket {ticket['ticket_code']} derived to area {target_area['name']}"
        )
        derived_ticket = await self.repo.derive_ticket(ticket_id, target_area_id)
        
        await ws_manager.broadcast_to_company(company_id, {
            "event": "TICKET_DERIVED",
            "data": derived_ticket
        })
        return derived_ticket

    async def return_ticket_to_queue(self, company_id: int, user_id: int, ticket_id: int) -> Dict[str, Any]:
        """Returns an active ticket back to the waiting queue."""
        ticket = await self.repo.get_ticket_by_id(ticket_id)
        if not ticket or ticket["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Ticket not found")
            
        updated_ticket = await self.repo.update_ticket_status(ticket_id, "WAITING", user_id=user_id)
        await self.repo.create_audit_log(
            company_id, user_id, "TICKET_RETURNED", f"Ticket {ticket['ticket_code']} returned to queue"
        )
        
        await ws_manager.broadcast_to_company(company_id, {
            "event": "TICKET_RETURNED",
            "data": updated_ticket
        })
        return updated_ticket

    async def cancel_ticket(self, company_id: int, user_id: int, ticket_id: int) -> Dict[str, Any]:
        """Cancels an active or waiting ticket."""
        ticket = await self.repo.get_ticket_by_id(ticket_id)
        if not ticket or ticket["company_id"] != company_id:
            raise HTTPException(status_code=404, detail="Ticket not found")
            
        cancelled_ticket = await self.repo.update_ticket_status(ticket_id, "CANCELLED")
        await self.repo.create_audit_log(
            company_id, user_id, "TICKET_CANCELLED", f"Ticket {ticket['ticket_code']} cancelled"
        )
        
        await ws_manager.broadcast_to_company(company_id, {
            "event": "TICKET_CANCELLED",
            "data": cancelled_ticket
        })
        return cancelled_ticket