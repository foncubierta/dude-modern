"""
TP-Link CPE (Pharos OS 2.x) REST client.
Pharos OS 2.2.x API: POST https://<ip>/ with JSON, stok-based auth.
"""

import asyncio
import hashlib
import json as _json
import ssl
import urllib.error
import urllib.request
from typing import Optional

_stok_cache: dict[str, str] = {}
_scheme_cache: dict[str, str] = {}


def _md5(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()


def _ssl_ctx() -> ssl.SSLContext:
    """Permissive SSL — CPE uses self-signed cert + old TLS ciphers."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_ciphers("ALL:@SECLEVEL=0")
    try:
        ctx.minimum_version = ssl.TLSVersion.TLSv1
    except AttributeError:
        pass
    return ctx


def _detect_scheme_sync(ip: str) -> str:
    """
    Detect scheme by sending GET without following redirects.
    If Location header points to https, return https.
    """
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            return None  # block all redirects

    opener = urllib.request.build_opener(
        _NoRedirect(),
        urllib.request.HTTPSHandler(context=_ssl_ctx()),
    )
    try:
        opener.open(f"http://{ip}/", timeout=5)
        return "http"
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location", "")
        print(f"[tplink_cpe] redirect {ip} → {loc}", flush=True)
        if "https" in loc:
            return "https"
        return "http"
    except Exception:
        pass

    # Fall back: try HTTPS directly
    try:
        req = urllib.request.Request(f"https://{ip}/", method="GET")
        with urllib.request.urlopen(req, timeout=5, context=_ssl_ctx()) as _:
            return "https"
    except urllib.error.HTTPError:
        return "https"  # got HTTP response = HTTPS is up
    except Exception:
        pass

    return "http"


async def _get_scheme(ip: str) -> str:
    if ip not in _scheme_cache:
        scheme = await asyncio.to_thread(_detect_scheme_sync, ip)
        _scheme_cache[ip] = scheme
        print(f"[tplink_cpe] {ip} using {scheme}", flush=True)
    return _scheme_cache[ip]


def _do_post(url: str, payload: dict, referer: str) -> dict:
    """Synchronous POST."""
    data = _json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "Referer": referer,
            "Origin": referer.rstrip("/"),
            "Connection": "close",
        },
    )
    with urllib.request.urlopen(req, timeout=8, context=_ssl_ctx()) as resp:
        return _json.loads(resp.read().decode("utf-8", errors="replace"))


# Try all combinations: both schemes × multiple paths
_LOGIN_CANDIDATES = [
    ("https", "/"),
    ("http",  "/"),
    ("https", "/cgi-bin/luci/"),
    ("http",  "/cgi-bin/luci/"),
]


async def _login(ip: str, user: str, password: str) -> Optional[str]:
    payload = {"method": "do", "login": {"username": user, "password": _md5(password)}}

    for scheme, path in _LOGIN_CANDIDATES:
        base = f"{scheme}://{ip}"
        url = f"{base}{path}"
        try:
            data = await asyncio.to_thread(_do_post, url, payload, base + "/")
            print(f"[tplink_cpe] login {ip} {scheme}{path} → {str(data)[:200]}", flush=True)
            stok = data.get("stok", "")
            if stok:
                _stok_cache[ip] = stok
                _stok_cache[f"{ip}__base"] = base
                _stok_cache[f"{ip}__path"] = path
                return stok
            err = data.get("error_code")
            if err is not None and err not in (-404, 404):
                # Real response on this path — credentials wrong or other error
                print(f"[tplink_cpe] login {ip} error_code={err}", flush=True)
                return None  # No point trying other paths
        except urllib.error.HTTPError as e:
            print(f"[tplink_cpe] login {ip} {scheme}{path} HTTP {e.code}", flush=True)
        except Exception as e:
            print(f"[tplink_cpe] login {ip} {scheme}{path} {type(e).__name__}: {e}", flush=True)

    return None


async def _post(ip: str, user: str, password: str, payload: dict) -> Optional[dict]:
    stok = _stok_cache.get(ip) or await _login(ip, user, password)
    if not stok:
        return None

    base = _stok_cache.get(f"{ip}__base", f"http://{ip}")
    path = _stok_cache.get(f"{ip}__path", "/")
    url = f"{base}{path}stok={stok}/ds"
    try:
        data = await asyncio.to_thread(_do_post, url, payload, base + "/")
        if data.get("error_code") == -40401:
            _stok_cache.pop(ip, None)
            stok = await _login(ip, user, password)
            if not stok:
                return None
            url = f"{base}{path}stok={stok}/ds"
            data = await asyncio.to_thread(_do_post, url, payload, base + "/")
        return data
    except Exception as e:
        print(f"[tplink_cpe] request {ip} {type(e).__name__}: {e}", flush=True)
        _stok_cache.pop(ip, None)
    return None


async def get_stations(ip: str, user: str, password: str) -> list[dict]:
    """Return list of connected wireless clients."""
    print(f"[tplink_cpe] get_stations called for {ip}", flush=True)
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
