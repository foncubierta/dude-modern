import asyncio
import time
import httpx

_traffic_prev: dict[int, dict] = {}


async def _api_get(ip: str, user: str, password: str, path: str) -> list[dict]:
    url = f"http://{ip}/rest{path}"
    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            r = await client.get(url, auth=(user, password))
            if r.status_code == 200:
                return r.json()
            print(f"MikroTik {ip} HTTP {r.status_code} on {path}")
    except Exception as e:
        print(f"MikroTik {ip} error on {path}: {e}")
    return []


async def get_arp_table(ip: str, user: str, password: str) -> list[dict]:
    return await _api_get(ip, user, password, "/ip/arp")


async def ping_device(router_ip: str, user: str, password: str,
                      target_ip: str, count: int = 2) -> bool:
    """
    Ask the MikroTik to ping target_ip from its own interfaces.
    Returns True if at least one reply was received.
    Useful for checking reachability of devices on subnets the backend
    cannot directly probe.
    """
    url = f"http://{router_ip}/rest/tool/ping"
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            r = await client.post(url, auth=(user, password), json={
                "address": target_ip,
                "count":   str(count),
                "interval": "0.1",
            })
            if r.status_code != 200:
                return False
            results = r.json()
            # Each result has "received" field; success if any reply came back
            return any(int(res.get("received", 0)) > 0 for res in results)
    except Exception as e:
        print(f"MikroTik ping {router_ip}→{target_ip} error: {e}")
        return False


async def ping_devices(router_ip: str, user: str, password: str,
                       target_ips: list[str], concurrency: int = 20) -> set[str]:
    """
    Ping multiple IPs from the MikroTik in parallel (capped at concurrency).
    Returns the set of IPs that responded.
    """
    sem = asyncio.Semaphore(concurrency)

    async def _check(ip: str) -> str | None:
        async with sem:
            ok = await ping_device(router_ip, user, password, ip)
            return ip if ok else None

    results = await asyncio.gather(*[_check(ip) for ip in target_ips])
    return {ip for ip in results if ip}


async def get_dhcp_leases(ip: str, user: str, password: str) -> list[dict]:
    """DHCP leases with active-hostname — the name the client announced."""
    return await _api_get(ip, user, password, "/ip/dhcp-server/lease")


async def get_traffic(device_id: int, ip: str, user: str, password: str) -> dict:
    ifaces = await _api_get(ip, user, password, "/interface")
    now = time.time()

    current: dict[str, dict] = {}
    for iface in ifaces:
        name = iface.get("name", "")
        try:
            current[name] = {
                "rx": int(iface.get("rx-byte", 0)),
                "tx": int(iface.get("tx-byte", 0)),
                "running": iface.get("running", False),
                "type": iface.get("type", ""),
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
                    rx_bps = max(0, cur["rx"] - p["rx"]) / dt * 8 / 1e6
                    tx_bps = max(0, cur["tx"] - p["tx"]) / dt * 8 / 1e6
                    total_rx += rx_bps
                    total_tx += tx_bps
                    if cur["running"]:
                        result["interfaces"].append({
                            "name": name,
                            "rx_mbps": round(rx_bps, 2),
                            "tx_mbps": round(tx_bps, 2),
                        })
            result["rx_mbps"] = round(total_rx, 2)
            result["tx_mbps"] = round(total_tx, 2)

    _traffic_prev[device_id] = {"ts": now, "ifaces": current}
    return result
