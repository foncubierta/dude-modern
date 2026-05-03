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
import edgeswitch
import tplink_cpe


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


async def enrich_hostnames_from_mikrotik():
    """Query MikroTik DHCP leases and update device hostnames with active-hostname."""
    from sqlmodel import Session as S
    with S(engine) as session:
        mt_devices = session.exec(
            select(Device).where(Device.mikrotik_user.isnot(None))
        ).all()
        if not mt_devices:
            return

        lease_results = await asyncio.gather(
            *[mikrotik.get_dhcp_leases(d.ip, d.mikrotik_user, d.mikrotik_pass) for d in mt_devices],
            return_exceptions=True,
        )

        # Build MAC -> hostname and IP -> hostname maps from all MikroTik routers
        mac_to_hostname: dict[str, str] = {}
        ip_to_hostname: dict[str, str] = {}
        for leases in lease_results:
            if isinstance(leases, Exception) or not leases:
                continue
            for lease in leases:
                mac = lease.get("mac-address", "").upper()
                ip = (lease.get("active-address") or lease.get("address") or "").strip()
                hostname = (
                    lease.get("active-hostname")
                    or lease.get("host-name")
                    or ""
                ).strip()
                if hostname:
                    if mac:
                        mac_to_hostname[mac] = hostname
                    if ip:
                        ip_to_hostname[ip] = hostname

        if not mac_to_hostname and not ip_to_hostname:
            return

        updated = False
        for device in session.exec(select(Device)).all():
            # Prefer MAC match (more reliable), fall back to IP match
            name = None
            if device.mac:
                name = mac_to_hostname.get(device.mac.upper())
            if not name:
                name = ip_to_hostname.get(device.ip)
            if name and name != device.hostname:
                device.hostname = name
                updated = True

        if updated:
            session.commit()


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
    await enrich_hostnames_from_mikrotik()


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
    return session.exec(select(Device).where(Device.is_deleted == False).order_by(Device.ip)).all()


@app.get("/api/devices/deleted")
def list_deleted_devices(session: Session = Depends(get_session)):
    return session.exec(select(Device).where(Device.is_deleted == True).order_by(Device.ip)).all()


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
    edgeswitch_user: Optional[str] = None
    edgeswitch_pass: Optional[str] = None
    tplink_user: Optional[str] = None
    tplink_pass: Optional[str] = None
    alias_of: Optional[int] = None


@app.patch("/api/devices/{device_id}")
def update_device(device_id: int, body: DeviceUpdate, session: Session = Depends(get_session)):
    d = session.get(Device, device_id)
    if not d:
        raise HTTPException(404, "Device not found")
    for field, val in body.model_dump(exclude_unset=True).items():
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
    d.is_deleted = True
    session.add(d)
    session.commit()
    return {"ok": True}


