"""
Main Application Module (Zendticket Backend).
Configures the database lifecycle, CORS middleware, REST API routers,
and the real-time multi-tenant WebSocket server.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import init_db, get_db_connection
from app.repositories.db_repository import DBRepository
from app.websockets.manager import ws_manager
from app.api.auth import router as auth_router
from app.api.tickets import router as tickets_router
from app.api.admin import router as admin_router
from app.api.operator import router as operator_router
from app.core.config import PROJECT_NAME

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application lifecycle.
    Initializes SQLite database tables on server startup.
    """
    await init_db()
    yield

app = FastAPI(
    title=PROJECT_NAME,
    description="Backend API for Zendticket multi-company system",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"]
)

app.include_router(auth_router)
app.include_router(tickets_router)
app.include_router(admin_router)
app.include_router(operator_router)

@app.websocket("/ws/{company_code}")
async def websocket_endpoint(websocket: WebSocket, company_code: str, user_id: int = Query(None)):
    """
    Tenant-isolated real-time WebSocket endpoint.
    Enables instant ticket state synchronization across TV displays,
    kiosks, and operator dashboards using the company's short code.
    """
    db = await get_db_connection()
    try:
        repo = DBRepository(db)
        company = await repo.get_company_by_short_code(company_code)
        
        if not company:
            await websocket.send_text('{"error": "Company not registered"}')
            await websocket.close(code=1008)
            return
            
        company_id = company["id"]
        await ws_manager.connect(company_id=company_id, websocket=websocket, user_id=user_id)
        print(f"🟢 [WS CONNECTED] Company Code: {company_code} | User ID: {user_id}")
        
        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text('{"event": "pong"}')
        except WebSocketDisconnect:
            ws_manager.disconnect(company_id, websocket)
            print(f"🔴 [WS DISCONNECTED] Company Code: {company_code} | User ID: {user_id}")
    finally:
        await db.close()

@app.get("/health")
async def health_check():
    """Basic service health check endpoint."""
    return {"status": "ok", "service": "zenticket-backend"}