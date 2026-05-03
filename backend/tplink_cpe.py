"""
TP-Link CPE (Pharos OS 2.x) REST client.
Uses urllib (sync) wrapped in asyncio.to_thread — more tolerant of
non-standard HTTP responses from embedded servers.

Auth flow:
  POST http://<ip>/  {"method":"do","login":{"username":"...","password":"<md5>"}}
  → {"stok":"<token>","error_code":0}
"""

import asyncio
import hashlib
import json as _json
import ssl
import urllib.error
import urllib.request
from typing import Optional

_stok_cache: dict[str, str] = {}
_scheme_cache: dict[str, str] = {}   # ip -> "http" or "https"


def _md5(password: str) -> str:
    # Pharos OS 2.x uses lowercase MD5
    return hashlib.md5(password.encode()).hexdigest()


def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _do_post(url: str, payload: dict, referer: str) -> dict:
    """Synchronous POST — called via asyncio.to_thread."""
    data = _json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Referer": referer,
            "Origin": referer.rstrip("/"),
            "Connection": "close",
        },
    )
    ctx = _ssl_ctx()
    with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return _json.loads(body)


def _detect_scheme_sync(ip: str) -> str:
    """Try HTTP first, then HTTPS. Return working scheme."""
    for scheme in ("http", "https"):
        url = f"{scheme}://{ip}/"
        req = urllib.request.Request(url, method="GET")
        try:
            ctx = _ssl_ctx()
            with urllib.request.urlopen(req, timeout=5, context=ctx):
                return scheme
        except urllib.error.HTTPError:
            # Got an HTTP error response — server IS there
            return scheme
        except Exception:
            continue
    return "http"


async def _get_scheme(ip: str) -> str:
    if ip not in _scheme_cache:
        scheme = await asyncio.to_thread(_detect_scheme_sync, ip)
        _scheme_cache[ip] = scheme
        print(f"[tplink_cpe] {ip} using {scheme}")
    return _scheme_cache[ip]


def _do_get(url: str) -> str:
    """Synchronous GET — returns response body."""
    req = urllib.request.Request(url, method="GET", headers={"Connection": "close"})
    ctx = _ssl_ctx()
    try:
        with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"


# Candidate login paths for different Pharos OS versions
_LOGIN_PATHS = ["/", "/cgi-bin/luci/", "/cgi-bin/luci"]


async def _login(ip: str, user: str, password: str) -> Optional[str]:
    scheme = await _get_scheme(ip)
    base = f"{scheme}://{ip}"
    payload = {"method": "do", "login": {"username": user, "password": _md5(password)}}

    # Debug: show what the root page looks like
    root_body = await asyncio.to_thread(_do_get, f"{base}/")
    print(f"[tplink_cpe] GET {ip}/ => {root_body[:300]}")

    for path in _LOGIN_PATHS:
        url = f"{base}{path}"
        try:
            data = await asyncio.to_thread(_do_post, url, payload, base + "/")
            print(f"[tplink_cpe] login {ip} path={path} response: {str(data)[:300]}")
            stok = data.get("stok", "")
            if stok:
                _stok_cache[ip] = stok
                _stok_cache[f"{ip}__path"] = path  # remember working path
                return stok
            if data.get("error_code") not in (None, -404, 404):
                # Got a real response (even an error) — this is the right path
                print(f"[tplink_cpe] login {ip} path={path} error_code={data.get('error_code')}")
                break
        except urllib.error.HTTPError as e:
            print(f"[tplink_cpe] login {ip} path={path} HTTP {e.code}")
            continue
        except Exception as e:
            print(f"[tplink_cpe] login {ip} path={path} error: {type(e).__name__}: {e}")
            continue
    return None


async def _post(ip: str, user: str, password: str, payload: dict) -> Optional[dict]:
    stok = _stok_cache.get(ip) or await _login(ip, user, password)
    if not stok:
        return None

    scheme = _scheme_cache.get(ip, "http")
    base = f"{scheme}://{ip}"
    login_path = _stok_cache.get(f"{ip}__path", "/")
    url = f"{base}{login_path}stok={stok}/ds"
    try:
        data = await asyncio.to_thread(_do_post, url, payload, base + "/")
        if data.get("error_code") == -40401:
            # Token expired — re-login once
            _stok_cache.pop(ip, None)
            stok = await _login(ip, user, password)
            if not stok:
                return None
            url = f"{base}{login_path}stok={stok}/ds"
            data = await asyncio.to_thread(_do_post, url, payload, base + "/")
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
