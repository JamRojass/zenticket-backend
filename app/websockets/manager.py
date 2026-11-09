"""
WebSocket Connection Manager.
Administer active in-memory sessions for connected clients (TV Displays,
Kiosks, and Operators) and facilitates real-time event broadcasting.
"""

import json
from typing import Dict, List, Tuple
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Central controller for concurrent socket management and event broadcasting."""
    
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.display_connections: Dict[int, Tuple[int, WebSocket]] = {}
        self.operator_connections: Dict[int, Tuple[int, WebSocket]] = {}

    async def connect(self, company_id: int, websocket: WebSocket, display_id: int = None, user_id: int = None) -> None:
        """Accepts and registers a new WebSocket connection associated with a company and role."""
        await websocket.accept()
        if company_id not in self.active_connections:
            self.active_connections[company_id] = []
        self.active_connections[company_id].append(websocket)
        
        if display_id is not None:
            self.display_connections[display_id] = (company_id, websocket)
        if user_id is not None:
            self.operator_connections[user_id] = (company_id, websocket)

    def disconnect(self, company_id: int, websocket: WebSocket) -> None:
        """Removes a WebSocket connection from active records upon client disconnection."""
        if company_id in self.active_connections:
            if websocket in self.active_connections[company_id]:
                self.active_connections[company_id].remove(websocket)
            if not self.active_connections[company_id]:
                del self.active_connections[company_id]
                
        display_to_remove = [d_id for d_id, (c_id, ws) in self.display_connections.items() if ws == websocket]
        for d_id in display_to_remove:
            del self.display_connections[d_id]
            
        user_to_remove = [u_id for u_id, (c_id, ws) in self.operator_connections.items() if ws == websocket]
        for u_id in user_to_remove:
            del self.operator_connections[u_id]

    async def broadcast_to_company(self, company_id: int, message: dict) -> None:
        """Broadcasts a JSON message in real-time to all screens and operators connected to a company."""
        if company_id not in self.active_connections:
            return
        payload = json.dumps(message)
        dead_sockets: List[WebSocket] = []
        
        for socket in self.active_connections[company_id]:
            try:
                await socket.send_text(payload)
            except Exception:
                dead_sockets.append(socket)
                
        for dead in dead_sockets:
            self.disconnect(company_id, dead)

    async def force_disconnect_display(self, display_id: int, pairing_code: str = None) -> bool:
        """Forces remote disconnection of a specific display screen or kiosk."""
        if display_id in self.display_connections:
            company_id, websocket = self.display_connections[display_id]
            try:
                await websocket.send_json({
                    "action": "FORCE_LOGOUT",
                    "pairing_code": pairing_code,
                    "reason": "This device has been disconnected by the administrator."
                })
                await websocket.close()
            except Exception:
                pass
            finally:
                self.disconnect(company_id, websocket)
            return True
        return False

    async def force_disconnect_user(self, user_id: int) -> bool:
        """Forces session closure and WebSocket disconnection for an operator user."""
        if user_id not in self.operator_connections:
            return False
        company_id, websocket = self.operator_connections[user_id]
        try:
            await websocket.send_json({
                "action": "FORCE_LOGOUT",
                "reason": "Your account has been disconnected or deactivated by the administrator."
            })
            await websocket.close()
        except Exception:
            pass
        finally:
            self.disconnect(company_id, websocket)
        return True

ws_manager = ConnectionManager()