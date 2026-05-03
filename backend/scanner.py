import asyncio
import subprocess
from datetime import datetime
from typing import Optional
import nmap
from sqlmodel import Session, select
from database import engine
from models import Device, ScanLog


VENDOR_GUESSES = {
    "ubiquiti": ("router", "Ubiquiti"),
    "mikrotik": ("router", "MikroTik"),
    "cisco": ("router", "Cisco"),
    "tp-link": ("router", "TP-Link"),
    "netgear": ("router", "Netgear"),
    "synology": ("server", "Synology"),
    "qnap": ("server", "QNAP"),
    "raspberry": ("server", "Raspberry Pi"),
    "apple": ("phone", "Apple"),
    "samsung": ("phone", "Samsung"),
    "hikvision": ("camera", "Hikvision"),
    "dahua": ("camera", "Dahua"),
    "axis": ("camera", "Axis"),
    "dell": ("pc", "Dell"),
    "hewlett": ("pc", "HP"),
    "lenovo": ("pc", "Lenovo"),
    "intel": ("pc", "Intel"),
    "vmware": ("server", "VMware"),
    "proxmox": ("server", "Proxmox"),
}

COMMON_WEB_PORTS = [80, 443, 8080, 8443, 8888, 8008, 8123, 3000, 5000, 9000, 9090, 7080]


def guess_icon_and_vendor(vendor_raw: str) -> tuple[str, str]:
    if not vendor_raw:
        return "unknown", ""
    low = vendor_raw.lower()
    for keyword, (icon, name) in VENDOR_GUESSES.items():
        if keyword in low:
            return icon, name
    return "unknown", vendor_raw


def get_local_networks() -> list[str]:
    """Detecta las redes locales disponibles en el host."""
    try:
        result = subprocess.run(
            ["ip", "route"],
            capture_output=True, text=True, timeout=5
        )
        networks = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts and "/" in parts[0] and not parts[0].startswith("default"):
                networks.append(parts[0])
        return networks if networks else ["192.168.1.0/24"]
    except Exception:
        return ["192.168.1.0/24"]


async def _try_port(ip: str, port: int) -> Optional[int]:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=0.3
        )
        writer.close()
        return port
    except Exception:
        return None


async def check_web_port(ip: str) -> tuple[Optional[int], str]:
    """Comprueba puertos web en paralelo."""
    results = await asyncio.gather(*[_try_port(ip, p) for p in COMMON_WEB_PORTS])
    for port in COMMON_WEB_PORTS:
        if port in results:
            protocol = "https" if port in (443, 8443) else "http"
            return port, protocol
    return None, "http"


def run_nmap_scan(network: str) -> list[dict]:
    """Ejecuta nmap en una subred y retorna lista de hosts encontrados."""
    nm = nmap.PortScanner()
    try:
        nm.scan(hosts=network, arguments="-sn --host-timeout 3s --max-retries 1 --min-rate 500")
    except Exception as e:
        print(f"nmap error on {network}: {e}")
        return []

    results = []
    for host in nm.all_hosts():
        info = nm[host]
        hostname = ""
        if info.hostname():
            hostname = info.hostname()
        elif info["hostnames"]:
            hostname = info["hostnames"][0].get("name", "")

        mac = ""
        vendor_raw = ""
        if "mac" in info.get("addresses", {}):
            mac = info["addresses"]["mac"]
        if "vendor" in info and mac and mac in info["vendor"]:
            vendor_raw = info["vendor"][mac]

        results.append({
            "ip": host,
            "hostname": hostname,
            "mac": mac,
            "vendor_raw": vendor_raw,
            "state": info.state(),
        })
    return results


async def scan_single_network(network: str) -> list[dict]:
    """Wrapper async para ejecutar nmap en un thread separado."""
    loop = asyncio.get_event_loop()
    hosts = await loop.run_in_executor(None, run_nmap_scan, network)

    # Detectar puertos web en paralelo
    tasks = [check_web_port(h["ip"]) for h in hosts]
    web_results = await asyncio.gather(*tasks)

    for host, (web_port, web_protocol) in zip(hosts, web_results):
        host["web_port"] = web_port
        host["web_protocol"] = web_protocol
        host["network"] = network

    return hosts


async def scan_networks(networks: list[str], scan_id: int):
    """Escanea múltiples subredes en paralelo y actualiza la base de datos."""

    # Escanear todas las redes en paralelo
    results_per_network = await asyncio.gather(
        *[scan_single_network(net) for net in networks],
        return_exceptions=True,
    )

    all_hosts: list[dict] = []
    for res in results_per_network:
        if isinstance(res, Exception):
            print(f"Scan error: {res}")
        else:
            all_hosts.extend(res)

    # Grid layout para dispositivos nuevos (por red)
    network_counters: dict[str, list[int]] = {}

    def next_position(network: str) -> tuple[float, float]:
        # Cada red en su propia fila de bloques para mantener orden visual
        if network not in network_counters:
            row_offset = len(network_counters) * 3
            network_counters[network] = [0, row_offset]
        col, row_base = network_counters[network]
        row = row_base + col // 5
        x = 150.0 + (col % 5) * 220.0
        y = 150.0 + row * 220.0
        network_counters[network][0] += 1
        return x, y

    with Session(engine) as session:
        # Marcar todos como offline; los encontrados se marcarán online
        for device in session.exec(select(Device)).all():
            # Solo marcar offline los de las redes escaneadas
            if device.network in networks or device.network is None:
                device.is_online = False

        for h in all_hosts:
            ip = h["ip"]
            icon, vendor = guess_icon_and_vendor(h["vendor_raw"])

            # Look up by MAC first so multi-homed devices (router with IPs in
            # multiple subnets) don't get created as separate records
            existing = None
            if h["mac"]:
                existing = session.exec(select(Device).where(Device.mac == h["mac"])).first()
            if not existing:
                existing = session.exec(select(Device).where(Device.ip == ip)).first()

            if existing:
                existing.is_online = True
                existing.last_seen = datetime.utcnow()
                existing.network = h["network"]
                if h["hostname"] and not existing.hostname:
                    existing.hostname = h["hostname"]
                if h["mac"] and not existing.mac:
                    existing.mac = h["mac"]
                if vendor and not existing.vendor:
                    existing.vendor = vendor
                if h["web_port"] and not existing.web_port:
                    existing.web_port = h["web_port"]
                    existing.web_protocol = h["web_protocol"]
                if icon != "unknown" and existing.icon in (None, "unknown"):
                    existing.icon = icon
            else:
                x, y = next_position(h["network"])
                device = Device(
                    ip=ip,
                    mac=h["mac"] or None,
                    hostname=h["hostname"] or None,
                    vendor=vendor or None,
                    icon=icon,
                    web_port=h["web_port"],
                    web_protocol=h["web_protocol"],
                    is_online=True,
                    last_seen=datetime.utcnow(),
                    network=h["network"],
                    x=x,
                    y=y,
                )
                session.add(device)

        scan_log = session.get(ScanLog, scan_id)
        if scan_log:
            scan_log.finished_at = datetime.utcnow()
            scan_log.devices_found = len(all_hosts)
            scan_log.status = "done"

        session.commit()
