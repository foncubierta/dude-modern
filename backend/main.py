import ipaddress
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
import asyncio

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel

from database import create_db, engine, get_session
from models import Device, ScanLog, Settings
from scanner import scan_networks, get_local_networks
import mikrotik


scheduler = AsyncIOScheduler()
scan_lock = asyncio.Lock()


def get_configured_networks(session: Session) -> list[str]:
    setting = session.exec(select(Settings).where(Settings.key == "scan_networks")).first()
    if setting:
        try:
            return json.loads(setting.value)
        except Exception:
            return [setting.value]
    return get_local_networks()


async def scheduled_scan():
    if scan_lock.locked():
        return

    from sqlmodel import Session as S
    with S(engine) as session:
        networks = get_configured_networks(session)
        log = ScanLog(network=json.dumps(networks))
        session.add(log)
        session.commit()
        session.refresh(log)
        scan_id = log.id

    async with scan_lock:
        await scan_networks(networks, scan_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db()
    _seed_default_settings()
    scheduler.add_job(scheduled_scan, "interval", minutes=5, id="auto_scan")
    scheduler.start()
    yield
    scheduler.shutdown()


def _seed_default_settings():
    from sqlmodel import Session as S
    detected = get_local_networks()
    with S(engine) as session:
        for key, value in [
            ("scan_networks", json.dumps(detected)),
            ("scan_interval", "5"),
            ("auto_scan", "true"),
        ]:
            exists = session.exec(select(Settings).where(Settings.key == key)).first()
            if not exists:
                session.add(Settings(key=key, value=value))
        session.commit()


app = FastAPI(title="Dude Modern", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Devices ──────────────────────────────────────────────────────────────────

@app.get("/api/devices")
def list_devices(session: Session = Depends(get_session)):
    return session.exec(select(Device).order_by(Device.ip)).all()


@app.get("/api/devices/{device_id}")
def get_device(device_id: int, session: Session = Depends(get_session)):
    d = session.get(Device, device_id)
    if not d:
        raise HTTPException(404, "Device not found")
    return d


class DeviceUpdate(BaseModel):
    label: Optional[str] = None
    icon: Optional[str] = None
    web_port: Optional[int] = None
    web_protocol: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    tags: Optional[str] = None
    network: Optional[str] = None
    mikrotik_user: Optional[str] = None
    mikrotik_pass: Optional[str] = None


@app.patch("/api/devices/{device_id}")
def update_device(device_id: int, body: DeviceUpdate, session: Session = Depends(get_session)):
    d = session.get(Device, device_id)
    if not d:
        raise HTTPException(404, "Device not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(d, field, val)
    session.add(d)
    session.commit()
    session.refresh(d)
    return d


@app.delete("/api/devices/{device_id}")
def delete_device(device_id: int, session: Session = Depends(get_session)):
    d = session.get(Device, device_id)
    if not d:
        raise HTTPException(404, "Device not found")
    session.delete(d)
    session.commit()
    return {"ok": True}


# ── Scan ─────────────────────────────────────────────────────────────────────

@app.post("/api/scan")
async def trigger_scan(background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    if scan_lock.locked():
        raise HTTPException(409, "Scan already running")

    networks = get_configured_networks(session)
    log = ScanLog(network=json.dumps(networks))
    session.add(log)
    session.commit()
    session.refresh(log)
    scan_id = log.id

    async def _run():
        async with scan_lock:
            await scan_networks(networks, scan_id)

    background_tasks.add_task(_run)
    return {"scan_id": scan_id, "networks": networks, "status": "started"}


@app.get("/api/scan/status")
def scan_status(session: Session = Depends(get_session)):
    latest = session.exec(select(ScanLog).order_by(ScanLog.id.desc())).first()
    return {
        "running": scan_lock.locked(),
        "latest": latest,
    }


@app.get("/api/scan/logs")
def scan_logs(session: Session = Depends(get_session)):
    return session.exec(select(ScanLog).order_by(ScanLog.id.desc())).all()


# ── Networks config ───────────────────────────────────────────────────────────

@app.get("/api/networks/configured")
def get_configured(session: Session = Depends(get_session)):
    return {"networks": get_configured_networks(session)}


@app.post("/api/networks/configured")
def add_network(body: dict, session: Session = Depends(get_session)):
    cidr = body.get("network", "").strip()
    if not cidr:
        raise HTTPException(400, "network is required")
    networks = get_configured_networks(session)
    if cidr in networks:
        raise HTTPException(409, "Network already configured")
    networks.append(cidr)
    _save_networks(session, networks)
    return {"networks": networks}


@app.delete("/api/networks/configured/{cidr:path}")
def remove_network(cidr: str, session: Session = Depends(get_session)):
    networks = get_configured_networks(session)
    if cidr not in networks:
        raise HTTPException(404, "Network not found")
    networks = [n for n in networks if n != cidr]
    _save_networks(session, networks)
    return {"networks": networks}


def _save_networks(session: Session, networks: list[str]):
    setting = session.exec(select(Settings).where(Settings.key == "scan_networks")).first()
    if setting:
        setting.value = json.dumps(networks)
    else:
        session.add(Settings(key="scan_networks", value=json.dumps(networks)))
    session.commit()


@app.get("/api/networks/detected")
def detected_networks():
    return {"networks": get_local_networks()}


# ── Settings ─────────────────────────────────────────────────────────────────

@app.get("/api/settings")
def get_settings(session: Session = Depends(get_session)):
    rows = session.exec(select(Settings)).all()
    return {r.key: r.value for r in rows}


class SettingUpdate(BaseModel):
    value: str


@app.put("/api/settings/{key}")
def set_setting(key: str, body: SettingUpdate, session: Session = Depends(get_session)):
    s = session.exec(select(Settings).where(Settings.key == key)).first()
    if s:
        s.value = body.value
    else:
        s = Settings(key=key, value=body.value)
        session.add(s)
    session.commit()
    return {"key": key, "value": body.value}


# ── Topology ─────────────────────────────────────────────────────────────────

def _gateway_for_network(cidr: str, devices: list[Device]) -> Optional[Device]:
    try:
        net = ipaddress.ip_network(cidr, strict=False)
        gw_ip = str(next(net.hosts()))
        for d in devices:
            if d.ip == gw_ip:
                return d
        for d in devices:
            if d.icon in ("router", "ap", "switch"):
                return d
        return devices[0] if devices else None
    except Exception:
        return None


@app.get("/api/topology")
async def get_topology(session: Session = Depends(get_session)):
    devices = session.exec(select(Device)).all()

    by_network: dict[str, list[Device]] = {}
    for d in devices:
        if d.network:
            by_network.setdefault(d.network, []).append(d)

    links: list[dict] = []
    for cidr, net_devs in by_network.items():
        gw = _gateway_for_network(cidr, net_devs)
        if gw:
            for d in net_devs:
                if d.id != gw.id:
                    links.append({"source": gw.id, "target": d.id})

    mt_devices = [d for d in devices if d.mikrotik_user and d.mikrotik_pass]
    if mt_devices:
        arp_results = await asyncio.gather(
            *[mikrotik.get_arp_table(d.ip, d.mikrotik_user, d.mikrotik_pass) for d in mt_devices],
            return_exceptions=True,
        )
        mac_to_device = {d.mac.upper(): d for d in devices if d.mac}
        for mt_dev, arp in zip(mt_devices, arp_results):
            if isinstance(arp, Exception) or not arp:
                continue
            for entry in arp:
                mac = entry.get("mac-address", "").upper()
                target = mac_to_device.get(mac)
                if target and target.id != mt_dev.id:
                    links = [l for l in links if l["target"] != target.id]
                    links.append({"source": mt_dev.id, "target": target.id})

    return {"links": links}


# ── Traffic ───────────────────────────────────────────────────────────────────

@app.get("/api/traffic")
async def get_traffic_stats(session: Session = Depends(get_session)):
    mt_devices = session.exec(
        select(Device).where(Device.mikrotik_user.isnot(None))
    ).all()

    if not mt_devices:
        return {"devices": {}}

    results = await asyncio.gather(
        *[mikrotik.get_traffic(d.id, d.ip, d.mikrotik_user, d.mikrotik_pass) for d in mt_devices],
        return_exceptions=True,
    )

    traffic = {}
    for d, res in zip(mt_devices, results):
        if not isinstance(res, Exception):
            traffic[str(d.id)] = res

    return {"devices": traffic}


# ── Stats ─────────────────────────────────────────────────────────────────────

@app.get("/api/stats")
def stats(session: Session = Depends(get_session)):
    devices = session.exec(select(Device)).all()
    online = sum(1 for d in devices if d.is_online)
    networks_found = list({d.network for d in devices if d.network})
    return {
        "total": len(devices),
        "online": online,
        "offline": len(devices) - online,
        "networks": len(networks_found),
    }
