"""Mapping correction PROPOSALS (never applied automatically).

Proposals are built ONLY from proven identifiers (obd_vin, vehicle.vin,
existing tracker_id links). The label/name is NEVER a basis for a proposal.

Each proposal is classified:
  SAFE_TO_REVIEW   - a proven match exists (e.g. obd_vin == vehicle.vin)
  AMBIGUOUS        - some evidence but conflicting/uncertain
  INSUFFICIENT_DATA - not enough proven data to propose anything

No write to Navixy is performed anywhere in this module.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .enums import ProposalClass


def _norm(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    v = v.strip().upper()
    return v or None


def build_proposals(
    identities: List[Any],
    vehicles: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    proposals: List[Dict[str, Any]] = []

    veh_by_vin: Dict[str, Dict[str, Any]] = {}
    for v in vehicles:
        vin = _norm(v.get("vin"))
        if vin:
            veh_by_vin[vin] = v

    linked_vehicle_ids = {i.vehicle_id for i in identities if i.vehicle_id is not None}

    for idt in identities:
        obd_vin = _norm(idt.obd_vin)

        # Case 1: tracker not linked to a vehicle.
        if idt.vehicle_id is None:
            if obd_vin and obd_vin in veh_by_vin:
                v = veh_by_vin[obd_vin]
                proposals.append(_p(
                    idt, ProposalClass.SAFE_TO_REVIEW,
                    anomaly="TRACKER_WITHOUT_VEHICLE",
                    proposed_match=f"link tracker {idt.tracker_id} -> vehicle {v.get('id')}",
                    proposed_vehicle_id=v.get("id"), vehicle_vin=_norm(v.get("vin")),
                    evidence=[f"obd_vin {obd_vin} == vehicle.vin {_norm(v.get('vin'))}"],
                    recommended_action="Review then set tracker_id on the vehicle record (manual).",
                    confidence="HIGH",
                ))
            elif obd_vin:
                proposals.append(_p(
                    idt, ProposalClass.INSUFFICIENT_DATA,
                    anomaly="TRACKER_WITHOUT_VEHICLE",
                    proposed_match=None,
                    evidence=[f"obd_vin {obd_vin} present but no vehicle record has this VIN (vehicle.vin empty)."],
                    recommended_action="Populate vehicle.vin from OBD VIN after manual verification; do NOT infer from label.",
                    confidence="MEDIUM",
                ))
            else:
                proposals.append(_p(
                    idt, ProposalClass.INSUFFICIENT_DATA,
                    anomaly="VIN_ABSENT",
                    proposed_match=None,
                    evidence=["No OBD VIN and no vehicle link; label is not a valid basis."],
                    recommended_action="Enable/await OBD VIN, or link manually with an authoritative source.",
                    confidence="NONE",
                ))

        # Case 2: VIN conflict (only when both VINs are proven).
        if obd_vin and idt.vehicle_vin and obd_vin != _norm(idt.vehicle_vin):
            proposals.append(_p(
                idt, ProposalClass.AMBIGUOUS,
                anomaly="VIN_CONFLICT",
                proposed_match=None,
                evidence=[f"obd_vin {obd_vin} != vehicle.vin {_norm(idt.vehicle_vin)}"],
                recommended_action="Manual investigation required; do not auto-correct.",
                confidence="LOW",
            ))

    # Case 3: vehicles without any tracker.
    for v in vehicles:
        if v.get("id") in linked_vehicle_ids:
            continue
        vin = _norm(v.get("vin"))
        match = None
        if vin:
            for idt in identities:
                if _norm(idt.obd_vin) == vin:
                    match = idt
                    break
        if match is not None:
            proposals.append({
                "anomaly": "VEHICLE_WITHOUT_TRACKER",
                "classification": ProposalClass.SAFE_TO_REVIEW.value,
                "vehicle_id": v.get("id"), "tracker_id": match.tracker_id,
                "current_label": v.get("label"),
                "vehicle_vin": vin, "obd_vin": _norm(match.obd_vin),
                "proposed_match": f"link vehicle {v.get('id')} -> tracker {match.tracker_id}",
                "evidence": [f"vehicle.vin {vin} == tracker obd_vin {_norm(match.obd_vin)}"],
                "recommended_action": "Review then set tracker_id on the vehicle (manual).",
                "confidence": "HIGH",
            })
        else:
            proposals.append({
                "anomaly": "VEHICLE_WITHOUT_TRACKER",
                "classification": ProposalClass.INSUFFICIENT_DATA.value,
                "vehicle_id": v.get("id"), "tracker_id": None,
                "current_label": v.get("label"),
                "vehicle_vin": vin, "obd_vin": None,
                "proposed_match": None,
                "evidence": ["Vehicle has no VIN or no matching OBD VIN; label not usable."],
                "recommended_action": "Add VIN to vehicle record, or link manually.",
                "confidence": "NONE",
            })

    return proposals


def _p(idt, classification: ProposalClass, anomaly: str, proposed_match,
       evidence, recommended_action, confidence,
       proposed_vehicle_id=None, vehicle_vin=None) -> Dict[str, Any]:
    return {
        "anomaly": anomaly,
        "classification": classification.value,
        "tracker_id": idt.tracker_id,
        "vehicle_id": proposed_vehicle_id if proposed_vehicle_id is not None else idt.vehicle_id,
        "current_label": idt.tracker_label,   # displayed as context only, never a basis
        "vehicle_vin": vehicle_vin if vehicle_vin is not None else idt.vehicle_vin,
        "obd_vin": idt.obd_vin,
        "proposed_match": proposed_match,
        "evidence": evidence,
        "recommended_action": recommended_action,
        "confidence": confidence,
    }
