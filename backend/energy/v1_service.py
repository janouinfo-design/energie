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


def _computed_metric(value, unit: str, reason: str) -> Dict[str, Any]:
    """A Journal envelope for an aggregate value derived from real data.

    A value computed from other data is ESTIMATED (per contract rules) and its
    source is CALCULATED (never a sensor source for a derived value).
    """
    return {
        "value": value,
        "unit": unit,
        "unit_verified": True,
        "availability": "AVAILABLE",
        "measurement_type": "ESTIMATED",
        "source": "CALCULATED",
        "timestamp": None,
        "reason": reason,
    }


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

        # Journal contract requires EXACTLY these two metric keys.
        # fuel_liters_total <- internal cumulative fuel consumed (NAVIXY_CAN).
        # energy_kwh_total  <- EV energy (no telemetry today -> UNAVAILABLE/null).
        out_metrics = {
            "fuel_liters_total": to_journal_metric(metrics_by_key.get("fuel_consumed")),
            "energy_kwh_total": (
                to_journal_metric(metrics_by_key.get("energy_used"))
                if metrics_by_key.get("energy_used")
                else empty_metric("no_ev_energy_telemetry")
            ),
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
                    **self._energy_blocks(
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
                **self._energy_blocks(
                    reason="per-trip historical energy not available from current telemetry"
                ),
            })
        return {"tenant_id": tenant_id, "count": len(results), "results": results}

    @staticmethod
    def _energy_blocks(reason: str) -> Dict[str, Any]:
        """Exact Journal field names. Litres and kWh kept in SEPARATE blocks."""
        return {
            "fuel": {
                "fuel_liters": empty_metric(reason),
                "consumption_l_100km": empty_metric(reason),
            },
            "electric": {
                "soc_start_pct": empty_metric(reason),
                "soc_end_pct": empty_metric(reason),
                "energy_kwh": empty_metric(reason),
                "consumption_kwh_100km": empty_metric(reason),
            },
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
        total = len(identities)
        obd_cov = round(100.0 * fuel_available_trackers / total, 1) if total else 0.0

        # Journal contract requires EXACTLY these 6 metric envelopes.
        # - Period consumption totals/averages are NOT computable from the current
        #   real telemetry -> honest UNAVAILABLE/value:null (no fabrication, no zero).
        # - obd_coverage_pct and vehicles_with_data ARE computable from real data
        #   (derived -> ESTIMATED / CALCULATED).
        metrics = {
            "thermal_consumption_l_100km": empty_metric("period_consumption_not_available"),
            "electric_consumption_kwh_100km": empty_metric("no_ev_energy_telemetry"),
            "fuel_liters_total": empty_metric("period_fuel_total_not_available"),
            "electric_kwh_total": empty_metric("no_ev_energy_telemetry"),
            "obd_coverage_pct": _computed_metric(
                obd_cov, "%", "share_of_trackers_with_obd_fuel_data"
            ),
            "vehicles_with_data": _computed_metric(
                fuel_available_trackers, "count", "trackers_with_fuel_data"
            ),
        }

        return {
            "tenant_id": tenant_id,
            "trackers_total": total,
            "trackers_associated": associated,
            "powertrain_distribution": powertrain_counts,
            "fuel_level_quality": quality,
            "metrics": metrics,
            "note": (
                "Aggregates reflect only proven data. Absence is reported as "
                "UNAVAILABLE, never as 0. Litres and kWh are never mixed."
            ),
        }
