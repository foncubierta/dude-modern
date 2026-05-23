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
import uptime_kuma as uk
import discovery


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


async def enrich_macs_from_mikrotik():
    """Query MikroTik ARP tables and fill in missing MACs on devices."""
    from sqlmodel import Session as S
    with S(engine) as session:
        mt_devices = session.exec(
            select(Device).where(Device.mikrotik_user.isnot(None))
        ).all()
        if not mt_devices:
            return

        arp_results = await asyncio.gather(
            *[mikrotik.get_arp_table(d.ip, d.mikrotik_user, d.mikrotik_pass) for d in mt_devices],
            return_exceptions=True,
        )

        # Build IP → MAC map from all MikroTik routers
        ip_to_mac: dict[str, str] = {}
        for arp in arp_results:
            if isinstance(arp, Exception) or not arp:
                continue
            for entry in arp:
                mac = entry.get("mac-address", "").upper().strip()
                ip  = entry.get("address", "").strip()
                if mac and ip:
                    ip_to_mac[ip] = mac

        if not ip_to_mac:
            return

        updated = False
        for device in session.exec(select(Device)).all():
            if device.mac:
                continue  # already has a MAC
            mac = ip_to_mac.get(device.ip)
            if mac:
                device.mac = mac
                updated = True

        if updated:
            session.commit()
            print(f"[enrich_macs] filled MAC addresses from MikroTik ARP table")


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


async def enrich_hostnames_from_discovery():
    """
    Run mDNS, SSDP and NetBIOS discovery in parallel and update device
    hostnames/icons. Only fills in missing hostnames — never overwrites
    a user label or an already-set hostname.
    """
    from sqlmodel import Session as S

    with S(engine) as session:
        devices = session.exec(select(Device).where(Device.is_deleted == False)).all()
        ips = [d.ip for d in devices]

    if not ips:
        return

    mdns_result, ssdp_names, netbios_names = await asyncio.gather(
        discovery.discover_mdns(timeout=6.0),
        discovery.discover_ssdp(timeout=4.0),
        discovery.discover_netbios(ips, timeout=0.8),
        return_exceptions=True,
    )

    # Unpack mDNS tuple (names, icon_hints)
    mdns_names: dict[str, str] = {}
    mdns_icons: dict[str, str] = {}
    if isinstance(mdns_result, tuple):
        mdns_names, mdns_icons = mdns_result

    if isinstance(ssdp_names, Exception):   ssdp_names   = {}
    if isinstance(netbios_names, Exception): netbios_names = {}

    # Merge: NetBIOS < SSDP < mDNS (highest priority last, overwrites lower)
    merged_names: dict[str, str] = {}
    for source in (netbios_names, ssdp_names, mdns_names):
        if isinstance(source, dict):
            merged_names.update(source)

    if not merged_names and not mdns_icons:
        return

    with S(engine) as session:
        updated = False
        for device in session.exec(select(Device)).all():
            # Only fill in hostname if currently empty
            name = merged_names.get(device.ip)
            if name and not device.hostname:
                device.hostname = name
                updated = True
            # Auto-set icon if still unknown and mDNS gave a hint
            icon_hint = mdns_icons.get(device.ip)
            if icon_hint and device.icon in (None, "unknown"):
                device.icon = icon_hint
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
    await enrich_macs_from_mikrotik()
    await enrich_hostnames_from_mikrotik()
    await enrich_hostnames_from_discovery()


STALE_SOFT_DAYS = 30   # offline this long → hide from map
STALE_HARD_DAYS = 90   # offline this long → delete from DB


async def cleanup_stale_devices():
    """
    Daily job:
      - Soft-delete devices not seen for STALE_SOFT_DAYS days.
      - Hard-delete devices not seen for STALE_HARD_DAYS days.
    Skips: manual devices (user-added), devices linked to a UK monitor.
    """
    from sqlmodel import Session as S
    now = datetime.utcnow()

    with S(engine) as session:
        devices = session.exec(select(Device)).all()
        soft_n = hard_n = 0

        for d in devices:
            # Never auto-clean manually added entries or monitored devices
            if d.is_manual or d.monitor_id:
                continue
            if not d.last_seen:
                continue

            days_gone = (now - d.last_seen).days

            if days_gone >= STALE_HARD_DAYS:
                session.delete(d)
                hard_n += 1
            elif days_gone >= STALE_SOFT_DAYS and not d.is_deleted and not d.is_online:
                d.is_deleted = True
                soft_n += 1

        if soft_n or hard_n:
            session.commit()
            print(f"[cleanup] soft-deleted {soft_n}, hard-deleted {hard_n} stale devices")


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db()
    _seed_default_settings()
    _backfill_offline_since()
    asyncio.get_event_loop().create_task(enrich_macs_from_mikrotik())
    scheduler.add_job(scheduled_scan,       "interval", minutes=5, id="auto_scan")
    scheduler.add_job(cleanup_stale_devices, "interval", hours=24,  id="stale_cleanup")
    scheduler.start()
    yield
    scheduler.shutdown()


def _backfill_offline_since():
    """One-time backfill: set offline_since = last_seen for devices already offline."""
    from sqlmodel import Session as S
    with S(engine) as session:
        devices = session.exec(
            select(Device).where(
                Device.is_online == False,
                Device.offline_since == None,
                Device.last_seen != None,
            )
        ).all()
        for d in devices:
            d.offline_since = d.last_seen
        if devices:
            session.commit()
            print(f"[backfill] set offline_since on {len(devices)} existing offline devices")


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
    is_manual: Optional[bool] = None


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
        await enrich_macs_from_mikrotik()
        await enrich_hostnames_from_mikrotik()
        await enrich_hostnames_from_discovery()

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
    ip_to_device  = {d.ip: d for d in devices}

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
                ip  = station.get("ip", "")
                # Match by MAC first, fall back to IP (ARP table entries have both)
                target = (mac_to_device.get(mac) if mac else None) or (ip_to_device.get(ip) if ip else None)
                if target and target.id != cpe_dev.id and target.id not in aliased_ids:
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