@app.post("/api/devices/{device_id}/restore")
def restore_device(device_id: int, session: Session = Depends(get_session)):
    d = session.get(Device, device_id)
    if not d:
        raise HTTPException(404, "Device not found")
    d.is_deleted = False
    session.add(d)
    session.commit()
    session.refresh(d)
    return d


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
        await enrich_hostnames_from_mikrotik()

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

    # Build alias resolution map: alias_id → primary_id
    def resolve(device_id: int, alias_map: dict) -> int:
        seen = set()
        while device_id in alias_map and device_id not in seen:
            seen.add(device_id)
            device_id = alias_map[device_id]
        return device_id

    alias_map = {d.id: d.alias_of for d in devices if d.alias_of}
    aliased_ids = set(alias_map.keys())

    # Only use non-alias devices for topology
    real_devices = [d for d in devices if d.id not in aliased_ids]

    by_network: dict[str, list[Device]] = {}
    for d in real_devices:
        if d.network:
            by_network.setdefault(d.network, []).append(d)

    # Also include alias devices in subnet groups (resolving to their primary)
    for d in devices:
        if d.id in aliased_ids and d.network:
            primary_id = resolve(d.id, alias_map)
            # alias devices' subnets are now owned by the primary
            by_network.setdefault(d.network, [])

    links: list[dict] = []
    for cidr, net_devs in by_network.items():
        # Find the intended gateway (.1 of the subnet), resolving aliases
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            gw_ip = str(next(net.hosts()))
        except Exception:
            gw_ip = None

        gw: Optional[Device] = None
        if gw_ip:
            gw = next((d for d in devices if d.ip == gw_ip), None)
        if gw and gw.id in aliased_ids:
            # Gateway is aliased — redirect to the primary device
            primary_id = resolve(gw.id, alias_map)
            gw = next((d for d in devices if d.id == primary_id), None)
        if not gw:
            # Fallback: router/AP/switch in subnet that isn't aliased
            gw = next(
                (d for d in net_devs if d.id not in aliased_ids and d.icon in ("router", "ap", "switch")),
                None,
            )
        if not gw:
            gw = next((d for d in net_devs if d.id not in aliased_ids), None)

        if gw:
            for d in net_devs:
                if d.id not in aliased_ids and d.id != gw.id:
                    links.append({"source": gw.id, "target": d.id})

    # Deduplicate
    seen_links: set[tuple] = set()
    unique_links = []
    for lnk in links:
        key = (lnk["source"], lnk["target"])
        if key not in seen_links:
            seen_links.add(key)
            unique_links.append(lnk)

    mac_to_device = {d.mac.upper(): d for d in devices if d.mac}

    # MikroTik: refine topology via ARP table
    mt_devices = [d for d in devices if d.mikrotik_user and d.mikrotik_pass]
    if mt_devices:
        arp_results = await asyncio.gather(
            *[mikrotik.get_arp_table(d.ip, d.mikrotik_user, d.mikrotik_pass) for d in mt_devices],
            return_exceptions=True,
        )
        for mt_dev, arp in zip(mt_devices, arp_results):
            if isinstance(arp, Exception) or not arp:
                continue
            for entry in arp:
                mac = entry.get("mac-address", "").upper()
                target = mac_to_device.get(mac)
                if target and target.id != mt_dev.id and target.id not in aliased_ids:
                    # Only refine devices in the same subnet — don't steal devices from other gateways
                    if target.network and mt_dev.network and target.network != mt_dev.network:
                        continue
                    unique_links = [l for l in unique_links if l["target"] != target.id]
                    unique_links.append({"source": mt_dev.id, "target": target.id})

    # EdgeSwitch: refine topology via FDB (MAC address table — most accurate)
    es_devices = [d for d in devices if d.edgeswitch_user and d.edgeswitch_pass]
    if es_devices:
        fdb_results = await asyncio.gather(
            *[edgeswitch.get_fdb(d.ip, d.edgeswitch_user, d.edgeswitch_pass) for d in es_devices],
            return_exceptions=True,
        )
        for es_dev, fdb in zip(es_devices, fdb_results):
            if isinstance(fdb, Exception) or not fdb:
                continue
            for entry in fdb:
                mac = entry.get("mac_address", "").upper()
                target = mac_to_device.get(mac)
                if target and target.id != es_dev.id and target.id not in aliased_ids:
                    # Only refine devices in the same subnet — don't steal devices from other gateways
                    if target.network and es_dev.network and target.network != es_dev.network:
                        continue
                    unique_links = [l for l in unique_links if l["target"] != target.id]
                    unique_links.append({"source": es_dev.id, "target": target.id})

    # TP-Link CPE: topology via wireless station list
    cpe_devices = [d for d in devices if d.tplink_user and d.tplink_pass]
    if cpe_devices:
        station_results = await asyncio.gather(
            *[tplink_cpe.get_stations(d.ip, d.tplink_user, d.tplink_pass) for d in cpe_devices],
            return_exceptions=True,
        )
        for cpe_dev, stations in zip(cpe_devices, station_results):
            if isinstance(stations, Exception) or not stations:
                continue
            for station in stations:
                mac = station.get("mac", "").upper()
                if not mac:
                    continue
                target = mac_to_device.get(mac)
                if target and target.id != cpe_dev.id and target.id not in aliased_ids:
                    # CPE clients can be on any subnet — no subnet restriction
                    unique_links = [l for l in unique_links if l["target"] != target.id]
                    unique_links.append({"source": cpe_dev.id, "target": target.id})

    return {"links": unique_links, "aliases": list(aliased_ids)}


# ── Traffic ───────────────────────────────────────────────────────────────────

@app.get("/api/traffic")
async def get_traffic_stats(session: Session = Depends(get_session)):
    mt_devices = session.exec(
        select(Device).where(Device.mikrotik_user.isnot(None))
    ).all()
    es_devices = session.exec(
        select(Device).where(Device.edgeswitch_user.isnot(None))
    ).all()

    if not mt_devices and not es_devices:
        return {"devices": {}}

    tasks = (
        [(d, "mikrotik") for d in mt_devices] +
        [(d, "edgeswitch") for d in es_devices]
    )

    results = await asyncio.gather(
        *[
            mikrotik.get_traffic(d.id, d.ip, d.mikrotik_user, d.mikrotik_pass)
            if kind == "mikrotik"
            else edgeswitch.get_traffic(d.id, d.ip, d.edgeswitch_user, d.edgeswitch_pass)
            for d, kind in tasks
        ],
        return_exceptions=True,
    )

    traffic = {}
    for (d, _), res in zip(tasks, results):
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
