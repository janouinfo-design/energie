"""Async, READ-ONLY Navixy client.

Strictly read-only in this phase. Absolutely no write endpoints
(vehicle/update, rename, assign, sensor create, etc.) are implemented here.

All calls use the session `hash` from the environment (server-side only).
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("energy.navixy")

# Whitelist of allowed (read-only) methods. Any attempt to call something
# outside this set raises, as a defensive guard against accidental writes.
_ALLOWED_METHODS = {
    "user/get_info",
    "tracker/list",
    "vehicle/list",
    "tracker/get_states",
    "tracker/get_diagnostics",
    "tracker/get_readings",
    "tracker/get_fuel",
    "tracker/get_counters",
    "tracker/sensor/list",
    "track/list",
}


class NavixyError(Exception):
    pass


class NavixyClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 25.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("NAVIXY_API_KEY", "")
        self.base_url = (base_url or os.environ.get(
            "NAVIXY_BASE_URL", "https://api.eu.navixy.com/v2"
        )).rstrip("/")
        self.timeout = timeout
        if not self.api_key:
            logger.warning("NAVIXY_API_KEY is not configured")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def _post(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if method not in _ALLOWED_METHODS:
            raise NavixyError(f"Method '{method}' is not in the read-only whitelist")
        body = {"hash": self.api_key, **payload}
        url = f"{self.base_url}/{method}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
        if not data.get("success", False):
            status = data.get("status", {})
            raise NavixyError(
                f"{method} failed: {status.get('code')} {status.get('description')}"
            )
        return data

    # ---- read-only endpoints ----
    async def user_get_info(self) -> Dict[str, Any]:
        return await self._post("user/get_info", {})

    async def tracker_list(self) -> List[Dict[str, Any]]:
        data = await self._post("tracker/list", {})
        return data.get("list", [])

    async def vehicle_list(self) -> List[Dict[str, Any]]:
        data = await self._post("vehicle/list", {})
        return data.get("list", [])

    async def get_states(self, tracker_ids: List[int]) -> Dict[str, Any]:
        data = await self._post("tracker/get_states", {"trackers": tracker_ids})
        return data.get("states", {})

    async def get_diagnostics(self, tracker_id: int) -> Dict[str, Any]:
        return await self._post("tracker/get_diagnostics", {"tracker_id": tracker_id})

    async def get_fuel(self, tracker_id: int) -> Dict[str, Any]:
        return await self._post("tracker/get_fuel", {"tracker_id": tracker_id})

    async def get_counters(self, tracker_id: int) -> Dict[str, Any]:
        return await self._post("tracker/get_counters", {"tracker_id": tracker_id})

    async def sensor_list(self, tracker_id: int) -> List[Dict[str, Any]]:
        data = await self._post("tracker/sensor/list", {"tracker_id": tracker_id})
        return data.get("list", [])

    async def gather(self, coros: List[Any]) -> List[Any]:
        """Run coroutines concurrently, keeping exceptions per-item."""
        return await asyncio.gather(*coros, return_exceptions=True)
