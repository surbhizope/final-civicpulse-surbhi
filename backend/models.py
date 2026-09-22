from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum


class DepartmentCode(str, Enum):
    ROADS = "ROADS"
    WATER = "WATER"
    SOLID_WASTE = "SOLID_WASTE"
    ELECTRICAL = "ELECTRICAL"
    PUBLIC_HEALTH = "PUBLIC_HEALTH"


class Priority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"
    CRITICAL = "CRITICAL"


class TicketStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLUTION_SUBMITTED = "RESOLUTION_SUBMITTED"
    RESOLVED = "RESOLVED"
    BREACHED = "BREACHED"
    REOPENED = "REOPENED"


class UserRole(str, Enum):
    FIELD_OFFICER = "FIELD_OFFICER"
    SUPERVISOR = "SUPERVISOR"
    COMMISSIONER = "COMMISSIONER"


class TicketCreate(BaseModel):
    description: str = Field(..., min_length=12)
    category: str = "General"
    latitude: float
    longitude: float
    address: Optional[str] = None
    before_photo: Optional[str] = None


class TicketResponse(BaseModel):
    id: str
    ticket_number: str
    pin: Optional[str] = None
    description: str
    category: str
    department_code: str
    priority: str
    status: str
    latitude: float
    longitude: float
    address: str
    before_photo: Optional[str] = None
    after_photo: Optional[str] = None
    closing_note: Optional[str] = None
    assigned_to: Optional[str] = None
    duplicate_of: Optional[str] = None
    impact_count: int
    created_at: str
    sla_due_at: str
    resolved_at: Optional[str] = None
    timeline: List[dict] = []


class TrackRequest(BaseModel):
    ticket_number: str
    pin: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    email: str
    name: str
    role: str
    token: str


class TicketAction(BaseModel):
    action: str
    closing_note: Optional[str] = None
    after_photo: Optional[str] = None


class TriageResult(BaseModel):
    department: DepartmentCode
    subcategory: str
    priority: Priority
    summary: str
    urgency_score: int


class DashboardStats(BaseModel):
    open: int
    in_progress: int
    breached: int
    resolved_today: int