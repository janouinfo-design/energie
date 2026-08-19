"""EV data-collection feasibility audit (evidence-based).

Assesses, per REAL device model present in the account, whether EV energy
metrics (SoC, HV battery, capacity, energy used, range, charge state/power,
kWh/100km) can technically be collected - and through which channel.

Hard rule: we NEVER claim a metric is available without technical evidence, and
we NEVER create an estimated SoC/kWh to compensate for missing telemetry.

Evidence base (Teltonika official docs, verified 2025):
  - FMC130 supports external CAN adapters (LV-CAN200 / ALL-CAN300) and an OBDII
    dongle. CAN adapters expose OEM signals depending on adapter + vehicle.
    (wiki.teltonika-gps.com/view/FMC130_CAN_adapters, /view/CAN_Adapters)
  - EV battery fields (Battery Charge Level, State of Health, HV Battery
    Voltage/Current) exist ONLY for vehicles in Teltonika's OBD supported list.
    (wiki.teltonika-gps.com/view/OBD_supported_vehicle_list)
  - SoC is OEM/vehicle data, NOT a universal OBDII standard PID; availability
    varies by make/model/year, and on some BEVs SoC is only sent while driving.
    (community.teltonika.lt/t/.../9918)
  - FMB003 is a compact OBD dongle (OEM OBD params, up to 32 onboard params); it
    has no external CAN-adapter option. (FMB003 datasheet; OBD_supported list)
  - Smartphone app trackers (iosnavixytracker, navixymobile) have no OBD/CAN.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .enums import Channel, Confidence

EVIDENCE = {
    "fmc130": "Teltonika FMC130: CAN adapter (LV-CAN200/ALL-CAN300) or OBDII dongle; EV fields only for supported vehicles (Teltonika wiki).",
    "fmb003": "Teltonika FMB003: compact OBD dongle, OEM OBD params only, no external CAN adapter; EV fields depend on vehicle OBD support (Teltonika datasheet/wiki).",
    "phone": "Smartphone app tracker: no OBD/CAN bus access.",
    "soc_note": "SoC is OEM data, not a universal OBDII PID; varies by make/model/year; may only update while driving.",
}

EV_METRICS = [
    "soc", "hv_battery_voltage", "battery_capacity", "energy_used_kwh",
    "range", "charge_state", "charge_power", "consumption_kwh_100",
]


def _model_family(model: Optional[str]) -> str:
    m = (model or "").lower()
    if "fmc130" in m or "fmu130" in m:
        return "fmc130"
    if "fmb003" in m or "fmc003" in m:
        return "fmb003"
    if "ios" in m or "mobile" in m or "xgps" in m:
        return "phone"
    return "unknown"


def _assess_metric(family: str, metric: str, has_ev_sensor: bool) -> Dict[str, Any]:
    """Return classification for one metric on one device family."""
    if has_ev_sensor:
        # A real EV sensor is already configured -> collection is possible now.
        return dict(channel=Channel.VIA_CAN.value, config_required="already_configured",
                    confidence=Confidence.HIGH.value,
                    limits="Verify value freshness and units before production use.")

    if family == "phone":
        return dict(channel=Channel.NOT_SUPPORTED.value, config_required=None,
                    confidence=Confidence.HIGH.value,
                    limits="No OBD/CAN access on smartphone trackers.")

    if family == "fmc130":
        if metric in ("soc", "hv_battery_voltage", "battery_capacity", "range",
                      "charge_state", "charge_power"):
            return dict(
                channel=Channel.NEEDS_HARDWARE.value,
                config_required="external CAN adapter (LV-CAN200/ALL-CAN300) + tracker CAN profile + Navixy sensor config; vehicle must be in Teltonika OBD supported list",
                confidence=Confidence.MEDIUM.value,
                limits="Device capable via CAN adapter, but vehicle-specific: NOT verifiable without confirming exact make/model/year in Teltonika supported list. SoC may only update while driving.",
            )
        if metric in ("energy_used_kwh", "consumption_kwh_100"):
            return dict(
                channel=Channel.NOT_SUPPORTED.value,
                config_required="derivable only if SoC + battery capacity available (SoC via CAN, capacity via DOCUMENTS/REFERENCE)",
                confidence=Confidence.MEDIUM.value,
                limits="Not a direct signal; would be CALCULATED and depends on SoC availability. No estimate is created while SoC is UNAVAILABLE.",
            )

    if family == "fmb003":
        return dict(
            channel=Channel.NOT_VERIFIABLE.value,
            config_required="vehicle must expose EV fields on OBD and be in Teltonika OBD supported list; no external CAN adapter option on FMB003",
            confidence=Confidence.LOW.value,
            limits="EV HV data rarely on standard OBD; likely NOT_SUPPORTED unless the exact vehicle exposes it.",
        )

    return dict(channel=Channel.NOT_VERIFIABLE.value, config_required=None,
                confidence=Confidence.NONE.value, limits="Unknown device model.")


def assess_tracker(
    tracker_id: int,
    model: Optional[str],
    obd_vin: Optional[str],
    vehicle_id: Optional[int],
    mapping_confidence: str,
    ev_sensors: List[str],
) -> Dict[str, Any]:
    family = _model_family(model)
    has_ev_sensor = bool(ev_sensors)
    # VIN/vehicle only cited when the mapping is proven.
    reliable_link = mapping_confidence in ("HIGH",)
    metrics = []
    for metric in EV_METRICS:
        a = _assess_metric(family, metric, has_ev_sensor)
        metrics.append({
            "metric": metric,
            "channel": a["channel"],
            "config_required": a["config_required"],
            "limits": a["limits"],
            "confidence": a["confidence"],
            "pid_or_can": ("CAN adapter signal" if a["channel"] in (Channel.VIA_CAN.value,)
                            else None),
        })
    return {
        "tracker_id": tracker_id,
        "device_model": model,
        "device_family": family,
        "vehicle_id": vehicle_id if reliable_link else None,
        "vin": obd_vin if obd_vin else None,
        "vin_reliable": reliable_link,
        "ev_sensors_configured": ev_sensors,
        "evidence": EVIDENCE.get(family, "") + " " + EVIDENCE["soc_note"],
        "metrics": metrics,
    }


def summarize(assessments: List[Dict[str, Any]]) -> Dict[str, Any]:
    families: Dict[str, int] = {}
    collectable_now = 0
    needs_hardware = 0
    not_supported = 0
    for a in assessments:
        families[a["device_family"]] = families.get(a["device_family"], 0) + 1
        channels = {m["channel"] for m in a["metrics"]}
        if a["ev_sensors_configured"]:
            collectable_now += 1
        elif Channel.NEEDS_HARDWARE.value in channels:
            needs_hardware += 1
        elif channels <= {Channel.NOT_SUPPORTED.value, Channel.NOT_VERIFIABLE.value}:
            not_supported += 1
    return {
        "device_families": families,
        "ev_collectable_now": collectable_now,
        "ev_needs_hardware_or_config": needs_hardware,
        "ev_not_supported_or_unverifiable": not_supported,
        "conclusion": (
            "No EV energy telemetry is collectable today. FMC130 units could collect "
            "SoC/HV battery via an external CAN adapter (LV-CAN200/ALL-CAN300) on a "
            "Teltonika-supported vehicle; FMB003 units depend on vehicle OBD support "
            "(likely unsupported); smartphone trackers are not supported. No SoC/kWh "
            "is estimated to compensate."
        ),
    }
