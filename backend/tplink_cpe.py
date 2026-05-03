"""
TP-Link CPE (Pharos OS) REST client.
Tested with CPE210, CPE510, CPE605, WBS series running Pharos OS 2.x+

Auth flow:
  POST http://<ip>/  {"method":"do","login":{"username":"...","password":"<MD5_UPPER>"}}
  → {"stok":"<token>","error_code":0}

Subsequent requests:
  POST http://<ip>/stok=<token>/ds  {<query>}
"""

import hashlib
from typing import Optional

import httpx

# Per-device session cache: ip -> stok token
_stok_cache: dict[str, str] = {}


def _md5(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest().upper()


def _client(ip: str) -> httpx.AsyncClient:
    """HttpClient configured for Pharos OS embedded web server."""
    return httpx.AsyncClient(
        verify=False,
        timeout=8,
        http1=True,
        http2=False,
        headers={
            "Content-Type": "application/json",
            "Referer": f"http://{ip}/",
            "Origin": f"http://{ip}",
        },
    )


async def _login(ip: str, user: str, password: str) -> Optional[str]:
    url = f"http://{ip}/"
    payload = {"method": "do", "login": {"username": user, "password": _md5(password)}}
    try:
        async with _client(ip) as client:
            resp = await client.post(url, json=payload)
            print(f"[tplink_cpe] login {ip} status={resp.status_code} body={resp.text[:300]}")
            data = resp.json()
            stok = data.get("stok", "")
            if stok:
                _stok_cache[ip] = stok
                return stok
            print(f"[tplink_cpe] login {ip} no stok: error_code={data.get('error_code')}")
    except Exception as e:
        print(f"[tplink_cpe] login {ip} error: {type(e).__name__}: {e}")
    return None


async def _post(ip: str, user: str, password: str, payload: dict) -> Optional[dict]:
    stok = _stok_cache.get(ip) or await _login(ip, user, password)
    if not stok:
        return None

    url = f"http://{ip}/stok={stok}/ds"
    try:
        async with _client(ip) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            if data.get("error_code") == -40401:
                # Token expired — re-login once
                _stok_cache.pop(ip, None)
                stok = await _login(ip, user, password)
                if not stok:
                    return None
                url = f"http://{ip}/stok={stok}/ds"
                resp = await client.post(url, json=payload)
                data = resp.json()
            return data
    except Exception as e:
        print(f"[tplink_cpe] request {ip} error: {type(e).__name__}: {e}")
        _stok_cache.pop(ip, None)
    return None


async def get_stations(ip: str, user: str, password: str) -> list[dict]:
    """
    Return list of connected wireless clients.
    Each entry: {"mac": "AA:BB:CC:DD:EE:FF", "signal": -70, ...}
    """
    data = await _post(ip, user, password, {
        "method": "get",
        "wireless": {"wlan_station_list": {"name": "station_table"}},
    })
    if not data:
        return []

    stations = data.get("wireless", {}).get("wlan_station_list", [])
    if isinstance(stations, list):
        return stations
    if isinstance(stations, dict):
        return list(stations.values())
    return []


async def get_status(ip: str, user: str, password: str) -> Optional[dict]:
    """Return basic device status (mode, SSID, channel, etc.)"""
    data = await _post(ip, user, password, {
        "method": "get",
        "wireless": {"wlan": {"name": "wlan"}},
    })
    if not data:
        return None
    return data.get("wireless", {}).get("wlan")
