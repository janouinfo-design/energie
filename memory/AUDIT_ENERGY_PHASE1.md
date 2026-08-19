# LOGITRAK — Projet ÉNERGIE — Rapport d'Audit Phase 1
Plateforme réelle auditée : Navixy EU `api.eu.navixy.com/v2` — PaaS 13588 (login.logitrak.fr, devise CHF).
Auth : paramètre `hash` (clé stockée server-side dans `backend/.env` → `NAVIXY_API_KEY`, jamais hardcodée).
Périmètre : audit des SOURCES DE DONNÉES réelles (lecture seule). Aucun code produit modifié.

## 0. STATUT DU LIVRABLE
- RÉALISÉ  : Audit des sources de données Navixy réelles (endpoints, métriques, unités, capability map, fraîcheur) — prouvé par appels live.
- PARTIEL  : Contrat API Energy→Journal (proposé ci-dessous, à valider ; dépend d'endpoints internes non encore codés).
- NON RÉALISÉ : Audit du CODE applicatif Énergie (le code existant n'a pas encore été fourni dans /app — workspace = template vierge).
- NON RÉALISÉ : Fallback VIN via projet Documents (Documents "pas encore disponible" → EV/estimations REFERENCE non alimentables aujourd'hui).

## 1. ARCHITECTURE ACTUELLE (côté données)
- Flotte : **12 trackers**, **8 véhicules**.
- Devices : Teltonika FMC130 / FMB003-FMC003 (OBD/CAN) + 1 smartphone (iosnavixytracker → PAS de CAN/OBD).
- `vehicle/list` : **tracker_id = null** et **vin = ""** pour TOUS → aucun lien véhicule↔tracker ni VIN côté fleet.
- Le VIN RÉEL est porté par le tracker dans `get_diagnostics.states.obd_vin`.
- Workspace /app : template Emergent vierge (backend 88 lignes, DB propre `MONGO_URL`/`DB_NAME`). Aucun module Énergie codé.

## 2. ENDPOINTS NAVIXY (testés en live)
VALIDES ✅
- `user/get_info` — plateforme/paas.
- `tracker/list` — 12 trackers (id, label, source.model, device_id).
- `vehicle/list` — 8 véhicules (tracker_id null, vin vide).
- `tracker/get_states` (batch `trackers[]`) — connection_status, movement_status, gps.updated, last_update, ignition[] → **base AVAILABLE/STALE**.
- `tracker/get_diagnostics` — `inputs[]` (OBD live) + `states{}` (obd_vin, obd_dtc_number, obd_mil_activated_distance, obd_dtc_cleared_distance, can_*).
- `tracker/get_readings` — toutes valeurs metering (board_voltage, etc.).
- `tracker/get_fuel` — obd_fuel + can_consumption (litre).
- `tracker/get_counters` — odometer (km), engine_hours.
- `tracker/sensor/list` — **capteurs CONFIGURÉS** (type, sensor_type, name, input_number).
- `track/list` (from/to) — trajets : id, start_date, end_date, length(km), avg/max speed.
- `history/tracker/list` — journal d'ÉVÉNEMENTS (speedup…), pas de valeurs capteurs.

INVALIDES ❌ (à ne pas utiliser)
- `tracker/readings`, `sensor/list`, `tracker/get_history`, `tracker/sensor/history`,
  `tracker/get_diagnostics_history`, `tracker/get_fuel_consumption`.
- Historique de valeurs capteurs/carburant sur période ⇒ via moteur de **rapports** `report/tracker/*` (param `plugin` obligatoire), non via endpoint temps réel.

## 3. MÉTRIQUES RÉELLEMENT DISPONIBLES (par preuve)
Exemple ICE frais — AUDI 781479 (VIN WAUZZZ8V0JA152970) :
- obd_fuel = 30.66 (niveau réservoir), can_consumption "Carburant Consommé" = 28.0 (max 42 ≈ capacité).
- obd_speed=9.0, obd_coolant_t=85.0, obd_control_module_voltage=12.94, obd_rpm=855, obd_throttle=0, obd_absolute_load=14.
- states : obd_vin, obd_dtc_number=0, obd_mil_activated_distance=0, obd_dtc_cleared_distance=383.
- counters : odometer=138357.0 km, engine_hours=1228.5.

## 4. UNITÉS RÉELLEMENT VÉRIFIÉES (source = `units_type` Navixy)
VÉRIFIÉES (exploitables) :
- speed = **kmh** | fuel / fuel_consumption / can_consumption = **litre** | temperature/coolant = **celsius**
- power / control_module_voltage / board_voltage = **volt** | throttle / absolute_load = **percent** | run_time = **second**
- counters : odometer = **km**, engine_hours = **h**.
NON VÉRIFIÉES / AMBIGUËS (units_type=custom → NE PAS exploiter en prod tel quel) :
- obd_rpm, "Kilométrage" (custom), "papillon", "Valeur absolue de charge", "Moment/Durée…".

## 5. CAPABILITY MAP (réelle, par type d'énergie)
| Métrique                | ICE AUDI 781479 | BEV (Enyaq/BMW/EX30) | Smartphone |
|-------------------------|-----------------|----------------------|-----------|
| Position/vitesse GPS    | AVAILABLE       | STALE                | AVAILABLE |
| odometer / engine_hours | AVAILABLE       | STALE                | UNAVAILABLE|
| fuel level (L)          | AVAILABLE(MEASURED) | UNAVAILABLE (capteur "fuel" = null, unité percent) | UNAVAILABLE |
| fuel consumed (L)       | AVAILABLE(MEASURED) | UNAVAILABLE        | UNAVAILABLE |
| coolant / voltage / OBD | AVAILABLE       | STALE/null           | UNAVAILABLE |
| VIN (states.obd_vin)    | AVAILABLE       | AVAILABLE (mais incohérent label) | UNAVAILABLE |
| **SoC (%)**             | N/A (ICE)       | **UNAVAILABLE (aucun capteur)** | N/A |
| **energy_used kWh**     | N/A             | **UNAVAILABLE (aucun capteur)** | N/A |
| **kWh/100km**           | N/A             | **UNAVAILABLE**      | N/A |
| **autonomie/range**     | N/A             | **UNAVAILABLE**      | N/A |
Constat majeur : **les 5 trackers "EV" ont exactement les mêmes 12 capteurs OBD-ICE génériques ; AUCUN capteur SoC/batterie/kWh/HV n'est configuré.** ⇒ toute donnée énergie EV = UNAVAILABLE aujourd'hui (source : aucun capteur). Seule voie future = ESTIMATED via reference_consumption_kwh_100 (Documents), indisponible actuellement.

## 6. SOURCES & HIÉRARCHIE (Phase 3)
1. OBD/CAN vérifié (Navixy) → aujourd'hui : uniquement ICE AUDI (fuel/counters/coolant).
2. Spec véhicule (Documents/VIN) → INDISPONIBLE (Documents non livré).
3. Base VIN constructeur → non intégrée.
4. Config manuelle → non définie.
5. Sinon UNAVAILABLE. VIN utilisable via states.obd_vin (à fiabiliser).

## 7. PROBLÈMES IDENTIFIÉS
- P1 (bloquant mapping) : `vehicle/list.tracker_id=null` + `vin=""` → pas de lien véhicule↔tracker. Mapping à établir via `states.obd_vin` ou table de correspondance.
- P2 (fiabilité) : labels trackers FAUX (ex. "KAIO Skoda Enyaq 07" → VIN BMW `WBY8P210607G21308` ; "KAIO Renault Zoe" → VIN BMW `WBY8P210407G21341`). Ne pas déduire la motorisation depuis le label.
- P3 (EV) : aucune donnée énergie électrique collectée (config capteurs = OBD ICE). Motorisation ≠ capabilities (Phase 2 respectée : energy_type peut être ELECTRIC avec soc=UNAVAILABLE).
- P4 (staleness) : majorité des EV STALE (2024/2025). Nécessite statut AVAILABLE/STALE/UNAVAILABLE calculé depuis get_states + update_time par capteur.
- P5 (unités custom) : rpm/kilométrage/throttle en `custom` → non exploitables sans confirmation.
- P6 (zéro≠indispo, Phase 8) : board_voltage EV=0.0 et obd_fuel EV=null → ne jamais afficher 0 comme mesure.
- P7 (historique) : pas d'endpoint temps réel d'historique capteurs → dépend des rapports Navixy (async, plugin).

## 8. CONTRAT PROPOSÉ Energy → Journal (v1, à valider)
Enveloppe standard par métrique :
`{ value, unit, availability(AVAILABLE|STALE|UNAVAILABLE), measurement_type(MEASURED|ESTIMATED|REFERENCE), source(OBD|CAN|VEHICLE_SPEC|MANUAL), timestamp }`
Endpoints (préfixe `/api`, multi-tenant, RBAC) :
- A `GET /api/energy/vehicles/{id}/summary` — energy_type + KPIs (fuel level, conso récente, odometer…).
- B `GET /api/energy/vehicles/{id}/capabilities` — capability map (quels champs MEASURED/UNAVAILABLE).
- C `GET /api/energy/vehicles/{id}/consumption?from&to` — conso période (L / kWh) avec statut par champ.
- D `GET /api/energy/vehicles/{id}/trip-energy?start&end` — énergie par trajet (fuel_used_l, consumption_l_100 ICE ; soc_start/end, energy_used_kwh EV — statut par champ).
- E `GET /api/energy/vehicles/{id}/quality` — fraîcheur/source/staleness.
Règles : Journal CONSOMME, ne recalcule pas. Zéro ≠ indisponible. Réponse jamais "entièrement MEASURED" si un champ est ESTIMATED/UNAVAILABLE.

## 9. MODIFICATIONS NÉCESSAIRES (avant implémentation)
1. Fournir le CODE Énergie existant (pour auditer modèles/collections/endpoints réels) — sinon build from scratch.
2. Établir mapping véhicule↔tracker (via obd_vin) — corriger P1/P2.
3. (Optionnel EV) Configurer capteurs SoC/batterie côté Navixy si le device le supporte, sinon EV=ESTIMATED via Documents.
4. Livrer l'API Documents (specs/VIN) pour activer les estimations REFERENCE (Phases 4/5).
5. Définir cache par type (position court, KPI court/moyen, historique long) et isolation tenant.

## 10. PHASE 2 — SOCLE IMPLÉMENTÉ (preuves réelles)
Livré (build from scratch, workspace vierge confirmé). Backend testé : 57/57 assertions OK.
- Enveloppe contrat enrichie : `availability`(AVAILABLE|UNAVAILABLE|STALE|ERROR) + `measurement_type`(MEASURED|ESTIMATED|REFERENCE|NONE) + `source`(NAVIXY_OBD|NAVIXY_CAN|NAVIXY_STATE|NAVIXY_COUNTER|DOCUMENTS|CALCULATED|NONE) + value/unit/unit_verified/timestamp/reason.
- Client Navixy READ-ONLY (whitelist stricte, aucun endpoint d'écriture).
- Mapping canonique vehicle↔tracker↔VIN : confiance HIGH/MEDIUM/NONE, provenance, JAMAIS depuis le label.
- Anomalies détectées (sync réel, tenant paas_13588) : NO_ENERGY_TELEMETRY=12, STALE_DATA=7, TRACKER_WITHOUT_VEHICLE=9, VEHICLE_WITHOUT_TRACKER=5, VIN_ABSENT=8.
- Audit capacité EV : aucun capteur SoC/batterie/kWh/range → toutes métriques EV UNAVAILABLE `no_sensor_configured` (aucune simulation).
- Règles vérifiées par tests : 0≠null, UNAVAILABLE≠0, STALE≠frais, unité `custom`→unit_verified=false, REFERENCE jamais MEASURED.
- Fichiers backend : energy/{enums,models,navixy_client,normalization,capability_service,mapping_service,service,routes}.py ; server.py (montage router) ; requirements (httpx) ; .env (NAVIXY_*, ENERGY_STALE_HOURS).
- Frontend : src/components/EnergyAudit.js (visualisation mapping/anomalies/capabilities, N/A jamais 0).
- Endpoints socle : /api/energy/{health,sync(POST),mapping,anomalies,trackers/{id}/capabilities,trackers/{id}/metrics,sync-runs}.
- Écritures Navixy : AUCUNE (lecture seule stricte).

NON RÉALISÉ (assumé, sans fallback inventé) :
- Contrat complet Energy→Journal A–E (volontairement hors Phase 2).
- Fallback VIN/specs via Documents (projet non livré) → estimations REFERENCE non alimentables.
- SoC/kWh/range EV : techniquement impossible aujourd'hui (aucun capteur configuré) → UNAVAILABLE, pas de fallback.
- Détection MAPPING_CHANGED (nécessite historique multi-run) : champ prévu, non actif.
- RBAC/auth utilisateur : non implémenté (tenant_id isolé et appliqué à toutes les requêtes ; RBAC = phase ultérieure).

## 11. PHASE 2.1 — FIABILISATION IDENTITÉ + FAISABILITÉ EV (preuves réelles, backend 71/71, UI 9/9)
### Propositions de correction Navixy (AUCUNE écriture)
- Endpoint `GET /api/energy/mapping-proposals`. Classées SAFE_TO_REVIEW / AMBIGUOUS / INSUFFICIENT_DATA.
- Champs : anomaly, classification, tracker_id, vehicle_id, current_label (contexte seul), vehicle_vin, obd_vin, proposed_match, evidence[], recommended_action, confidence.
- Résultat réel : 14 propositions, toutes INSUFFICIENT_DATA (car `vehicle.vin` vide partout → aucun match prouvé). JAMAIS de proposition basée sur le label (vérifié par tests). Aucune écriture Navixy.

### Faisabilité EV (evidence-based, modèles réels du compte)
- Endpoint `GET /api/energy/ev-feasibility`. Familles réelles : fmc130=6, fmb003=4, phone=2.
- Canaux par métrique : NATIVE/VIA_OBD/VIA_CAN/NEEDS_NAVIXY_CONFIG/NEEDS_TRACKER_CONFIG/NEEDS_HARDWARE/NOT_SUPPORTED/NOT_VERIFIABLE.
- Conclusion prouvée : SoC EV non collectable aujourd'hui. FMC130 → NEEDS_HARDWARE (adaptateur CAN LV-CAN200/ALL-CAN300 + profil + config Navixy + véhicule dans la liste supportée Teltonika) ; FMB003 → NOT_VERIFIABLE (pas d'adaptateur CAN, dépend de l'OBD véhicule) ; smartphones → NOT_SUPPORTED. Aucun SoC/kWh estimé. Preuves : wiki Teltonika (FMC130_CAN_adapters, CAN_Adapters, OBD_supported_vehicle_list) + datasheet FMB003.

### Historique de mapping + MAPPING_CHANGED (activé)
- Collections `energy_mapping_history` (tracker_id, vehicle_id, obd_vin, source, confidence, first_seen, last_seen) et `energy_mapping_changes` (audit trail).
- Détection : NEW_ASSOCIATION / TRACKER_CHANGE / VIN_CHANGE / ASSOCIATION_REMOVED / CONFLICT.
- Réel : 6 NEW_ASSOCIATION au 1er sync ; 2e sync = 0 nouveau (idempotent, vérifié).

### Readiness (recommandation démarrage A–E)
- Endpoint `GET /api/energy/readiness`. Résultat : NOT_READY_FOR_A_E.
- KPIs réels : trackers associés 25.0% · véhicules associés 37.5% · couverture VIN (physiques) 40.0% · énergie thermique 25.0% · énergie EV 0.0% · stale 7 · anomalies bloquantes 0.
- Raison : <90% de trackers fiablement associés → ne pas démarrer A–E avant fiabilisation identité.

### Fichiers Phase 2.1
- Backend : energy/ev_feasibility.py, energy/mapping_proposals.py ; extensions energy/{enums,service,routes}.py.
- Frontend : src/components/EnergyAudit.js (onglets Propositions/Faisabilité EV/Changements + bannière Readiness).
- Endpoints ajoutés : /api/energy/{mapping-proposals, ev-feasibility, mapping-changes, readiness}.
