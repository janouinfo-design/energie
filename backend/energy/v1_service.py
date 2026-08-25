"""Journal-facing v1 business service.

Reuses the existing EnergyService (which owns the single Navixy client and the
synced snapshots). This layer performs NO live Navixy calls per request: it
serves the last synced snapshot, so responses are fast (Journal timeout = 10s,
no retry) and there is no N+1 against Navixy.

Identity resolution:
  {ref} is the Journal's opaque vehicle_id. Resolution uses ONLY proven
  identifiers, in this order:
    1. ref == a known navixy_tracker_id (canonical internal identity)
    2. ref == a known Navixy vehicle_id (from vehicle/list) linked to a tracker
  Never by name / plate / brand / model. If nothing matches -> invalid mapping.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .service import EnergyService
from .v1_contract import empty_metric, to_journal_metric

# Metrics we expose per vehicle summary (fuel/thermal side + counters).
_SUMMARY_METRIC_KEYS = [
    "fuel_level", "fuel_consumed", "odometer", "engine_hours", "coolant_temp",
]


class EnergyV1Service:
    def __init__(self, energy: EnergyService) -> None:
        self.energy = energy

    async def _identities(self, tenant_id: str) -> List[Dict[str, Any]]:
        return await self.energy.get_mapping(tenant_id)

    async def resolve_ref(self, tenant_id: str, ref: str) -> Optional[Dict[str, Any]]:
        """Resolve opaque {ref} to a tracker identity using proven ids only."""
        identities = await self._identities(tenant_id)
        # try integer interpretation (tracker_id or navixy vehicle_id)
        ref_int: Optional[int] = None
        try:
            ref_int = int(ref)
        except (TypeError, ValueError):
            ref_int = None

        if ref_int is not None:
            for idt in identities:
                if idt.get("tracker_id") == ref_int:
                    return idt
            for idt in identities:
                if idt.get("vehicle_id") == ref_int:
                    return idt
        return None  # invalid mapping (explicit)

    async def vehicle_summary(self, tenant_id: str, ref: str) -> Tuple[int, Dict[str, Any]]:
        idt = await self.resolve_ref(tenant_id, ref)
        if idt is None:
            return 404, {
                "ref": ref,
                "tenant_id": tenant_id,
                "mapping": "INVALID",
                "reason": "ref could not be resolved to a proven tracker/vehicle identity",
            }
        tracker_id = idt.get("tracker_id")
        snap = await self.energy.get_metrics(tenant_id, tracker_id)
        metrics_by_key: Dict[str, Dict[str, Any]] = {}
        if snap:
            for m in snap.get("metrics", []):
                metrics_by_key[m.get("key")] = m

        out_metrics = {
            k: to_journal_metric(metrics_by_key.get(k)) for k in _SUMMARY_METRIC_KEYS
        }
        body = {
            "ref": ref,
            "tenant_id": tenant_id,
            "tracker_id": tracker_id,
            "vehicle_id": idt.get("vehicle_id"),
            "vin": idt.get("obd_vin"),
            "powertrain": idt.get("energy_type", "UNKNOWN"),   # UNKNOWN stays UNKNOWN
            "connection_status": idt.get("connection_status"),
            "metrics": out_metrics,
        }
        return 200, body

    async def trips_energy_batch(
        self, tenant_id: str, trips: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Enrich each trip independently. No fabricated consumption.

        Per-window historical energy is not available from the current
        telemetry snapshot, so energy metrics are returned honestly as
        UNAVAILABLE / value:null. Powertrain-specific fields are ALWAYS kept
        separate (fuel L vs electric kWh) and never merged.
        """
        # Pre-load identities once (avoid N+1).
        identities = {i.get("tracker_id"): i for i in await self._identities(tenant_id)}
        veh_index = {i.get("vehicle_id"): i for i in identities.values()}

        results: List[Dict[str, Any]] = []
        for trip in trips:
            trip_id = trip.get("trip_id", trip.get("id"))
            ref = trip.get("ref", trip.get("vehicle_id"))
            start = trip.get("start", trip.get("start_time", trip.get("from")))
            end = trip.get("end", trip.get("end_time", trip.get("to")))

            idt = None
            ref_int = None
            try:
                ref_int = int(ref)
            except (TypeError, ValueError):
                ref_int = None
            if ref_int is not None:
                idt = identities.get(ref_int) or veh_index.get(ref_int)

            if idt is None:
                results.append({
                    "trip_id": trip_id,
                    "ref": ref,
                    "tracker_id": None,
                    "status": "MAPPING_INVALID",
                    "powertrain": "UNKNOWN",
                    "window": {"start": start, "end": end},
                    "energy": self._empty_energy_block(
                        reason="ref could not be resolved to a proven tracker"
                    ),
                })
                continue

            # No per-window historical energy available -> honest UNAVAILABLE.
            results.append({
                "trip_id": trip_id,
                "ref": ref,
                "tracker_id": idt.get("tracker_id"),
                "status": "NO_ENERGY_DATA",
                "powertrain": idt.get("energy_type", "UNKNOWN"),
                "window": {"start": start, "end": end},
                "energy": self._empty_energy_block(
                    reason="per-trip historical energy not available from current telemetry"
                ),
            })
        return {"tenant_id": tenant_id, "count": len(results), "results": results}

    @staticmethod
    def _empty_energy_block(reason: str) -> Dict[str, Any]:
        """Powertrain-agnostic energy block; L and kWh kept strictly separate."""
        return {
            # ICE / HEV / PHEV fuel side
            "fuel_used_l": empty_metric(reason),
            "consumption_l_100": empty_metric(reason),
            # BEV / PHEV electric side (NEVER merged with litres)
            "energy_kwh": empty_metric(reason),
            "consumption_kwh_100": empty_metric(reason),
            "soc_start": empty_metric(reason),
            "soc_end": empty_metric(reason),
        }

    async def fleet_summary(self, tenant_id: str) -> Dict[str, Any]:
        """Aggregate ONLY what the individual data really supports.

        - counts by powertrain (UNKNOWN kept as UNKNOWN, never treated as ICE)
        - data-quality distribution from real per-tracker snapshots
        - never converts absence into a zero total; never merges L and kWh
        """
        identities = await self._identities(tenant_id)
        # powertrain distribution (proven only; all currently UNKNOWN)
        powertrain_counts: Dict[str, int] = {}
        for idt in identities:
            p = idt.get("energy_type", "UNKNOWN")
            powertrain_counts[p] = powertrain_counts.get(p, 0) + 1

        # fuel-level data quality across the fleet (real snapshots)
        quality = {"AVAILABLE": 0, "STALE": 0, "UNAVAILABLE": 0}
        fuel_available_trackers = 0
        for idt in identities:
            snap = await self.energy.get_metrics(tenant_id, idt.get("tracker_id"))
            avail = "UNAVAILABLE"
            if snap:
                for m in snap.get("metrics", []):
                    if m.get("key") == "fuel_level":
                        avail = m.get("availability", "UNAVAILABLE")
                        if avail == "ERROR":
                            avail = "UNAVAILABLE"
                        break
            quality[avail] = quality.get(avail, 0) + 1
            if avail in ("AVAILABLE", "STALE"):
                fuel_available_trackers += 1

        associated = sum(1 for i in identities if i.get("vehicle_id") is not None)

        return {
            "tenant_id": tenant_id,
            "trackers_total": len(identities),
            "trackers_associated": associated,
            "powertrain_distribution": powertrain_counts,
            "fuel_level_quality": quality,
            "fuel_trackers_with_data": fuel_available_trackers,
            # EV energy is not collected -> report explicitly, do NOT zero it out
            "ev_energy": {"available_trackers": 0, "status": "UNAVAILABLE"},
            "note": (
                "Aggregates reflect only proven data. Absence is reported as "
                "UNAVAILABLE, never as 0. Litres and kWh are never mixed."
            ),
        }
