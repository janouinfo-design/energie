"""Canonical vehicle <-> tracker <-> VIN mapping + anomaly detection.

Rules (validated with product owner):
  - Mapping is built ONLY from proven identifiers: vehicle_id, tracker_id,
    obd_vin, vehicle.vin. NEVER from the tracker/vehicle label.
  - No automatic writes to Navixy. Corrections are proposed, not applied.
  - Provenance + confidence are preserved for auditability.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from .enums import AnomalyType, Confidence, Source
from .models import Anomaly, Identity


def _norm_vin(vin: Optional[str]) -> Optional[str]:
    if not vin:
        return None
    v = vin.strip().upper()
    return v or None


def build_identities(
    tenant_id: str,
    trackers: List[Dict[str, Any]],
    tracker_states: Dict[str, Dict[str, Any]],
    tracker_obd_vins: Dict[int, Optional[str]],
    vehicles: List[Dict[str, Any]],
) -> List[Identity]:
    """Create one Identity per tracker, linking to a vehicle only when PROVEN."""
    # Index vehicles by proven VIN and by explicit tracker_id link.
    veh_by_vin: Dict[str, Dict[str, Any]] = {}
    veh_by_tracker: Dict[int, Dict[str, Any]] = {}
    for v in vehicles:
        vin = _norm_vin(v.get("vin"))
        if vin:
            veh_by_vin[vin] = v
        tid = v.get("tracker_id")
        if tid is not None:
            veh_by_tracker[int(tid)] = v

    identities: List[Identity] = []
    for t in trackers:
        tid = t.get("id")
        source = t.get("source", {}) or {}
        state = tracker_states.get(str(tid), {}) or {}
        obd_vin = _norm_vin(tracker_obd_vins.get(tid))

        vehicle = None
        confidence = Confidence.NONE
        # 1) explicit tracker_id link on the vehicle (strongest, if present)
        if tid in veh_by_tracker:
            vehicle = veh_by_tracker[tid]
            confidence = Confidence.HIGH
        # 2) proven VIN match (OBD VIN == vehicle VIN)
        elif obd_vin and obd_vin in veh_by_vin:
            vehicle = veh_by_vin[obd_vin]
            confidence = Confidence.HIGH
        # 3) OBD VIN present but no vehicle match -> identifiable but unlinked
        elif obd_vin:
            confidence = Confidence.MEDIUM

        identities.append(Identity(
            tenant_id=tenant_id,
            tracker_id=tid,
            tracker_label=t.get("label"),  # informational only
            device_model=source.get("model"),
            device_id=source.get("device_id"),
            obd_vin=obd_vin,
            vin_source=Source.NAVIXY_STATE if obd_vin else Source.NONE,
            vehicle_id=vehicle.get("id") if vehicle else None,
            vehicle_vin=_norm_vin(vehicle.get("vin")) if vehicle else None,
            vehicle_label=vehicle.get("label") if vehicle else None,
            confidence=confidence,
            connection_status=state.get("connection_status"),
            last_update=state.get("last_update"),
        ))
    return identities


def detect_anomalies(
    tenant_id: str,
    identities: List[Identity],
    vehicles: List[Dict[str, Any]],
    ev_sensor_presence: Dict[int, bool],
    stale_hours: float,
    navixy_now: Optional[str],
) -> List[Anomaly]:
    from .normalization import parse_dt  # local import to avoid cycle

    anomalies: List[Anomaly] = []
    now = parse_dt(navixy_now)

    # VIN duplicates across trackers
    vin_to_trackers: Dict[str, List[int]] = defaultdict(list)
    for idt in identities:
        if idt.obd_vin:
            vin_to_trackers[idt.obd_vin].append(idt.tracker_id)
    for vin, tids in vin_to_trackers.items():
        if len(tids) > 1:
            anomalies.append(Anomaly(
                tenant_id=tenant_id, type=AnomalyType.VIN_DUPLICATE.value,
                severity="critical", vin=vin,
                detail=f"OBD VIN {vin} present on multiple trackers: {tids}",
                recommendation="Investigate duplicate VIN before any linking.",
            ))

    linked_vehicle_ids = {i.vehicle_id for i in identities if i.vehicle_id is not None}

    for idt in identities:
        # VIN absent
        if not idt.obd_vin:
            anomalies.append(Anomaly(
                tenant_id=tenant_id, type=AnomalyType.VIN_ABSENT.value,
                severity="warning", tracker_id=idt.tracker_id,
                detail=f"Tracker {idt.tracker_id} has no OBD VIN in states.",
                recommendation="Cannot prove vehicle identity from telematics.",
            ))
        # VIN conflict (OBD VIN present AND vehicle vin present AND differ)
        if idt.obd_vin and idt.vehicle_vin and idt.obd_vin != idt.vehicle_vin:
            anomalies.append(Anomaly(
                tenant_id=tenant_id, type=AnomalyType.VIN_CONFLICT.value,
                severity="critical", tracker_id=idt.tracker_id,
                vehicle_id=idt.vehicle_id, vin=idt.obd_vin,
                detail=f"OBD VIN {idt.obd_vin} != vehicle VIN {idt.vehicle_vin}",
                recommendation="Do not link automatically; manual review needed.",
            ))
        # Tracker without vehicle
        if idt.vehicle_id is None:
            anomalies.append(Anomaly(
                tenant_id=tenant_id, type=AnomalyType.TRACKER_WITHOUT_VEHICLE.value,
                severity="warning", tracker_id=idt.tracker_id,
                detail=f"Tracker {idt.tracker_id} is not linked to any vehicle record.",
                recommendation="Establish mapping via proven VIN or manual assignment.",
            ))
        # Stale data
        ts = parse_dt(idt.last_update)
        if now is not None and ts is not None:
            age_h = (now - ts).total_seconds() / 3600.0
            if age_h > stale_hours:
                anomalies.append(Anomaly(
                    tenant_id=tenant_id, type=AnomalyType.STALE_DATA.value,
                    severity="info", tracker_id=idt.tracker_id,
                    detail=f"Last update {idt.last_update} (age {age_h:.0f}h > {stale_hours}h).",
                    recommendation="Treat metrics as STALE, not fresh.",
                ))
        # No energy telemetry (no EV sensors) - reported per tracker
        if not ev_sensor_presence.get(idt.tracker_id, False):
            anomalies.append(Anomaly(
                tenant_id=tenant_id, type=AnomalyType.NO_ENERGY_TELEMETRY.value,
                severity="info", tracker_id=idt.tracker_id,
                detail="No EV energy sensor (SoC/battery/kWh/range) configured.",
                recommendation="EV energy metrics remain UNAVAILABLE unless configured.",
            ))

    # Vehicle without tracker
    for v in vehicles:
        if v.get("id") not in linked_vehicle_ids:
            anomalies.append(Anomaly(
                tenant_id=tenant_id, type=AnomalyType.VEHICLE_WITHOUT_TRACKER.value,
                severity="warning", vehicle_id=v.get("id"),
                detail=f"Vehicle {v.get('id')} ('{v.get('label')}') has no linked tracker.",
                recommendation="Link a tracker via proven identifiers.",
            ))
    return anomalies
