"""Journal-facing Energy v1 business routes.

Exactly the 4 validated routes:
  GET  /api/energy/v1/health                     (public, no tenant, no secret)
  POST /api/energy/v1/trips/energy:batch         (Bearer, tenant in body)
  GET  /api/energy/v1/fleet/summary              (Bearer, tenant in query)
  GET  /api/energy/v1/vehicles/{ref}/summary     (Bearer, tenant in query)

Tenant mechanism:
  - X-Tenant-Id header accepted on data routes.
  - trips:batch primary tenant = body.tenant_id
  - fleet/vehicle summary primary tenant = query tenant_id
  - health: no tenant
  If both header and body/query tenant are provided and DIFFER -> 400.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, status

from .auth import require_bearer
from .service import EnergyService
from .v1_service import EnergyV1Service

MAX_TRIPS = 100


def _resolve_tenant(primary: Optional[str], header: Optional[str]) -> str:
    """Reconcile tenant from the documented location and the X-Tenant-Id header."""
    if primary and header and primary != header:
        raise HTTPException(status_code=400, detail="Tenant mismatch between body/query and X-Tenant-Id.")
    tid = primary or header
    if not tid:
        raise HTTPException(status_code=400, detail="Missing tenant (tenant_id or X-Tenant-Id).")
    return tid


def build_energy_v1_router(db) -> APIRouter:
    router = APIRouter(prefix="/energy/v1", tags=["energy-v1"])
    energy = EnergyService(db)
    svc = EnergyV1Service(energy)
    secured = [Depends(require_bearer)]

    @router.get("/health")
    async def health():
        # Public liveness: no tenant, no secret exposed.
        return {
            "status": "ok",
            "contract_version": "v1",
            "service": "energy",
            "navixy_configured": energy.client.configured,
        }

    @router.get("/vehicles/{ref}/summary", dependencies=secured)
    async def vehicle_summary(
        ref: str,
        tenant_id: Optional[str] = Query(None),
        x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-Id"),
    ):
        tid = _resolve_tenant(tenant_id, x_tenant_id)
        code, body = await svc.vehicle_summary(tid, ref)
        if code != 200:
            raise HTTPException(status_code=code, detail=body)
        return body

    @router.get("/fleet/summary", dependencies=secured)
    async def fleet_summary(
        tenant_id: Optional[str] = Query(None),
        x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-Id"),
    ):
        tid = _resolve_tenant(tenant_id, x_tenant_id)
        return await svc.fleet_summary(tid)

    @router.post("/trips/energy:batch", dependencies=secured)
    async def trips_energy_batch(
        payload: Dict[str, Any] = Body(...),
        x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-Id"),
    ):
        tid = _resolve_tenant(payload.get("tenant_id"), x_tenant_id)
        trips: List[Dict[str, Any]] = payload.get("trips") or []
        if not isinstance(trips, list):
            raise HTTPException(status_code=400, detail="'trips' must be a list.")
        if len(trips) > MAX_TRIPS:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Batch limited to {MAX_TRIPS} trips (received {len(trips)}).",
            )
        return await svc.trips_energy_batch(tid, trips)

    return router
