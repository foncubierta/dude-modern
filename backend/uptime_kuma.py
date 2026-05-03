"""
Uptime Kuma integration via uptime-kuma-api (Socket.IO wrapper).
All functions run the sync API in asyncio.to_thread to avoid blocking.
"""

import asyncio
from typing import Optional


def _get_api(url: str):
    from uptime_kuma_api import UptimeKumaApi
    return UptimeKumaApi(url)


async def add_monitor(
    uk_url: str, user: str, password: str,
    name: str, target: str, is_http: bool = False,
) -> int:
    """Create a monitor in Uptime Kuma. Returns the new monitor ID."""
    def _do():
        from uptime_kuma_api import UptimeKumaApi
        api = UptimeKumaApi(uk_url)
        try:
            api.login(user, password)
            # Use api.call() directly so we can include 'conditions'
            # which newer UK versions require (NOT NULL) but the library ignores.
            monitor = {
                "name": name,
                "type": "http" if is_http else "ping",
                "interval": 60,
                "maxretries": 1,
                "retryInterval": 60,
                "timeout": 48,
                "upsideDown": False,
                "notificationIDList": {},
                "conditions": [],          # required by UK ≥ 2.x
                "accepted_statuscodes": ["200-299"],
            }
            if is_http:
                monitor["url"] = target
            else:
                monitor["hostname"] = target

            r = api.call("add", monitor)
            if not r.get("ok"):
                raise Exception(r.get("msg", "Unknown error from Uptime Kuma"))
            return r["monitorID"]
        finally:
            try:
                api.disconnect()
            except Exception:
                pass

    return await asyncio.to_thread(_do)


async def delete_monitor(uk_url: str, user: str, password: str, monitor_id: int):
    """Remove a monitor from Uptime Kuma."""
    def _do():
        from uptime_kuma_api import UptimeKumaApi
        api = UptimeKumaApi(uk_url)
        try:
            api.login(user, password)
            api.delete_monitor(monitor_id)
        finally:
            try:
                api.disconnect()
            except Exception:
                pass

    await asyncio.to_thread(_do)


async def test_connection(uk_url: str, user: str, password: str) -> bool:
    """Return True if we can login successfully."""
    def _do():
        from uptime_kuma_api import UptimeKumaApi
        api = UptimeKumaApi(uk_url)
        try:
            api.login(user, password)
            return True
        except Exception:
            return False
        finally:
            try:
                api.disconnect()
            except Exception:
                pass

    return await asyncio.to_thread(_do)
