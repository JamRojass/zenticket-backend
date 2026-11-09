"""
Pydantic Data Models Module.
Defines data transfer objects (DTOs), request payloads, and response serialization schemas.
"""

from pydantic import BaseModel, Field
from typing import Optional, List

class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    short_code: str = Field(..., min_length=2, max_length=10)

class RegisterCompanyRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=100)
    admin_username: str = Field(..., min_length=3, max_length=50)
    admin_password: str = Field(..., min_length=6)

class UpdateProfileRequest(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    new_password: Optional[str] = Field(None, min_length=6)

class CompanyOut(BaseModel):
    id: int
    name: str
    short_code: str
    is_active: int
    created_at: int

class UserCreate(BaseModel):
    company_id: Optional[int] = None
    username: str
    fullname: str
    password: str
    role: str # 'admin' or 'operator'
    area_id: Optional[int] = None

class UpdateUsernameRequest(BaseModel):
    username: str

class UserUpdate(BaseModel):
    fullname: Optional[str] = None
    area_id: Optional[int] = None

class UserOut(BaseModel):
    id: int
    company_id: int
    company_short_code: Optional[str] = None
    username: str
    fullname: Optional[str] = None
    role: str
    area_id: Optional[int] = None
    area_name: Optional[str] = None
    is_active: int
    created_at: int

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class AreaCreate(BaseModel):
    company_id: Optional[int] = None
    name: str = Field(..., min_length=2, max_length=100)
    short_code: str = Field(..., min_length=1, max_length=10)

class AreaOut(BaseModel):
    id: int
    company_id: int
    name: str
    short_code: str
    is_active: int
    created_at: int

class StationCreate(BaseModel):
    company_id: Optional[int] = None
    area_id: int
    name: str

class StationUpdate(BaseModel):
    #id: int
    name: str
    #company_id: Optional[int] = None
    area_id: Optional[int] = None
    #is_active: Optional[bool] = None

class StationOut(BaseModel):
    id: int
    company_id: int
    area_id: int
    name: str
    is_active: int

class operatorSessionRequest(BaseModel):
    station_id: int

class TicketCreate(BaseModel):
    area_id: int

class TicketOut(BaseModel):
    id: int
    company_id: int
    area_id: int
    ticket_code: str
    status: str
    assigned_user_id: Optional[int] = None
    created_at: int
    called_at: Optional[int] = None
    completed_at: Optional[int] = None
    area_name: Optional[str] = None
    assigned_username: Optional[str] = None

class TicketDeriveRequest(BaseModel):
    target_area_id: int

class AuditLogOut(BaseModel):
    id: int
    company_id: int
    user_id: Optional[int] = None
    action: str
    details: Optional[str] = None
    created_at: int
    username: Optional[str] = None

class MetricsSummaryOut(BaseModel):
    total_tickets_today: int
    waiting_tickets: int
    in_service_tickets: int
    completed_tickets: int
    derived_tickets: int
    cancelled_tickets: int
    avg_service_time_seconds: float

class DisplayScreenCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    type: str = Field(default="tv", pattern="^(tv|kiosk)$")

class DisplayScreenOut(BaseModel):
    id: int
    company_id: int
    name: str
    type: str
    pairing_code: str
    is_active: int
    created_at: int

class ScreenPairRequest(BaseModel):
    company_code: str
    pairing_code: str
    device_type: Optional[str] = Field(None, pattern="^(tv|kiosk)$")

class UserPreferencesUpdate(BaseModel):
    per_page: int
    font_size: str
    font_family: str

class UserPreferencesOut(BaseModel):
    per_page: int
    font_size: str
    font_family: str