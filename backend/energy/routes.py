"""Energy foundation API routes (Phase 2 scaffold).

NOTE: This is intentionally NOT the full Energy->Journal A-E contract.
It exposes only the foundation: identity/mapping, capability map, anomalies,
normalized metric snapshot, and a read-only sync trigger.

All routes are under /api and are tenant-scoped. tenant_id resolves to the
last synced tenant when not provided (single-platform convenience) but the
isolation field is always applied to queries.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .service import EnergyService


def build_energy_router(db) -> APIRouter:
    router = APIRouter(prefix="/energy", tags=["energy"])
    service = EnergyService(db)

    async def _resolve_tenant(tenant_id: Optional[str]) -> str:
        if tenant_id:
            return tenant_id
        latest = await service.latest_tenant()
        if not latest:
            raise HTTPException(
                status_code=409,
                detail="No tenant data yet. Run POST /api/energy/sync first.",
            )
        return latest

    @router.get("/health")
    async def health():
        return {
            "status": "ok",
            "navixy_configured": service.client.configured,
            "stale_hours": __import__("os").environ.get("ENERGY_STALE_HOURS", "48"),
        }

    @router.post("/sync")
    async def sync(tenant_id: Optional[str] = Query(None)):
        summary = await service.run_sync(tenant_override=tenant_id)
        return summary.model_dump()

    @router.get("/mapping")
    async def mapping(tenant_id: Optional[str] = Query(None)):
        tid = await _resolve_tenant(tenant_id)
        return {"tenant_id": tid, "mapping": await service.get_mapping(tid)}

    @router.get("/anomalies")
    async def anomalies(tenant_id: Optional[str] = Query(None)):
        tid = await _resolve_tenant(tenant_id)
        data = await service.get_anomalies(tid)
        # group counts by type for quick overview
        counts: dict = {}
        for a in data:
            counts[a["type"]] = counts.get(a["type"], 0) + 1
        return {"tenant_id": tid, "counts": counts, "anomalies": data}

    @router.get("/trackers/{tracker_id}/capabilities")
    async def capabilities(tracker_id: int, tenant_id: Optional[str] = Query(None)):
        tid = await _resolve_tenant(tenant_id)
        doc = await service.get_capabilities(tid, tracker_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Tracker capabilities not found")
        return doc

    @router.get("/trackers/{tracker_id}/metrics")
    async def metrics(tracker_id: int, tenant_id: Optional[str] = Query(None)):
        tid = await _resolve_tenant(tenant_id)
        doc = await service.get_metrics(tid, tracker_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Tracker metrics not found")
        return doc

    @router.get("/sync-runs")
    async def sync_runs(tenant_id: Optional[str] = Query(None)):
        tid = await _resolve_tenant(tenant_id)
        return {"tenant_id": tid, "runs": await service.list_sync_runs(tid)}

    return router
