"""Journal-facing v1 output contract helpers.

Transforms internal socle metrics into the exact envelope the Journal client
consumes, enforcing the ABSOLUTE rules agreed with the product owner:

  - null stays null ; a real zero stays 0 (never confused).
  - STALE stays STALE (never promoted to AVAILABLE).
  - availability sent to the Journal is ONLY: AVAILABLE | UNAVAILABLE | STALE.
    (internal ERROR is mapped to UNAVAILABLE; reason is preserved).
  - measurement_type is NEVER sent as the string "NONE": when there is no
    value (UNAVAILABLE) we send measurement_type=null and source=null.
  - estimation != measurement (MEASURED/ESTIMATED/REFERENCE preserved as-is).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# What the Journal is allowed to receive.
_ALLOWED_AVAILABILITY = {"AVAILABLE", "UNAVAILABLE", "STALE"}
_ALLOWED_MEASUREMENT = {"MEASURED", "ESTIMATED", "REFERENCE"}


def empty_metric(reason: str = "no_data") -> Dict[str, Any]:
    """A contractually-correct 'no data' metric: UNAVAILABLE / value:null."""
    return {
        "value": None,
        "unit": None,
        "unit_verified": True,
        "availability": "UNAVAILABLE",
        "measurement_type": None,   # never "NONE"
        "source": None,
        "timestamp": None,
        "reason": reason,
    }


def to_journal_metric(m: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize an internal metric dict into the Journal envelope."""
    if not m:
        return empty_metric("missing_metric")

    availability = m.get("availability", "UNAVAILABLE")
    # Never surface ERROR to the Journal.
    if availability == "ERROR":
        availability = "UNAVAILABLE"
    if availability not in _ALLOWED_AVAILABILITY:
        availability = "UNAVAILABLE"

    value = m.get("value", None)  # 0 preserved, None preserved

    if availability == "UNAVAILABLE":
        # No trustworthy value: strip measurement_type/source, keep value/null.
        return {
            "value": value if value is not None else None,
            "unit": m.get("unit"),
            "unit_verified": bool(m.get("unit_verified", True)),
            "availability": "UNAVAILABLE",
            "measurement_type": None,
            "source": None,
            "timestamp": m.get("timestamp"),
            "reason": m.get("reason") or "unavailable",
        }

    mtype = m.get("measurement_type")
    if mtype not in _ALLOWED_MEASUREMENT:
        # A present value must have a real classification; if internal said NONE
        # while a value exists (should not happen), be honest -> UNAVAILABLE.
        return empty_metric("inconsistent_measurement_type")

    return {
        "value": value,
        "unit": m.get("unit"),
        "unit_verified": bool(m.get("unit_verified", True)),
        "availability": availability,   # AVAILABLE or STALE
        "measurement_type": mtype,
        "source": m.get("source"),
        "timestamp": m.get("timestamp"),
        "reason": m.get("reason"),
    }
