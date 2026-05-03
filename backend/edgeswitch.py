import time
import httpx

_sessions: dict[str, dict] = {}   # ip -> {cookie, ts}
_traffic_prev: dict[int, dict] = {}


async def _login(ip: str, user: str, password: str) -> str | None:
    for scheme in ("https", "http"):
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                r = await client.post(
                    f"{scheme}://{ip}/api/v1.0/user/login",
                    json={"username": user, "password": password},
                )
                if r.status_code == 200:
                    cookie = next(iter(r.cookies.values()), None)
                    if cookie:
                        _sessions[ip] = {"cookie": cookie, "scheme": scheme, "ts": time.time()}
                        return cookie
        except Exception as e:
            print(f"EdgeSwitch {ip} login ({scheme}) error: {e}")
    return None


async def _get(ip: str, user: str, password: str, path: str):
    now = time.time()
    session = _sessions.get(ip)

    if not session or now - session["ts"] > 300:
        if not await _login(ip, user, password):
            return None
        session = _sessions[ip]

    scheme = session.get("scheme", "https")
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            r = await client.get(
                f"{scheme}://{ip}{path}",
                cookies={"PHPSESSID": session["cookie"]},
            )
            if r.status_code == 401:
                _sessions.pop(ip, None)
                if await _login(ip, user, password):
                    return await _get(ip, user, password, path)
                return None
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        print(f"EdgeSwitch {ip} GET {path} error: {e}")
    return None


async def get_fdb(ip: str, user: str, password: str) -> list[dict]:
    """MAC address table: which MAC is on which port."""
    data = await _get(ip, user, password, "/api/v1.0/switching/fdb")
    if isinstance(data, dict):
        return data.get("fdb_table", [])
    return []


async def get_arp(ip: str, user: str, password: str) -> list[dict]:
    """ARP table: IP ↔ MAC mappings."""
    data = await _get(ip, user, password, "/api/v1.0/routing/arp")
    if isinstance(data, dict):
        return data.get("arp_table", [])
    return []


async def get_traffic(device_id: int, ip: str, user: str, password: str) -> dict:
    """Interface rx/tx Mbps."""
    data = await _get(ip, user, password, "/api/v1.0/interfaces/")
    now = time.time()

    ifaces_raw: list[dict] = []
    if isinstance(data, dict):
        ifaces_raw = data.get("interfaces", [])

    current: dict[str, dict] = {}
    for iface in ifaces_raw:
        name = iface.get("intf_name", "")
        try:
            current[name] = {
                "rx": int(iface.get("rx_bytes", 0)),
                "tx": int(iface.get("tx_bytes", 0)),
                "up": iface.get("link_status", "") == "up",
            }
        except (ValueError, TypeError):
            pass

    result: dict = {"rx_mbps": 0.0, "tx_mbps": 0.0, "interfaces": []}
    prev = _traffic_prev.get(device_id)
    if prev:
        dt = now - prev["ts"]
        if dt > 0:
            total_rx = total_tx = 0.0
            for name, cur in current.items():
                if name in prev["ifaces"]:
                    p = prev["ifaces"][name]
                    rx_mbps = max(0, cur["rx"] - p["rx"]) / dt * 8 / 1e6
                    tx_mbps = max(0, cur["tx"] - p["tx"]) / dt * 8 / 1e6
                    total_rx += rx_mbps
                    total_tx += tx_mbps
                    if cur["up"] and (rx_mbps > 0.001 or tx_mbps > 0.001):
                        result["interfaces"].append({
                            "name": name,
                            "rx_mbps": round(rx_mbps, 2),
                            "tx_mbps": round(tx_mbps, 2),
                        })
            result["rx_mbps"] = round(total_rx, 2)
            result["tx_mbps"] = round(total_tx, 2)

    _traffic_prev[device_id] = {"ts": now, "ifaces": current}
    return result
