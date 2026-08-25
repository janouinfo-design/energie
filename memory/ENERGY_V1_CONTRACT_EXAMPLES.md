# Energy API v1 — Contrat Journal (exemples structurels)

> **Placeholders uniquement** (`<...>`, `null`). Aucune donnée opérationnelle réelle.
> Base URL : `ENERGY_API_BASE_URL` (ex. `https://energy-telemetry-1.preview.emergentagent.com`).
> Les chemins sont concaténés tels quels : `${ENERGY_API_BASE_URL}/api/energy/v1/...`.
>
> **Auth** : `Authorization: Bearer <ENERGY_API_TOKEN>` sur toutes les routes de données. `health` est public.
> **Tenant** : `health` = aucun ; `trips:batch` = `tenant_id` dans le body **ou** `X-Tenant-Id` ;
> `fleet`/`vehicle summary` = `tenant_id` en query **ou** `X-Tenant-Id`. Si header ET body/query présents
> et **différents** → `400`. Absent sur route de données → `400`.
>
> **Enveloppe métrique `<METRIC>`** (identique partout) :
> ```json
> {
>   "value": null,                 // nombre réel, 0 valide, ou null (jamais 0 pour "absent")
>   "unit": null,                  // "L" | "%" | "km" | "kWh" | "kWh/100km" | ...
>   "unit_verified": true,
>   "availability": "UNAVAILABLE", // AVAILABLE | UNAVAILABLE | STALE   (jamais ERROR)
>   "measurement_type": null,      // MEASURED | ESTIMATED | REFERENCE | null (jamais "NONE")
>   "source": null,                // NAVIXY_OBD | NAVIXY_CAN | NAVIXY_STATE | NAVIXY_COUNTER | CALCULATED | REFERENCE | null
>   "timestamp": null,             // ISO/horodatage du relevé sous-jacent
>   "reason": "<why_unavailable_or_stale>"
> }
> ```

---

## 1) GET /api/energy/v1/health
**Requête**
```
GET ${ENERGY_API_BASE_URL}/api/energy/v1/health
(headers: aucun requis ; un Bearer éventuel est accepté sans erreur)
```
**Réponse 200**
```json
{
  "status": "ok",
  "contract_version": "v1",
  "service": "energy",
  "navixy_configured": true
}
```

---

## 2) POST /api/energy/v1/trips/energy:batch
**Requête**
```
POST ${ENERGY_API_BASE_URL}/api/energy/v1/trips/energy:batch
Headers:
  Authorization: Bearer <ENERGY_API_TOKEN>
  X-Tenant-Id: <tenant_id>            // optionnel si tenant_id fourni dans le body
  Content-Type: application/json
Body:
{
  "tenant_id": "<tenant_id>",
  "trips": [
    { "trip_id": "<trip_id>", "ref": "<vehicle_ref>", "start": "<ISO8601>", "end": "<ISO8601>" }
  ]
}
```
- `ref` = vehicle_id opaque Journal (résolu en interne vers `navixy_tracker_id`).
- Limite : **100 trajets** par requête (au-delà → `413`).

**Réponse 200** (un résultat indépendant par trajet ; L et kWh séparés)
```json
{
  "tenant_id": "<tenant_id>",
  "count": 1,
  "results": [
    {
      "trip_id": "<trip_id>",
      "ref": "<vehicle_ref>",
      "tracker_id": null,
      "status": "<NO_ENERGY_DATA | MAPPING_INVALID>",
      "powertrain": "<ICE_PETROL | ICE_DIESEL | HYBRID | PHEV | BEV | UNKNOWN>",
      "window": { "start": "<ISO8601>", "end": "<ISO8601>" },
      "fuel": {
        "fuel_liters": <METRIC>,
        "consumption_l_100km": <METRIC>
      },
      "electric": {
        "soc_start_pct": <METRIC>,
        "soc_end_pct": <METRIC>,
        "energy_kwh": <METRIC>,
        "consumption_kwh_100km": <METRIC>
      }
    }
  ]
}
```
**Erreurs** : `401` (token absent/invalide) · `400` (tenant mismatch/absent, `trips` non-liste) · `413` (>100).

---

## 3) GET /api/energy/v1/fleet/summary
**Requête**
```
GET ${ENERGY_API_BASE_URL}/api/energy/v1/fleet/summary?tenant_id=<tenant_id>
Headers:
  Authorization: Bearer <ENERGY_API_TOKEN>
  X-Tenant-Id: <tenant_id>            // optionnel si tenant_id en query
```
**Réponse 200** (`metrics` contient EXACTEMENT ces 6 clés)
```json
{
  "tenant_id": "<tenant_id>",
  "trackers_total": <int>,
  "trackers_associated": <int>,
  "powertrain_distribution": { "UNKNOWN": <int> },
  "fuel_level_quality": { "AVAILABLE": <int>, "STALE": <int>, "UNAVAILABLE": <int> },
  "metrics": {
    "thermal_consumption_l_100km": <METRIC>,
    "electric_consumption_kwh_100km": <METRIC>,
    "fuel_liters_total": <METRIC>,
    "electric_kwh_total": <METRIC>,
    "obd_coverage_pct": <METRIC>,
    "vehicles_with_data": <METRIC>
  },
  "note": "<agrégats sur données prouvées ; absence = UNAVAILABLE, jamais 0 ; L et kWh jamais mélangés>"
}
```
**Erreurs** : `401` · `400` (tenant mismatch/absent).

---

## 4) GET /api/energy/v1/vehicles/{ref}/summary
**Requête**
```
GET ${ENERGY_API_BASE_URL}/api/energy/v1/vehicles/<vehicle_ref>/summary?tenant_id=<tenant_id>
Headers:
  Authorization: Bearer <ENERGY_API_TOKEN>
  X-Tenant-Id: <tenant_id>            // optionnel si tenant_id en query
```
- `{ref}` = vehicle_id opaque Journal → résolu en interne vers `navixy_tracker_id`
  (identifiants prouvés uniquement ; jamais nom/plaque/modèle).

**Réponse 200** (`metrics` contient EXACTEMENT ces 2 clés)
```json
{
  "ref": "<vehicle_ref>",
  "tenant_id": "<tenant_id>",
  "tracker_id": <int>,
  "vehicle_id": null,
  "vin": null,
  "powertrain": "<... | UNKNOWN>",
  "connection_status": "<active | offline | ...>",
  "metrics": {
    "fuel_liters_total": <METRIC>,
    "energy_kwh_total": <METRIC>
  }
}
```
**Réponse 404** (mapping invalide — `ref` non résolu à un identifiant prouvé)
```json
{ "detail": { "ref": "<vehicle_ref>", "tenant_id": "<tenant_id>", "mapping": "INVALID", "reason": "<...>" } }
```
**Erreurs** : `401` · `400` (tenant mismatch/absent) · `404` (mapping invalide).
