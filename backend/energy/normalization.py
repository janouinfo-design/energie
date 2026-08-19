"""Normalization: units, staleness, and metric classification.

Core invariants:
  - Only VERIFIED units (from Navixy `units_type`) are exploitable in production.
    `custom`/unknown units are flagged unit_verified=False and never presented as
    a trustworthy production value.
  - 0 is a valid measurement; None means UNAVAILABLE.
  - Staleness is computed against Navixy server time (`user_time`) when available,
    NOT the container clock.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from .enums import Availability, MeasurementType, Source
from .models import Metric

# Verified Navixy units_type -> canonical unit
VERIFIED_UNITS = {
    "kmh": "km/h",
    "litre": "L",
    "liter": "L",
    "celsius": "\u00b0C",
    "volt": "V",
    "percent": "%",
    "second": "s",
    "km": "km",
    "hour": "h",
}

# units_type values we explicitly consider UNVERIFIED / ambiguous.
UNVERIFIED_UNIT_TYPES = {"custom", "", None}

_DT_FMT = "%Y-%m-%d %H:%M:%S"


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:19], _DT_FMT)
    except (ValueError, TypeError):
        return None


def resolve_unit(units_type: Optional[str]) -> Tuple[Optional[str], bool]:
    """Return (canonical_unit, verified)."""
    if units_type in UNVERIFIED_UNIT_TYPES:
        return (units_type or None, False)
    canonical = VERIFIED_UNITS.get(units_type)
    if canonical is None:
        # Known type name but not in our verified whitelist -> treat as unverified.
        return (units_type, False)
    return (canonical, True)


def compute_availability(
    value: Optional[float],
    reading_ts: Optional[str],
    navixy_now: Optional[str],
    stale_hours: float,
    connection_status: Optional[str] = None,
) -> Tuple[Availability, Optional[str]]:
    """Decide AVAILABLE / STALE / UNAVAILABLE (never ERROR here).

    - value is None -> UNAVAILABLE (0 is NOT None and stays AVAILABLE/STALE).
    - offline connection OR age beyond threshold -> STALE.
    """
    if value is None:
        return (Availability.UNAVAILABLE, "no_value")

    now = parse_dt(navixy_now)
    ts = parse_dt(reading_ts)
    if now is not None and ts is not None:
        age_hours = (now - ts).total_seconds() / 3600.0
        if age_hours > stale_hours:
            return (Availability.STALE, f"age_hours={age_hours:.1f}>{stale_hours}")
    if connection_status and connection_status.lower() in {"offline", "just_registered"}:
        # Connection offline: last value may be old even if timestamp missing.
        if ts is None:
            return (Availability.STALE, f"connection={connection_status}")
    return (Availability.AVAILABLE, None)


def build_metric(
    key: str,
    label: str,
    raw_value,
    units_type: Optional[str],
    reading_ts: Optional[str],
    navixy_now: Optional[str],
    stale_hours: float,
    source: Source,
    measurement_type: MeasurementType = MeasurementType.MEASURED,
    connection_status: Optional[str] = None,
) -> Metric:
    """Build a fully-classified Metric envelope from a raw Navixy value."""
    unit, verified = resolve_unit(units_type)

    value: Optional[float]
    if raw_value is None:
        value = None
    else:
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = None

    availability, reason = compute_availability(
        value, reading_ts, navixy_now, stale_hours, connection_status
    )

    mtype = measurement_type
    if availability == Availability.UNAVAILABLE:
        mtype = MeasurementType.NONE
        src = Source.NONE if source == Source.NONE else source
    else:
        src = source

    # An unverified unit must never be presented as a trustworthy measurement.
    if not verified and availability in (Availability.AVAILABLE, Availability.STALE):
        reason = (reason + "; " if reason else "") + "unit_unverified"

    return Metric(
        key=key,
        label=label,
        value=value,
        unit=unit,
        unit_verified=verified,
        availability=availability,
        measurement_type=mtype,
        source=src,
        timestamp=reading_ts,
        reason=reason,
    )
