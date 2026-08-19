"""Capability map + metric snapshot per tracker.

Determines, from REAL configured sensors and REAL values, what each tracker can
actually provide. Never infers powertrain from the tracker label.

EV capability audit: we look for actually-configured EV sensors
(SoC/battery/range/charge/energy). If none exist, the corresponding metrics are
UNAVAILABLE with an explicit reason (`no_sensor_configured`) - we do NOT simulate.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .enums import Availability, MeasurementType, Source
from .models import CapabilityEntry, Metric
from .normalization import build_metric

# Canonical ICE/common metrics we try to extract from diagnostics/fuel/counters.
# name substrings are matched case-insensitively against Navixy input `name`.
_ICE_METRIC_MATCHERS = [
    # (metric_key, label, name_substrings, source)
    ("fuel_level", "Niveau carburant", ["obd_fuel"], Source.NAVIXY_OBD),
    ("fuel_consumed", "Carburant consomm\u00e9", ["can_consumption"], Source.NAVIXY_CAN),
    ("coolant_temp", "Temp\u00e9rature liquide refroidissement", ["obd_coolant_t", "coolant"], Source.NAVIXY_OBD),
    ("board_voltage", "Tension d'alimentation", ["board_voltage"], Source.NAVIXY_STATE),
    ("control_module_voltage", "Tension module", ["obd_control_module_voltage"], Source.NAVIXY_OBD),
    ("obd_speed", "Vitesse OBD", ["obd_speed"], Source.NAVIXY_OBD),
    ("engine_rpm", "R\u00e9gime moteur", ["obd_rpm"], Source.NAVIXY_OBD),
    ("throttle", "Papillon", ["obd_throttle"], Source.NAVIXY_OBD),
]

# EV metrics we audit for. sensor_type / name keyword detection.
_EV_KEYWORDS = [
    "soc", "state_of_charge", "state of charge", "battery", "batt", "hv_",
    "high_voltage", "high voltage", "charge", "charging", "kwh", "range",
    "autonomy", "autonomie", "electric", "ev_",
]

_EV_EXPECTED = [
    ("soc", "\u00c9tat de charge (SoC)", "%"),
    ("battery_capacity", "Capacit\u00e9 batterie", "kWh"),
    ("battery_state", "\u00c9tat batterie", None),
    ("range_est", "Autonomie estim\u00e9e", "km"),
    ("charge_power", "Puissance de charge", "kW"),
    ("charge_state", "\u00c9tat de charge (branchement)", None),
    ("energy_used", "\u00c9nergie consomm\u00e9e", "kWh"),
    ("consumption_kwh_100", "Consommation", "kWh/100km"),
]


def _find_input(inputs: List[Dict[str, Any]], substrings: List[str]) -> Optional[Dict[str, Any]]:
    for inp in inputs:
        name = (inp.get("name") or "").lower()
        for sub in substrings:
            if sub.lower() in name:
                return inp
    return None


def detect_ev_sensors(sensors: List[Dict[str, Any]]) -> List[str]:
    """Return names of any configured sensors that look EV-related."""
    found = []
    for s in sensors:
        blob = f"{s.get('sensor_type','')} {s.get('name','')}".lower()
        if any(kw in blob for kw in _EV_KEYWORDS):
            # exclude the generic ICE 'fuel'/'charge (load)' false positives
            if "absolute load" in blob or "charge value" in blob or "valeur" in blob:
                continue
            found.append(s.get("name") or s.get("sensor_type") or "?")
    return found


def build_metric_snapshot(
    inputs: List[Dict[str, Any]],
    fuel_inputs: List[Dict[str, Any]],
    counters: List[Dict[str, Any]],
    navixy_now: Optional[str],
    reading_ts: Optional[str],
    connection_status: Optional[str],
    stale_hours: float,
) -> List[Metric]:
    metrics: List[Metric] = []
    merged = list(inputs) + list(fuel_inputs)

    for key, label, subs, source in _ICE_METRIC_MATCHERS:
        inp = _find_input(merged, subs)
        if inp is None:
            metrics.append(Metric(
                key=key, label=label, value=None, unit=None,
                availability=Availability.UNAVAILABLE,
                measurement_type=MeasurementType.NONE, source=Source.NONE,
                reason="no_sensor_configured",
            ))
            continue
        metrics.append(build_metric(
            key=key, label=label, raw_value=inp.get("value"),
            units_type=inp.get("units_type"), reading_ts=reading_ts,
            navixy_now=navixy_now, stale_hours=stale_hours, source=source,
            connection_status=connection_status,
        ))

    # counters: odometer (km) + engine_hours
    counter_map = {c.get("type"): c for c in counters}
    for ckey, label, unit_type, source in [
        ("odometer", "Kilom\u00e9trage", "km", Source.NAVIXY_COUNTER),
        ("engine_hours", "Heures moteur", "hour", Source.NAVIXY_COUNTER),
    ]:
        c = counter_map.get(ckey)
        if c is None:
            metrics.append(Metric(
                key=ckey, label=label, availability=Availability.UNAVAILABLE,
                measurement_type=MeasurementType.NONE, source=Source.NONE,
                reason="no_counter",
            ))
            continue
        metrics.append(build_metric(
            key=ckey, label=label, raw_value=c.get("value"),
            units_type=unit_type, reading_ts=c.get("update_time"),
            navixy_now=navixy_now, stale_hours=stale_hours, source=source,
            connection_status=connection_status,
        ))
    return metrics


def build_capability_map(
    sensors: List[Dict[str, Any]],
    metrics: List[Metric],
) -> List[CapabilityEntry]:
    entries: List[CapabilityEntry] = []

    # ICE/common metrics reflect the actual snapshot classification.
    for m in metrics:
        entries.append(CapabilityEntry(
            metric_key=m.key, label=m.label,
            configured=(m.reason not in ("no_sensor_configured", "no_counter")),
            availability=m.availability, measurement_type=m.measurement_type,
            source=m.source, unit=m.unit, unit_verified=m.unit_verified,
            reason=m.reason,
        ))

    # EV audit: expected EV metrics, marked UNAVAILABLE unless a real sensor exists.
    ev_sensors = detect_ev_sensors(sensors)
    for key, label, unit in _EV_EXPECTED:
        configured = bool(ev_sensors)
        entries.append(CapabilityEntry(
            metric_key=key, label=label, configured=configured,
            availability=Availability.UNAVAILABLE,
            measurement_type=MeasurementType.NONE, source=Source.NONE,
            unit=unit, unit_verified=True,
            reason=("ev_sensor_detected_but_unread" if configured
                    else "no_sensor_configured"),
        ))
    return entries
