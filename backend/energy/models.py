"""Pydantic models for the Energy foundation."""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field

from .enums import (
    Availability,
    Confidence,
    EnergyType,
    MeasurementType,
    Source,
)


class Metric(BaseModel):
    """The canonical energy metric envelope.

    Rules enforced by construction:
      - 0 is a valid measurement (AVAILABLE), it is NEVER null.
      - UNAVAILABLE / STALE / ERROR keep value=None unless the value is
        genuinely known (STALE keeps the last known value + its timestamp).
      - REFERENCE is never presented as MEASURED.
    """

    key: str
    label: str
    value: Optional[float] = None
    unit: Optional[str] = None
    unit_verified: bool = True
    availability: Availability = Availability.UNAVAILABLE
    measurement_type: MeasurementType = MeasurementType.NONE
    source: Source = Source.NONE
    timestamp: Optional[str] = None  # ISO8601 of the underlying reading
    reason: Optional[str] = None     # why UNAVAILABLE/STALE/ERROR


class CapabilityEntry(BaseModel):
    metric_key: str
    label: str
    configured: bool               # a sensor/source exists for this metric
    availability: Availability
    measurement_type: MeasurementType = MeasurementType.NONE
    source: Source = Source.NONE
    unit: Optional[str] = None
    unit_verified: bool = True
    reason: Optional[str] = None


class Identity(BaseModel):
    tenant_id: str
    tracker_id: Optional[int] = None
    tracker_label: Optional[str] = None   # informational ONLY, never a source of truth
    device_model: Optional[str] = None
    device_id: Optional[str] = None
    obd_vin: Optional[str] = None
    vin_source: Source = Source.NONE
    vehicle_id: Optional[int] = None
    vehicle_vin: Optional[str] = None
    vehicle_label: Optional[str] = None
    energy_type: EnergyType = EnergyType.UNKNOWN
    energy_type_source: Source = Source.NONE
    confidence: Confidence = Confidence.NONE
    connection_status: Optional[str] = None
    last_update: Optional[str] = None


class Anomaly(BaseModel):
    tenant_id: str
    type: str
    severity: str = "warning"           # info | warning | critical
    tracker_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    vin: Optional[str] = None
    detail: str = ""
    recommendation: Optional[str] = None


class SyncSummary(BaseModel):
    tenant_id: str
    sync_run_id: str
    started_at: str
    finished_at: str
    navixy_now: Optional[str] = None
    trackers: int = 0
    vehicles: int = 0
    anomalies: int = 0
    errors: List[str] = Field(default_factory=list)
