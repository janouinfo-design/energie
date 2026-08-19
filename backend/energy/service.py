"""Energy foundation orchestration service.

Orchestrates a READ-ONLY Navixy collection run:
  1. resolve tenant (paas_id) via user/get_info
  2. list trackers + vehicles
  3. batch states, per-tracker diagnostics/fuel/counters/sensors (concurrent)
  4. normalize metrics, build capability map
  5. build canonical identity mapping + detect anomalies
  6. persist everything with provenance (sync_run_id, timestamps) and tenant_id

Multi-tenant: every stored document carries tenant_id (derived from paas_id).
Reads are always filtered by tenant_id.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .capability_service import (
    build_capability_map,
    build_metric_snapshot,
    detect_ev_sensors,
)
from .mapping_service import build_identities, detect_anomalies
from .models import SyncSummary
from .navixy_client import NavixyClient, NavixyError

logger = logging.getLogger("energy.service")

STALE_HOURS = float(os.environ.get("ENERGY_STALE_HOURS", "48"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EnergyService:
    def __init__(self, db, client: Optional[NavixyClient] = None) -> None:
        self.db = db
        self.client = client or NavixyClient()

    # ---------- persistence helpers ----------
    async def ensure_indexes(self) -> None:
        await self.db.energy_identities.create_index([("tenant_id", 1), ("tracker_id", 1)])
        await self.db.energy_identities.create_index([("tenant_id", 1), ("obd_vin", 1)])
        await self.db.energy_capabilities.create_index([("tenant_id", 1), ("tracker_id", 1)])
        await self.db.energy_metrics.create_index([("tenant_id", 1), ("tracker_id", 1)])
        await self.db.energy_anomalies.create_index([("tenant_id", 1), ("type", 1)])
        await self.db.energy_vehicles.create_index([("tenant_id", 1), ("vehicle_id", 1)])
        await self.db.energy_sync_runs.create_index([("tenant_id", 1), ("sync_run_id", 1)])

    # ---------- Navixy collection ----------
    async def _collect_tracker_detail(self, tracker_id: int) -> Dict[str, Any]:
        """Collect per-tracker read-only data; capture errors per call."""
        result: Dict[str, Any] = {"tracker_id": tracker_id, "errors": []}
        diag = await asyncio.gather(
            self.client.get_diagnostics(tracker_id),
            self.client.get_fuel(tracker_id),
            self.client.get_counters(tracker_id),
            self.client.sensor_list(tracker_id),
            return_exceptions=True,
        )
        keys = ["diagnostics", "fuel", "counters", "sensors"]
        for k, r in zip(keys, diag):
            if isinstance(r, Exception):
                result[k] = None
                result["errors"].append(f"{k}: {r}")
            else:
                result[k] = r
        return result

    async def run_sync(self, tenant_override: Optional[str] = None) -> SyncSummary:
        started = _now_iso()
        sync_run_id = str(uuid.uuid4())
        errors: List[str] = []

        if not self.client.configured:
            return SyncSummary(
                tenant_id=tenant_override or "unknown", sync_run_id=sync_run_id,
                started_at=started, finished_at=_now_iso(),
                errors=["NAVIXY_API_KEY not configured"],
            )

        # 1) tenant + now
        navixy_now = None
        tenant_id = tenant_override
        try:
            info = await self.client.user_get_info()
            paas = info.get("paas_id")
            tenant_id = tenant_override or f"paas_{paas}"
        except NavixyError as e:
            errors.append(f"user_get_info: {e}")
            tenant_id = tenant_override or "unknown"

        # 2) trackers + vehicles
        try:
            trackers = await self.client.tracker_list()
        except NavixyError as e:
            errors.append(f"tracker_list: {e}")
            trackers = []
        try:
            vehicles = await self.client.vehicle_list()
        except NavixyError as e:
            errors.append(f"vehicle_list: {e}")
            vehicles = []

        tracker_ids = [t.get("id") for t in trackers if t.get("id") is not None]

        # 3) states (batch)
        try:
            states = await self.client.get_states(tracker_ids)
            for st in states.values():
                navixy_now = navixy_now or st.get("last_update")
        except NavixyError as e:
            errors.append(f"get_states: {e}")
            states = {}

        # 3b) per-tracker details (concurrent, bounded)
        details: Dict[int, Dict[str, Any]] = {}
        sem = asyncio.Semaphore(6)

        async def _one(tid: int):
            async with sem:
                details[tid] = await self._collect_tracker_detail(tid)

        await asyncio.gather(*[_one(tid) for tid in tracker_ids])

        # derive navixy_now from fuel/counters user_time if still missing
        if not navixy_now:
            for d in details.values():
                fuel = d.get("fuel") or {}
                navixy_now = fuel.get("user_time") or navixy_now
                if navixy_now:
                    break

        # 4) normalize per tracker
        tracker_obd_vins: Dict[int, Optional[str]] = {}
        ev_presence: Dict[int, bool] = {}
        capability_docs: List[Dict[str, Any]] = []
        metric_docs: List[Dict[str, Any]] = []

        for tid in tracker_ids:
            d = details.get(tid, {})
            diagnostics = d.get("diagnostics") or {}
            fuel = d.get("fuel") or {}
            counters = (d.get("counters") or {}).get("list", []) if d.get("counters") else []
            sensors = d.get("sensors") or []
            state = states.get(str(tid), {}) or {}

            diag_states = diagnostics.get("states", {}) or {}
            tracker_obd_vins[tid] = diag_states.get("obd_vin")
            ev_presence[tid] = bool(detect_ev_sensors(sensors))

            reading_ts = diagnostics.get("update_time") or fuel.get("update_time")
            metrics = build_metric_snapshot(
                inputs=diagnostics.get("inputs", []) if isinstance(diagnostics.get("inputs"), list) else [],
                fuel_inputs=fuel.get("inputs", []) if isinstance(fuel.get("inputs"), list) else [],
                counters=counters,
                navixy_now=navixy_now,
                reading_ts=reading_ts,
                connection_status=state.get("connection_status"),
                stale_hours=STALE_HOURS,
            )
            caps = build_capability_map(sensors, metrics)

            metric_docs.append({
                "tenant_id": tenant_id, "sync_run_id": sync_run_id,
                "tracker_id": tid, "collected_at": started, "navixy_now": navixy_now,
                "metrics": [m.model_dump() for m in metrics],
            })
            capability_docs.append({
                "tenant_id": tenant_id, "sync_run_id": sync_run_id,
                "tracker_id": tid, "collected_at": started,
                "ev_sensors": detect_ev_sensors(sensors),
                "configured_sensor_count": len(sensors),
                "capabilities": [c.model_dump() for c in caps],
            })

        # 5) mapping + anomalies
        identities = build_identities(
            tenant_id, trackers, states, tracker_obd_vins, vehicles
        )
        anomalies = detect_anomalies(
            tenant_id, identities, vehicles, ev_presence, STALE_HOURS, navixy_now
        )

        # 6) persist (replace tenant snapshot atomically per collection)
        await self.ensure_indexes()
        await self._replace_tenant("energy_identities", tenant_id,
                                   [{**i.model_dump(), "sync_run_id": sync_run_id} for i in identities])
        await self._replace_tenant("energy_vehicles", tenant_id,
                                   [{"tenant_id": tenant_id, "sync_run_id": sync_run_id,
                                     "vehicle_id": v.get("id"), "label": v.get("label"),
                                     "vin": v.get("vin"), "model": v.get("model"),
                                     "reg_number": v.get("reg_number"),
                                     "tracker_id": v.get("tracker_id")} for v in vehicles])
        await self._replace_tenant("energy_capabilities", tenant_id, capability_docs)
        await self._replace_tenant("energy_metrics", tenant_id, metric_docs)
        await self._replace_tenant("energy_anomalies", tenant_id,
                                   [{**a.model_dump(), "sync_run_id": sync_run_id} for a in anomalies])

        summary = SyncSummary(
            tenant_id=tenant_id, sync_run_id=sync_run_id,
            started_at=started, finished_at=_now_iso(), navixy_now=navixy_now,
            trackers=len(trackers), vehicles=len(vehicles),
            anomalies=len(anomalies), errors=errors,
        )
        await self.db.energy_sync_runs.insert_one(summary.model_dump())
        return summary

    async def _replace_tenant(self, coll: str, tenant_id: str, docs: List[Dict[str, Any]]) -> None:
        await self.db[coll].delete_many({"tenant_id": tenant_id})
        if docs:
            await self.db[coll].insert_many(docs)

    # ---------- read APIs ----------
    async def get_mapping(self, tenant_id: str) -> List[Dict[str, Any]]:
        return await self.db.energy_identities.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(1000)

    async def get_anomalies(self, tenant_id: str) -> List[Dict[str, Any]]:
        return await self.db.energy_anomalies.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(2000)

    async def get_capabilities(self, tenant_id: str, tracker_id: int) -> Optional[Dict[str, Any]]:
        return await self.db.energy_capabilities.find_one(
            {"tenant_id": tenant_id, "tracker_id": tracker_id}, {"_id": 0}
        )

    async def get_metrics(self, tenant_id: str, tracker_id: int) -> Optional[Dict[str, Any]]:
        return await self.db.energy_metrics.find_one(
            {"tenant_id": tenant_id, "tracker_id": tracker_id}, {"_id": 0}
        )

    async def latest_tenant(self) -> Optional[str]:
        doc = await self.db.energy_sync_runs.find_one(sort=[("finished_at", -1)])
        return doc.get("tenant_id") if doc else None

    async def list_sync_runs(self, tenant_id: str) -> List[Dict[str, Any]]:
        return await self.db.energy_sync_runs.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).sort("finished_at", -1).to_list(50)
