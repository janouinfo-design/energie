"""Canonical enums for the Energy contract envelope.

The envelope for every metric is intentionally split into THREE orthogonal axes
plus a timestamp, as validated with the product owner:

    availability      : AVAILABLE | UNAVAILABLE | STALE | ERROR
    measurement_type  : MEASURED  | ESTIMATED   | REFERENCE
    source            : NAVIXY_OBD | NAVIXY_CAN | DOCUMENTS | CALCULATED | NONE

This lets us express e.g. "manufacturer consumption AVAILABLE but REFERENCE",
"SoC UNAVAILABLE", "fuel level MEASURED but STALE" cleanly.
"""
from enum import Enum


class Availability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    ERROR = "ERROR"


class MeasurementType(str, Enum):
    MEASURED = "MEASURED"
    ESTIMATED = "ESTIMATED"
    REFERENCE = "REFERENCE"
    # NONE is used when there is no value at all (availability != AVAILABLE)
    NONE = "NONE"


class Source(str, Enum):
    NAVIXY_OBD = "NAVIXY_OBD"
    NAVIXY_CAN = "NAVIXY_CAN"
    NAVIXY_STATE = "NAVIXY_STATE"
    NAVIXY_COUNTER = "NAVIXY_COUNTER"
    DOCUMENTS = "DOCUMENTS"
    CALCULATED = "CALCULATED"
    NONE = "NONE"


class EnergyType(str, Enum):
    ICE_PETROL = "ICE_PETROL"
    ICE_DIESEL = "ICE_DIESEL"
    HYBRID = "HYBRID"
    PHEV = "PHEV"
    BEV = "BEV"
    UNKNOWN = "UNKNOWN"


class Confidence(str, Enum):
    HIGH = "HIGH"        # proven link (e.g. OBD VIN == vehicle VIN)
    MEDIUM = "MEDIUM"    # partial proof (OBD VIN present, no vehicle match)
    LOW = "LOW"          # weak / heuristic
    NONE = "NONE"        # no proven link


class AnomalyType(str, Enum):
    VIN_ABSENT = "VIN_ABSENT"
    VIN_DUPLICATE = "VIN_DUPLICATE"
    VIN_CONFLICT = "VIN_CONFLICT"
    TRACKER_WITHOUT_VEHICLE = "TRACKER_WITHOUT_VEHICLE"
    VEHICLE_WITHOUT_TRACKER = "VEHICLE_WITHOUT_TRACKER"
    STALE_DATA = "STALE_DATA"
    UNIT_UNVERIFIED = "UNIT_UNVERIFIED"
    NO_ENERGY_TELEMETRY = "NO_ENERGY_TELEMETRY"
    # TRACKER/VEHICLE change detection requires history across sync runs.
    MAPPING_CHANGED = "MAPPING_CHANGED"


class Channel(str, Enum):
    """How an energy metric could technically be obtained (evidence-based)."""
    NATIVE = "NATIVE"                       # provided natively by device today
    VIA_OBD = "VIA_OBD"                     # standard/OEM OBD PID on supported vehicle
    VIA_CAN = "VIA_CAN"                     # external CAN adapter signal
    NEEDS_NAVIXY_CONFIG = "NEEDS_NAVIXY_CONFIG"
    NEEDS_TRACKER_CONFIG = "NEEDS_TRACKER_CONFIG"
    NEEDS_HARDWARE = "NEEDS_HARDWARE"       # extra hardware/wiring (e.g. CAN adapter)
    NOT_SUPPORTED = "NOT_SUPPORTED"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"       # cannot be proven without vehicle profile


class ProposalClass(str, Enum):
    SAFE_TO_REVIEW = "SAFE_TO_REVIEW"
    AMBIGUOUS = "AMBIGUOUS"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ChangeType(str, Enum):
    NEW_ASSOCIATION = "NEW_ASSOCIATION"
    TRACKER_CHANGE = "TRACKER_CHANGE"
    VIN_CHANGE = "VIN_CHANGE"
    ASSOCIATION_REMOVED = "ASSOCIATION_REMOVED"
    CONFLICT = "CONFLICT"