# ── Manual devices ───────────────────────────────────────────────────────────

class ManualDeviceCreate(BaseModel):
    ip: str                          # IP or hostname/domain
    label: Optional[str] = None
    icon: Optional[str] = "unknown"
    web_port: Optional[int] = None
    web_protocol: Optional[str] = "http"
    tags: Optional[str] = None


@app.post("/api/devices/manual")
def create_manual_device(body: ManualDeviceCreate, session: Session = Depends(get_session)):
    existing = session.exec(select(Device).where(Device.ip == body.ip)).first()
    if existing:
        raise HTTPException(409, "Device already exists")
    d = Device(
        ip=body.ip,
        label=body.label or None,
        icon=body.icon or "unknown",
        web_port=body.web_port,
        web_protocol=body.web_protocol or "http",
        tags=body.tags,
        is_manual=True,
        is_online=False,
        x=100.0, y=100.0,
    )
    session.add(d)
    session.commit()
    session.refresh(d)
    return d


# ── Uptime Kuma ───────────────────────────────────────────────────────────────

def _get_uk_settings(session: Session) -> dict:
    keys = ["uptime_kuma_url", "uptime_kuma_user", "uptime_kuma_pass"]
    result = {}
    for k in keys:
        s = session.exec(select(Settings).where(Settings.key == k)).first()
        result[k] = s.value if s else ""
    return result


@app.get("/api/uptime-kuma/settings")
def get_uk_settings(session: Session = Depends(get_session)):
    return _get_uk_settings(session)


class UKSettingsBody(BaseModel):
    url: str
    user: str
    password: str


@app.put("/api/uptime-kuma/settings")
async def save_uk_settings(body: UKSettingsBody, session: Session = Depends(get_session)):
    for key, value in [
        ("uptime_kuma_url",  body.url),
        ("uptime_kuma_user", body.user),
        ("uptime_kuma_pass", body.password),
    ]:
        s = session.exec(select(Settings).where(Settings.key == key)).first()
        if s:
            s.value = value
        else:
            session.add(Settings(key=key, value=value))
    session.commit()
    return {"ok": True}


@app.post("/api/uptime-kuma/test")
async def test_uk(session: Session = Depends(get_session)):
    cfg = _get_uk_settings(session)
    if not cfg["uptime_kuma_url"]:
        raise HTTPException(400, "Uptime Kuma not configured")
    ok = await uk.test_connection(cfg["uptime_kuma_url"], cfg["uptime_kuma_user"], cfg["uptime_kuma_pass"])
    return {"ok": ok}


@app.post("/api/devices/{device_id}/monitor")
async def add_monitor(device_id: int, session: Session = Depends(get_session)):
    d = session.get(Device, device_id)
    if not d:
        raise HTTPException(404, "Device not found")
    cfg = _get_uk_settings(session)
    if not cfg["uptime_kuma_url"]:
        raise HTTPException(400, "Uptime Kuma not configured — go to Settings first")
    name = d.label or d.hostname or d.ip
    if d.web_port:
        target = f"{d.web_protocol}://{d.ip}:{d.web_port}"
        is_http = True
    else:
        target = d.ip
        is_http = False
    try:
        mid = await uk.add_monitor(
            cfg["uptime_kuma_url"], cfg["uptime_kuma_user"], cfg["uptime_kuma_pass"],
            name, target, is_http,
        )
    except Exception as e:
        raise HTTPException(500, f"Uptime Kuma error: {e}")
    d.monitor_id = mid
    session.add(d)
    session.commit()
    session.refresh(d)
    return d


@app.delete("/api/devices/{device_id}/monitor")
async def remove_monitor(device_id: int, session: Session = Depends(get_session)):
    d = session.get(Device, device_id)
    if not d:
        raise HTTPException(404, "Device not found")
    if not d.monitor_id:
        raise HTTPException(400, "No monitor configured for this device")
    cfg = _get_uk_settings(session)
    if not cfg["uptime_kuma_url"]:
        raise HTTPException(400, "Uptime Kuma not configured")
    try:
        await uk.delete_monitor(
            cfg["uptime_kuma_url"], cfg["uptime_kuma_user"], cfg["uptime_kuma_pass"],
            d.monitor_id,
        )
    except Exception as e:
        raise HTTPException(500, f"Uptime Kuma error: {e}")
    d.monitor_id = None
    d.alert_status = None
    session.add(d)
    session.commit()
    session.refresh(d)
    return d


@app.post("/api/webhook")
async def receive_webhook(payload: dict, session: Session = Depends(get_session)):
    """Receive Uptime Kuma status change webhooks."""
    monitor = payload.get("monitor", {})
    heartbeat = payload.get("heartbeat", {})
    monitor_id = monitor.get("id")
    status = heartbeat.get("status")  # 0=down, 1=up

    if monitor_id is None or status is None:
        return {"ok": True}

    d = session.exec(select(Device).where(Device.monitor_id == monitor_id)).first()
    if d:
        d.alert_status = "up" if status == 1 else "down"
        session.add(d)
        session.commit()

    return {"ok": True}


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
