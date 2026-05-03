"""
TP-Link CPE (Pharos OS 2.x) REST client.
Tested with CPE210/CPE510 running Pharos OS 2.2.x

Auth flow:
  POST http://<ip>/  {"method":"do","login":{"username":"...","password":"<md5_lower>"}}
  → {"stok":"<token>","error_code":0}

Subsequent requests:
  POST http://<ip>/stok=<token>/ds  {<query>}
"""

import hashlib
from typing import Optional

import httpx

_stok_cache: dict[str, str] = {}
_base_url_cache: dict[str, str] = {}   # ip -> "http://..." or "https://..."


def _md5(password: str) -> str:
    # Pharos OS 2.x uses lowercase MD5
    return hashlib.md5(password.encode()).hexdigest()


async def _detect_base_url(ip: str) -> str:
    """Try HTTP first, then HTTPS. Return working base URL."""
    if ip in _base_url_cache:
        return _base_url_cache[ip]
    for scheme in ("http", "https"):
        url = f"{scheme}://{ip}/"
        try:
            async with httpx.AsyncClient(verify=False, timeout=5, follow_redirects=False) as c:
                resp = await c.get(url)
                # Any response (even 302/401) means the server is there
                _base_url_cache[ip] = f"{scheme}://{ip}"
                return _base_url_cache[ip]
        except Exception:
            continue
    # Default fallback
    _base_url_cache[ip] = f"http://{ip}"
    return _base_url_cache[ip]


def _client(ip: str, base: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        verify=False,
        timeout=8,
        http1=True,
        http2=False,
        follow_redirects=True,
        headers={
            "Content-Type": "application/json",
            "Referer": f"{base}/",
            "Origin": base,
        },
    )


async def _login(ip: str, user: str, password: str) -> Optional[str]:
    base = await _detect_base_url(ip)
    url = f"{base}/"
    payload = {"method": "do", "login": {"username": user, "password": _md5(password)}}
    try:
        async with _client(ip, base) as client:
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

    base = _base_url_cache.get(ip, f"http://{ip}")
    url = f"{base}/stok={stok}/ds"
    try:
        async with _client(ip, base) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            if data.get("error_code") == -40401:
                # Token expired — re-login once
                _stok_cache.pop(ip, None)
                stok = await _login(ip, user, password)
                if not stok:
                    return None
                url = f"{base}/stok={stok}/ds"
                resp = await client.post(url, json=payload)
                data = resp.json()
            return data
    except Exception as e:
        print(f"[tplink_cpe] request {ip} error: {type(e).__name__}: {e}")
        _stok_cache.pop(ip, None)
    return None


async def get_stations(ip: str, user: str, password: str) -> list[dict]:
    """Return list of connected wireless clients."""
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
