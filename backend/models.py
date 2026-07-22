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
    edgeswitch_user: Optional[str] = None
    edgeswitch_pass: Optional[str] = None
    tplink_user: Optional[str] = None
    tplink_pass: Optional[str] = None
    alias_of: Optional[int] = Field(default=None, foreign_key="device.id")
    is_deleted: bool = Field(default=False)
    is_manual: bool = Field(default=False)
    monitor_id: Optional[int] = None
    alert_status: Optional[str] = None  # "up", "down", or None
    offline_since: Optional[datetime] = None
    ssh_banner: Optional[str] = None    # first line of SSH banner, e.g. "SSH-2.0-dropbear"
    topology_parent_id: Optional[int] = Field(default=None, foreign_key="device.id")  # manual topology override
    is_pinned: bool = Field(default=False)  # never auto-deleted by dedup
    switch_port: Optional[str] = None       # port label on parent switch/router


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
