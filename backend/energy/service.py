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
from .enums import ChangeType
from .ev_feasibility import assess_tracker, summarize as ev_summarize
from .mapping_proposals import build_proposals
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
        await self.db.energy_mapping_history.create_index([("tenant_id", 1), ("tracker_id", 1)])
        await self.db.energy_mapping_changes.create_index([("tenant_id", 1), ("detected_at", -1)])
        await self.db.energy_proposals.create_index([("tenant_id", 1), ("tracker_id", 1)])
        await self.db.energy_ev_feasibility.create_index([("tenant_id", 1), ("tracker_id", 1)])

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
        ev_sensors_by_tracker: Dict[int, List[str]] = {}
        model_by_tracker: Dict[int, Optional[str]] = {}
        t_by_id: Dict[int, Dict[str, Any]] = {t.get("id"): t for t in trackers}
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
            ev_sensors_by_tracker[tid] = detect_ev_sensors(sensors)
            model_by_tracker[tid] = (t_by_id.get(tid, {}).get("source", {}) or {}).get("model")

        # 5) mapping + anomalies
        identities = build_identities(
            tenant_id, trackers, states, tracker_obd_vins, vehicles
        )
        anomalies = detect_anomalies(
            tenant_id, identities, vehicles, ev_presence, STALE_HOURS, navixy_now
        )

        # 5b) mapping correction proposals (NO Navixy writes)
        proposals = build_proposals(identities, vehicles)

        # 5c) EV feasibility assessment (evidence-based, real device models)
        ev_assessments = [
            assess_tracker(
                tracker_id=idt.tracker_id,
                model=model_by_tracker.get(idt.tracker_id),
                obd_vin=idt.obd_vin,
                vehicle_id=idt.vehicle_id,
                mapping_confidence=idt.confidence.value,
                ev_sensors=ev_sensors_by_tracker.get(idt.tracker_id, []),
            )
            for idt in identities
        ]

        # 5d) mapping history + change detection (activates MAPPING_CHANGED)
        changes = await self._update_mapping_history(
            tenant_id, sync_run_id, identities, started
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
        await self._replace_tenant("energy_proposals", tenant_id,
                                   [{**p, "tenant_id": tenant_id, "sync_run_id": sync_run_id}
                                    for p in proposals])
        await self._replace_tenant("energy_ev_feasibility", tenant_id,
                                   [{**a, "tenant_id": tenant_id, "sync_run_id": sync_run_id}
                                    for a in ev_assessments])
        # mapping_changes are appended (audit trail), not replaced
        if changes:
            await self.db.energy_mapping_changes.insert_many(changes)

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

    async def _update_mapping_history(
        self, tenant_id: str, sync_run_id: str, identities: List[Any], now_iso: str,
    ) -> List[Dict[str, Any]]:
        """Upsert per-tracker mapping history and emit change events.

        History key = tracker_id. We record vehicle_id, obd_vin, source,
        confidence, first_seen, last_seen. Comparing the previous stored state
        to the current one yields MAPPING_CHANGED events. No Navixy writes.
        """
        changes: List[Dict[str, Any]] = []
        for idt in identities:
            prev = await self.db.energy_mapping_history.find_one(
                {"tenant_id": tenant_id, "tracker_id": idt.tracker_id}
            )
            cur = {
                "vehicle_id": idt.vehicle_id,
                "obd_vin": idt.obd_vin,
                "confidence": idt.confidence.value,
                "source": idt.vin_source.value,
            }
            if prev is None:
                await self.db.energy_mapping_history.insert_one({
                    "tenant_id": tenant_id, "tracker_id": idt.tracker_id,
                    **cur, "first_seen": now_iso, "last_seen": now_iso,
                    "last_sync_run_id": sync_run_id,
                })
                if idt.vehicle_id is not None or idt.obd_vin:
                    changes.append(self._change(
                        tenant_id, ChangeType.NEW_ASSOCIATION, idt.tracker_id,
                        now_iso, sync_run_id, None, cur,
                        f"First observation of tracker {idt.tracker_id}",
                    ))
                continue

            # detect changes vs previous
            if prev.get("obd_vin") and idt.obd_vin and prev["obd_vin"] != idt.obd_vin:
                changes.append(self._change(
                    tenant_id, ChangeType.VIN_CHANGE, idt.tracker_id, now_iso,
                    sync_run_id, {"obd_vin": prev.get("obd_vin")},
                    {"obd_vin": idt.obd_vin},
                    "OBD VIN changed on this tracker",
                ))
            if prev.get("vehicle_id") != idt.vehicle_id:
                if prev.get("vehicle_id") is not None and idt.vehicle_id is None:
                    ctype = ChangeType.ASSOCIATION_REMOVED
                elif prev.get("vehicle_id") is None and idt.vehicle_id is not None:
                    ctype = ChangeType.NEW_ASSOCIATION
                else:
                    ctype = ChangeType.TRACKER_CHANGE
                changes.append(self._change(
                    tenant_id, ctype, idt.tracker_id, now_iso, sync_run_id,
                    {"vehicle_id": prev.get("vehicle_id")},
                    {"vehicle_id": idt.vehicle_id},
                    "Vehicle association changed",
                ))

            await self.db.energy_mapping_history.update_one(
                {"_id": prev["_id"]},
                {"$set": {**cur, "last_seen": now_iso, "last_sync_run_id": sync_run_id}},
            )
        return changes

    @staticmethod
    def _change(tenant_id, ctype, tracker_id, now_iso, sync_run_id, before, after, detail):
        return {
            "tenant_id": tenant_id, "type": ctype.value, "tracker_id": tracker_id,
            "detected_at": now_iso, "sync_run_id": sync_run_id,
            "before": before, "after": after, "detail": detail,
        }


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

    async def get_proposals(self, tenant_id: str) -> List[Dict[str, Any]]:
        return await self.db.energy_proposals.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(2000)

    async def get_ev_feasibility(self, tenant_id: str) -> Dict[str, Any]:
        items = await self.db.energy_ev_feasibility.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(1000)
        return {"summary": ev_summarize(items), "assessments": items}

    async def get_mapping_changes(self, tenant_id: str) -> List[Dict[str, Any]]:
        return await self.db.energy_mapping_changes.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).sort("detected_at", -1).to_list(2000)

    async def get_readiness(self, tenant_id: str) -> Dict[str, Any]:
        """Compute identity-reliability KPIs to decide if Energy->Journal (A-E)
        can start. Only real, stored data is used."""
        identities = await self.get_mapping(tenant_id)
        vehicles = await self.db.energy_vehicles.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(1000)
        metrics_docs = await self.db.energy_metrics.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(1000)
        anomalies = await self.get_anomalies(tenant_id)

        n_trackers = len(identities)
        # physical OBD trackers only (exclude smartphone app trackers)
        def _is_phone(m):
            m = (m or "").lower()
            return "ios" in m or "mobile" in m or "xgps" in m
        physical = [i for i in identities if not _is_phone(i.get("device_model"))]
        n_physical = len(physical)

        assoc_trackers = [i for i in identities if i.get("vehicle_id") is not None]
        vin_present = [i for i in physical if i.get("obd_vin")]
        linked_vehicle_ids = {i.get("vehicle_id") for i in assoc_trackers}
        assoc_vehicles = [v for v in vehicles if v.get("vehicle_id") in linked_vehicle_ids]

        # thermal coverage: trackers with a fuel value present (any freshness)
        def _has_fuel(doc):
            for m in doc.get("metrics", []):
                if m.get("key") in ("fuel_level", "fuel_consumed") and m.get("value") is not None:
                    return True
            return False
        thermal_trackers = [d for d in metrics_docs if _has_fuel(d)]

        # EV coverage: trackers with any EV metric AVAILABLE (currently expected 0)
        ev_feas = await self.db.energy_ev_feasibility.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(1000)
        ev_collectable = [a for a in ev_feas if a.get("ev_sensors_configured")]

        # freshness by connection/last_update already reflected in STALE_DATA anomalies
        stale_count = sum(1 for a in anomalies if a.get("type") == "STALE_DATA")

        blocking = [a for a in anomalies if a.get("type") in ("VIN_CONFLICT", "VIN_DUPLICATE")]

        def pct(a, b):
            return round(100.0 * a / b, 1) if b else 0.0

        kpis = {
            "trackers_total": n_trackers,
            "physical_obd_trackers": n_physical,
            "trackers_associated": len(assoc_trackers),
            "pct_trackers_associated": pct(len(assoc_trackers), n_trackers),
            "vehicles_total": len(vehicles),
            "vehicles_associated": len(assoc_vehicles),
            "pct_vehicles_associated": pct(len(assoc_vehicles), len(vehicles)),
            "vin_coverage_physical": pct(len(vin_present), n_physical),
            "thermal_energy_coverage": pct(len(thermal_trackers), n_trackers),
            "ev_energy_coverage": pct(len(ev_collectable), n_trackers),
            "stale_trackers": stale_count,
            "blocking_anomalies": len(blocking),
        }

        ready = (kpis["pct_trackers_associated"] >= 90.0
                 and kpis["blocking_anomalies"] == 0)
        recommendation = (
            "READY_FOR_A_E" if ready else "NOT_READY_FOR_A_E"
        )
        reasons = []
        if kpis["pct_trackers_associated"] < 90.0:
            reasons.append(
                f"Only {kpis['pct_trackers_associated']}% of trackers are reliably "
                f"associated to a vehicle (target >=90%)."
            )
        if kpis["blocking_anomalies"] > 0:
            reasons.append(f"{kpis['blocking_anomalies']} blocking VIN anomalies present.")
        if not reasons:
            reasons.append("Identity reliability sufficient to start the contract.")

        return {
            "tenant_id": tenant_id,
            "recommendation": recommendation,
            "kpis": kpis,
            "reasons": reasons,
        }

