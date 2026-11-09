Zendticket Backend

Project Overview

Zendticket is a multi-company queue and ticket management system built with FastAPI (Python) and SQLite (using aiosqlite for asynchronous operations). It provides real-time event synchronization through WebSockets, allowing seamless management of service areas, attention stations, operators, kiosks, and TV display boards across multiple tenants (companies).

Key architectural features include:

Multi-tenancy Isolation: Secured and segmented by company short codes.

Real-time WebSockets: Instant broadcasting of ticket events (TICKET_CREATED, TICKET_CALLED, TICKET_COMPLETED, TICKET_DERIVED, TICKET_RETURNED, SHIFT_OPENED, SHIFT_CLOSED).

Role-Based Access Control (RBAC): Strict privileges separating system administrators from department operators using JSON Web Tokens (JWT).

Audit Trails & Metrics: Comprehensive logging of system actions and real-time operational metrics calculation.

Project Structure

ticketing-backend/
├── .env
├── database.sqlite
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── admin.py
│   │   ├── auth.py
│   │   ├── operator.py
│   │   └── tickets.py
│   ├── core/
│   │   ├── cache.py
│   │   ├── config.py
│   │   ├── database.py
│   │   └── deps.py
│   ├── repositories/
│   │   └── db_repository.py
│   ├── schemas/
│   │   └── pydantic_models.py
│   ├── services/
│   │   ├── auth_service.py
│   │   └── ticket_service.py
│   └── websockets/
│       └── manager.py


Deployment & Local Setup Guide

Prerequisites

Python 3.10+ installed on your system.

pip package manager.

Step 1: Clone or Open the Project Directory

Navigate to the root directory of your backend project:

cd ticketing-backend


Step 2: Create and Activate a Virtual Environment

python -m venv venv

# On Windows (Command Prompt / PowerShell):
venv\Scripts\activate

# On macOS / Linux:
source venv/bin/activate


Step 3: Install Dependencies

Install the required packages using pip (FastAPI, Uvicorn, aiosqlite, PyJWT, bcrypt, python-dotenv, pydantic):

pip install fastapi uvicorn aiosqlite pyjwt bcrypt python-dotenv pydantic


Step 4: Configure Environment Variables

Ensure you have a .env file in the root directory with the appropriate configuration settings:

HOST=0.0.0.0
PORT=8000
DEBUG=True
DATABASE_URL=sqlite+aiosqlite:///./database.db
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173


Step 5: Run the Development Server

Start the FastAPI server using uvicorn with auto-reload enabled:

python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000


Once running, the application will automatically initialize the SQLite database (database.sqlite) and will be accessible at:

API Documentation (Swagger UI): http://localhost:8000/docs

Alternative Documentation (ReDoc): http://localhost:8000/redoc

WebSocket Endpoint: ws://localhost:8000/ws/{company_code}