from typing import Optional
from sqlmodel import Field, SQLModel
from datetime import datetime


class Device(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ip: str = Field(index=True, unique=True)
    mac: Optional[str] = None
    hostname: Optional[str] = None
    vendor: Optional[str] = None
    label: Optional[str] = None
    icon: Optional[str] = None  # router, switch, server, camera, pc, phone, unknown
    web_port: Optional[int] = None
    web_protocol: Optional[str] = "http"
    is_online: bool = False
    x: float = 100.0
    y: float = 100.0
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: Optional[datetime] = None
    tags: Optional[str] = None
    network: Optional[str] = None
    mikrotik_user: Optional[str] = None
    mikrotik_pass: Optional[str] = None


class ScanLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    devices_found: int = 0
    network: str = ""
    status: str = "running"  # running, done, error


class Settings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    value: str
