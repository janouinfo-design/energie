#!/usr/bin/env python3
"""
Comprehensive contractual + security + REAL NAVIXY test of LOGITRAK Energy v1 (Journal-facing).
Tests all contract routes, auth, tenant isolation, limits, rules, and real Navixy data.
"""
import os
import sys
import time
import json
import requests
from typing import Dict, Any, List, Optional, Tuple

# Configuration
BASE_URL = "https://energy-telemetry-1.preview.emergentagent.com"
VALID_TOKEN = "3N5HmYTEbKf58YXgAM7LkTAzmVNa6nhBkO761jNhp_cSZsw7OuyH1M4OXSnf_QBM"
TENANT_ID = "paas_13588"
TRACKER_ID_VALID = 781479
TRACKER_ID_INVALID = 999999

# Test results tracking
test_results = {
    "passed": 0,
    "failed": 0,
    "details": []
}


def log_test(section: str, test_name: str, passed: bool, details: str = ""):
    """Log test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    msg = f"{status} | {section} | {test_name}"
    if details:
        msg += f" | {details}"
    print(msg)
    
    test_results["details"].append({
        "section": section,
        "test": test_name,
        "passed": passed,
        "details": details
    })
    
    if passed:
        test_results["passed"] += 1
    else:
        test_results["failed"] += 1


def check_no_secret_in_response(response_data: Any, test_name: str) -> bool:
    """Verify no token/secret is exposed in response."""
    response_str = json.dumps(response_data) if isinstance(response_data, dict) else str(response_data)
    if "3N5HmYTEbKf58YXgAM7LkTAzmVNa6nhBkO761jNhp_cSZsw7OuyH1M4OXSnf_QBM" in response_str:
        log_test("SECURITY", test_name, False, "Token exposed in response!")
        return False
    return True


def test_1a_health_public():
    """1a. GET /api/energy/v1/health (NO token) -> 200, correct fields, no secret."""
    section = "1. CONTRACT ROUTES"
    test_name = "1a. Health endpoint (public, no token)"
    
    try:
        resp = requests.get(f"{BASE_URL}/api/energy/v1/health", timeout=10)
        data = resp.json()
        
        # Check status code
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Expected 200, got {resp.status_code}")
            return
        
        # Check required fields
        checks = [
            ("status", "ok"),
            ("contract_version", "v1"),
            ("service", "energy"),
        ]
        
        for field, expected in checks:
            if data.get(field) != expected:
                log_test(section, test_name, False, f"{field}={data.get(field)}, expected {expected}")
                return
        
        # Check navixy_configured is present (boolean)
        if "navixy_configured" not in data:
            log_test(section, test_name, False, "navixy_configured field missing")
            return
        
        # Check no token/secret field
        if any(k in data for k in ["token", "secret", "api_key", "bearer"]):
            log_test(section, test_name, False, "Response contains token/secret field")
            return
        
        # Check no secret value exposed
        if not check_no_secret_in_response(data, test_name):
            return
        
        log_test(section, test_name, True, f"status=ok, contract_version=v1, service=energy, navixy_configured={data.get('navixy_configured')}")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_1b_vehicle_summary_valid():
    """1b. GET /api/energy/v1/vehicles/781479/summary?tenant_id=paas_13588 (valid token)."""
    section = "1. CONTRACT ROUTES"
    test_name = "1b. Vehicle summary (valid tracker 781479)"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Expected 200, got {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        
        # Verify tracker_id
        if data.get("tracker_id") != TRACKER_ID_VALID:
            log_test(section, test_name, False, f"tracker_id={data.get('tracker_id')}, expected {TRACKER_ID_VALID}")
            return
        
        # Verify VIN
        if data.get("vin") != "WAUZZZ8V0JA152970":
            log_test(section, test_name, False, f"vin={data.get('vin')}, expected WAUZZZ8V0JA152970")
            return
        
        # Verify powertrain
        if data.get("powertrain") != "UNKNOWN":
            log_test(section, test_name, False, f"powertrain={data.get('powertrain')}, expected UNKNOWN")
            return
        
        # Check metrics structure
        metrics = data.get("metrics", {})
        if not metrics:
            log_test(section, test_name, False, "metrics field missing or empty")
            return
        
        # Check fuel_level metric
        fuel_level = metrics.get("fuel_level", {})
        if fuel_level.get("availability") != "STALE":
            log_test(section, test_name, False, f"fuel_level.availability={fuel_level.get('availability')}, expected STALE")
            return
        
        if fuel_level.get("measurement_type") != "MEASURED":
            log_test(section, test_name, False, f"fuel_level.measurement_type={fuel_level.get('measurement_type')}, expected MEASURED")
            return
        
        if fuel_level.get("source") != "NAVIXY_OBD":
            log_test(section, test_name, False, f"fuel_level.source={fuel_level.get('source')}, expected NAVIXY_OBD")
            return
        
        # Check value is approximately 30.66 (NOT 0)
        fuel_value = fuel_level.get("value")
        if fuel_value is None or fuel_value == 0:
            log_test(section, test_name, False, f"fuel_level.value={fuel_value}, expected ~30.66 (NOT 0 or null)")
            return
        
        if not (29 < fuel_value < 32):
            log_test(section, test_name, False, f"fuel_level.value={fuel_value}, expected ~30.66")
            return
        
        # Check odometer
        odometer = metrics.get("odometer", {})
        if odometer.get("availability") != "AVAILABLE":
            log_test(section, test_name, False, f"odometer.availability={odometer.get('availability')}, expected AVAILABLE")
            return
        
        # CRITICAL: Check UNAVAILABLE metrics have value=null and measurement_type=null (NOT "NONE")
        for metric_key in ["fuel_consumed", "coolant_temp"]:
            metric = metrics.get(metric_key, {})
            if metric.get("availability") == "UNAVAILABLE":
                if metric.get("value") is not None:
                    log_test(section, test_name, False, f"{metric_key}.value={metric.get('value')}, expected null for UNAVAILABLE")
                    return
                if metric.get("measurement_type") is not None:
                    log_test(section, test_name, False, f"{metric_key}.measurement_type={metric.get('measurement_type')}, expected null (NOT 'NONE') for UNAVAILABLE")
                    return
        
        # Check no "ERROR" availability
        for metric_key, metric in metrics.items():
            if metric.get("availability") == "ERROR":
                log_test(section, test_name, False, f"{metric_key}.availability=ERROR, must NEVER appear in v1")
                return
        
        # Check no "NONE" measurement_type
        for metric_key, metric in metrics.items():
            if metric.get("measurement_type") == "NONE":
                log_test(section, test_name, False, f"{metric_key}.measurement_type='NONE', must NEVER appear in v1")
                return
        
        log_test(section, test_name, True, f"tracker_id={TRACKER_ID_VALID}, vin=WAUZZZ8V0JA152970, powertrain=UNKNOWN, fuel_level STALE/MEASURED/NAVIXY_OBD ~{fuel_value:.2f}L, odometer AVAILABLE")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_1c_vehicle_summary_invalid():
    """1c. GET /api/energy/v1/vehicles/999999/summary?tenant_id=paas_13588 (valid token) -> 404."""
    section = "1. CONTRACT ROUTES"
    test_name = "1c. Vehicle summary (invalid tracker 999999)"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_INVALID}/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 404:
            log_test(section, test_name, False, f"Expected 404, got {resp.status_code}")
            return
        
        data = resp.json()
        
        # FastAPI wraps HTTPException body in 'detail' field
        body = data.get("detail", data)
        
        # Check mapping field indicates invalid
        if "mapping" not in body or body.get("mapping") != "INVALID":
            log_test(section, test_name, False, f"Expected mapping=INVALID in response, got {body}")
            return
        
        log_test(section, test_name, True, f"404 with mapping=INVALID")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_1d_fleet_summary():
    """1d. GET /api/energy/v1/fleet/summary?tenant_id=paas_13588 (valid token) -> 200."""
    section = "1. CONTRACT ROUTES"
    test_name = "1d. Fleet summary"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/fleet/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Expected 200, got {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        
        # Verify trackers_total
        if data.get("trackers_total") != 12:
            log_test(section, test_name, False, f"trackers_total={data.get('trackers_total')}, expected 12")
            return
        
        # Verify powertrain_distribution shows UNKNOWN=12 (UNKNOWN not treated as ICE)
        powertrain_dist = data.get("powertrain_distribution", {})
        if powertrain_dist.get("UNKNOWN") != 12:
            log_test(section, test_name, False, f"powertrain_distribution.UNKNOWN={powertrain_dist.get('UNKNOWN')}, expected 12")
            return
        
        # Check no ICE/BEV/HEV keys (all are UNKNOWN)
        if any(k in powertrain_dist for k in ["ICE", "BEV", "HEV", "PHEV"]):
            log_test(section, test_name, False, f"powertrain_distribution has ICE/BEV/HEV keys, expected only UNKNOWN: {powertrain_dist}")
            return
        
        # Verify fuel_level_quality has AVAILABLE/STALE/UNAVAILABLE counts
        fuel_quality = data.get("fuel_level_quality", {})
        if not all(k in fuel_quality for k in ["AVAILABLE", "STALE", "UNAVAILABLE"]):
            log_test(section, test_name, False, f"fuel_level_quality missing keys: {fuel_quality}")
            return
        
        # Verify ev_energy.status="UNAVAILABLE" (NOT zeroed)
        ev_energy = data.get("ev_energy", {})
        if ev_energy.get("status") != "UNAVAILABLE":
            log_test(section, test_name, False, f"ev_energy.status={ev_energy.get('status')}, expected UNAVAILABLE")
            return
        
        # Confirm no field mixes litres and kWh
        data_str = json.dumps(data)
        if "fuel_kwh" in data_str or "energy_l" in data_str:
            log_test(section, test_name, False, "Response mixes litres and kWh units")
            return
        
        log_test(section, test_name, True, f"trackers_total=12, powertrain UNKNOWN=12, fuel_quality={fuel_quality}, ev_energy.status=UNAVAILABLE")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_1e_trips_batch():
    """1e. POST /api/energy/v1/trips/energy:batch with 2 trips (1 valid, 1 invalid)."""
    section = "1. CONTRACT ROUTES"
    test_name = "1e. Trips energy batch (2 trips: 1 valid, 1 invalid)"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        payload = {
            "tenant_id": TENANT_ID,
            "trips": [
                {
                    "trip_id": "A",
                    "ref": TRACKER_ID_VALID,
                    "start": "2026-08-18T08:00:00Z",
                    "end": "2026-08-18T08:40:00Z"
                },
                {
                    "trip_id": "B",
                    "ref": TRACKER_ID_INVALID,
                    "start": "2026-08-18T09:00:00Z",
                    "end": "2026-08-18T09:30:00Z"
                }
            ]
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/energy/v1/trips/energy:batch",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Expected 200, got {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        
        # Verify results is a list of 2 items
        results = data.get("results", [])
        if len(results) != 2:
            log_test(section, test_name, False, f"Expected 2 results, got {len(results)}")
            return
        
        # Trip A: status NO_ENERGY_DATA, tracker_id 781479
        trip_a = results[0]
        if trip_a.get("trip_id") != "A":
            log_test(section, test_name, False, f"Trip A trip_id={trip_a.get('trip_id')}, expected 'A'")
            return
        
        if trip_a.get("status") != "NO_ENERGY_DATA":
            log_test(section, test_name, False, f"Trip A status={trip_a.get('status')}, expected NO_ENERGY_DATA")
            return
        
        if trip_a.get("tracker_id") != TRACKER_ID_VALID:
            log_test(section, test_name, False, f"Trip A tracker_id={trip_a.get('tracker_id')}, expected {TRACKER_ID_VALID}")
            return
        
        # Check energy block has SEPARATE keys
        energy_a = trip_a.get("energy", {})
        required_keys = ["fuel_used_l", "consumption_l_100", "energy_kwh", "consumption_kwh_100", "soc_start", "soc_end"]
        if not all(k in energy_a for k in required_keys):
            log_test(section, test_name, False, f"Trip A energy block missing keys: {energy_a.keys()}")
            return
        
        # All should be UNAVAILABLE with value=null
        for key in required_keys:
            metric = energy_a.get(key, {})
            if metric.get("availability") != "UNAVAILABLE":
                log_test(section, test_name, False, f"Trip A energy.{key}.availability={metric.get('availability')}, expected UNAVAILABLE")
                return
            if metric.get("value") is not None:
                log_test(section, test_name, False, f"Trip A energy.{key}.value={metric.get('value')}, expected null")
                return
            # Check measurement_type is null (NOT "NONE")
            if metric.get("measurement_type") is not None:
                log_test(section, test_name, False, f"Trip A energy.{key}.measurement_type={metric.get('measurement_type')}, expected null (NOT 'NONE')")
                return
        
        # Trip B: status MAPPING_INVALID, tracker_id null
        trip_b = results[1]
        if trip_b.get("trip_id") != "B":
            log_test(section, test_name, False, f"Trip B trip_id={trip_b.get('trip_id')}, expected 'B'")
            return
        
        if trip_b.get("status") != "MAPPING_INVALID":
            log_test(section, test_name, False, f"Trip B status={trip_b.get('status')}, expected MAPPING_INVALID")
            return
        
        if trip_b.get("tracker_id") is not None:
            log_test(section, test_name, False, f"Trip B tracker_id={trip_b.get('tracker_id')}, expected null")
            return
        
        # Powertrain stays UNKNOWN for both
        if trip_a.get("powertrain") != "UNKNOWN":
            log_test(section, test_name, False, f"Trip A powertrain={trip_a.get('powertrain')}, expected UNKNOWN")
            return
        
        if trip_b.get("powertrain") != "UNKNOWN":
            log_test(section, test_name, False, f"Trip B powertrain={trip_b.get('powertrain')}, expected UNKNOWN")
            return
        
        log_test(section, test_name, True, "Trip A: NO_ENERGY_DATA/tracker_id=781479/energy UNAVAILABLE/null, Trip B: MAPPING_INVALID/tracker_id=null, both powertrain=UNKNOWN")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_2a_auth_no_token():
    """2a. Data routes WITHOUT token -> 401."""
    section = "2. AUTH"
    test_name = "2a. Data routes without token (401)"
    
    routes = [
        f"/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary?tenant_id={TENANT_ID}",
        f"/api/energy/v1/fleet/summary?tenant_id={TENANT_ID}",
    ]
    
    try:
        for route in routes:
            resp = requests.get(f"{BASE_URL}{route}", timeout=10)
            if resp.status_code != 401:
                log_test(section, test_name, False, f"Route {route} returned {resp.status_code}, expected 401")
                return
            
            # Check no secret in 401 response
            if not check_no_secret_in_response(resp.text, test_name):
                return
        
        # Test POST /sync
        resp = requests.post(f"{BASE_URL}/api/energy/sync", json={"tenant_id": TENANT_ID}, timeout=10)
        if resp.status_code != 401:
            log_test(section, test_name, False, f"POST /sync returned {resp.status_code}, expected 401")
            return
        
        # Test POST trips batch
        resp = requests.post(
            f"{BASE_URL}/api/energy/v1/trips/energy:batch",
            json={"tenant_id": TENANT_ID, "trips": []},
            timeout=10
        )
        if resp.status_code != 401:
            log_test(section, test_name, False, f"POST trips batch returned {resp.status_code}, expected 401")
            return
        
        log_test(section, test_name, True, "All data routes return 401 without token")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_2b_auth_wrong_token():
    """2b. With wrong token or wrong scheme -> 401."""
    section = "2. AUTH"
    test_name = "2b. Wrong token / wrong scheme (401)"
    
    try:
        # Wrong token
        headers = {"Authorization": "Bearer wrong"}
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        if resp.status_code != 401:
            log_test(section, test_name, False, f"Wrong token returned {resp.status_code}, expected 401")
            return
        
        # Wrong scheme
        headers = {"Authorization": "Basic x"}
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        if resp.status_code != 401:
            log_test(section, test_name, False, f"Wrong scheme returned {resp.status_code}, expected 401")
            return
        
        log_test(section, test_name, True, "Wrong token and wrong scheme both return 401")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_2c_health_no_secret():
    """2c. Health works WITHOUT token, no secret leaked."""
    section = "2. AUTH"
    test_name = "2c. Health public, no secret leaked"
    
    try:
        resp = requests.get(f"{BASE_URL}/api/energy/v1/health", timeout=10)
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Health returned {resp.status_code}, expected 200")
            return
        
        data = resp.json()
        
        # Check no secret in response
        if not check_no_secret_in_response(data, test_name):
            return
        
        # Check no 401 body contains secret
        resp_401 = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary",
            params={"tenant_id": TENANT_ID},
            timeout=10
        )
        if not check_no_secret_in_response(resp_401.text, test_name):
            return
        
        log_test(section, test_name, True, "Health public, no secret leaked in any response")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_3a_tenant_isolation_nonexistent():
    """3a. Vehicle summary with tenant_id=paas_DOESNOTEXIST -> 404."""
    section = "3. TENANT ISOLATION / IDOR"
    test_name = "3a. Non-existent tenant (404)"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary",
            params={"tenant_id": "paas_DOESNOTEXIST"},
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 404:
            log_test(section, test_name, False, f"Expected 404, got {resp.status_code}: {resp.text}")
            return
        
        log_test(section, test_name, True, "Non-existent tenant returns 404 (no cross-tenant leak)")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_3b_tenant_mismatch():
    """3b. Tenant mismatch: query tenant_id=paas_13588 AND header X-Tenant-Id: paas_OTHER -> 400."""
    section = "3. TENANT ISOLATION / IDOR"
    test_name = "3b. Tenant mismatch (400)"
    
    try:
        headers = {
            "Authorization": f"Bearer {VALID_TOKEN}",
            "X-Tenant-Id": "paas_OTHER"
        }
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 400:
            log_test(section, test_name, False, f"Expected 400, got {resp.status_code}: {resp.text}")
            return
        
        log_test(section, test_name, True, "Tenant mismatch returns 400")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_3c_missing_tenant():
    """3c. Missing tenant entirely (no query, no header) -> 400."""
    section = "3. TENANT ISOLATION / IDOR"
    test_name = "3c. Missing tenant (400)"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        
        # Vehicle summary
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary",
            headers=headers,
            timeout=10
        )
        if resp.status_code != 400:
            log_test(section, test_name, False, f"Vehicle summary returned {resp.status_code}, expected 400")
            return
        
        # Fleet summary
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/fleet/summary",
            headers=headers,
            timeout=10
        )
        if resp.status_code != 400:
            log_test(section, test_name, False, f"Fleet summary returned {resp.status_code}, expected 400")
            return
        
        log_test(section, test_name, True, "Missing tenant returns 400 for both routes")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_3d_batch_cross_tenant():
    """3d. Batch cross-tenant: body tenant_id=paas_13588 but X-Tenant-Id: paas_OTHER -> 400."""
    section = "3. TENANT ISOLATION / IDOR"
    test_name = "3d. Batch cross-tenant (400)"
    
    try:
        headers = {
            "Authorization": f"Bearer {VALID_TOKEN}",
            "X-Tenant-Id": "paas_OTHER"
        }
        payload = {
            "tenant_id": TENANT_ID,
            "trips": [{"trip_id": "X", "ref": TRACKER_ID_VALID, "start": "2026-08-18T08:00:00Z", "end": "2026-08-18T08:40:00Z"}]
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/energy/v1/trips/energy:batch",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 400:
            log_test(section, test_name, False, f"Expected 400, got {resp.status_code}: {resp.text}")
            return
        
        log_test(section, test_name, True, "Batch cross-tenant returns 400 (no leak)")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_3e_batch_header_only():
    """3e. Batch with tenant only via X-Tenant-Id header (no body tenant_id) -> 200."""
    section = "3. TENANT ISOLATION / IDOR"
    test_name = "3e. Batch with header-only tenant (200)"
    
    try:
        headers = {
            "Authorization": f"Bearer {VALID_TOKEN}",
            "X-Tenant-Id": TENANT_ID
        }
        payload = {
            "trips": [{"trip_id": "Y", "ref": TRACKER_ID_VALID, "start": "2026-08-18T08:00:00Z", "end": "2026-08-18T08:40:00Z"}]
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/energy/v1/trips/energy:batch",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Expected 200, got {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        if data.get("tenant_id") != TENANT_ID:
            log_test(section, test_name, False, f"Response tenant_id={data.get('tenant_id')}, expected {TENANT_ID}")
            return
        
        log_test(section, test_name, True, "Batch with header-only tenant returns 200")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_4a_batch_limit():
    """4a. Batch with 101 trips -> 413."""
    section = "4. LIMITS / PARTIAL"
    test_name = "4a. Batch limit 101 trips (413)"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        trips = [
            {"trip_id": f"T{i}", "ref": TRACKER_ID_VALID, "start": "2026-08-18T08:00:00Z", "end": "2026-08-18T08:40:00Z"}
            for i in range(101)
        ]
        payload = {"tenant_id": TENANT_ID, "trips": trips}
        
        resp = requests.post(
            f"{BASE_URL}/api/energy/v1/trips/energy:batch",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 413:
            log_test(section, test_name, False, f"Expected 413, got {resp.status_code}: {resp.text}")
            return
        
        log_test(section, test_name, True, "Batch with 101 trips returns 413")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_4b_batch_partial():
    """4b. Batch with 1 valid + 1 unresolved ref -> both returned independently."""
    section = "4. LIMITS / PARTIAL"
    test_name = "4b. Batch partial (1 valid + 1 invalid)"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        payload = {
            "tenant_id": TENANT_ID,
            "trips": [
                {"trip_id": "VALID", "ref": TRACKER_ID_VALID, "start": "2026-08-18T08:00:00Z", "end": "2026-08-18T08:40:00Z"},
                {"trip_id": "INVALID", "ref": TRACKER_ID_INVALID, "start": "2026-08-18T09:00:00Z", "end": "2026-08-18T09:30:00Z"}
            ]
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/energy/v1/trips/energy:batch",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Expected 200, got {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        results = data.get("results", [])
        
        if len(results) != 2:
            log_test(section, test_name, False, f"Expected 2 results, got {len(results)}")
            return
        
        # Check both are present
        trip_ids = [r.get("trip_id") for r in results]
        if "VALID" not in trip_ids or "INVALID" not in trip_ids:
            log_test(section, test_name, False, f"Missing trip_ids: {trip_ids}")
            return
        
        # Check valid one is not dropped
        valid_trip = next((r for r in results if r.get("trip_id") == "VALID"), None)
        if not valid_trip or valid_trip.get("status") != "NO_ENERGY_DATA":
            log_test(section, test_name, False, f"Valid trip not returned correctly: {valid_trip}")
            return
        
        log_test(section, test_name, True, "Batch partial: both valid and invalid trips returned independently")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_5a_null_not_zero():
    """5a. UNAVAILABLE metrics return value=null (never 0)."""
    section = "5. RULES"
    test_name = "5a. null != 0 (UNAVAILABLE metrics)"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Expected 200, got {resp.status_code}")
            return
        
        data = resp.json()
        metrics = data.get("metrics", {})
        
        # Check UNAVAILABLE metrics have value=null (not 0)
        for metric_key, metric in metrics.items():
            if metric.get("availability") == "UNAVAILABLE":
                if metric.get("value") == 0:
                    log_test(section, test_name, False, f"{metric_key}.value=0 for UNAVAILABLE (should be null)")
                    return
        
        log_test(section, test_name, True, "UNAVAILABLE metrics have value=null (never 0)")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_5b_stale_preserved():
    """5b. STALE preserved: fuel_level for 781479 must remain STALE."""
    section = "5. RULES"
    test_name = "5b. STALE preserved (not promoted to AVAILABLE)"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Expected 200, got {resp.status_code}")
            return
        
        data = resp.json()
        fuel_level = data.get("metrics", {}).get("fuel_level", {})
        
        if fuel_level.get("availability") != "STALE":
            log_test(section, test_name, False, f"fuel_level.availability={fuel_level.get('availability')}, expected STALE")
            return
        
        log_test(section, test_name, True, "fuel_level remains STALE (not promoted to AVAILABLE)")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_5c_no_none_or_error():
    """5c. measurement_type 'NONE' and availability 'ERROR' must NEVER appear in v1."""
    section = "5. RULES"
    test_name = "5c. No 'NONE' measurement_type or 'ERROR' availability"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        
        # Check vehicle summary
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Vehicle summary returned {resp.status_code}")
            return
        
        data = resp.json()
        response_str = json.dumps(data)
        
        # Search for "NONE" measurement_type
        if '"measurement_type": "NONE"' in response_str or '"measurement_type":"NONE"' in response_str:
            log_test(section, test_name, False, "Found measurement_type='NONE' in vehicle summary")
            return
        
        # Search for "ERROR" availability
        if '"availability": "ERROR"' in response_str or '"availability":"ERROR"' in response_str:
            log_test(section, test_name, False, "Found availability='ERROR' in vehicle summary")
            return
        
        # Check fleet summary
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/fleet/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Fleet summary returned {resp.status_code}")
            return
        
        data = resp.json()
        response_str = json.dumps(data)
        
        if '"availability": "ERROR"' in response_str or '"availability":"ERROR"' in response_str:
            log_test(section, test_name, False, "Found availability='ERROR' in fleet summary")
            return
        
        # Check trips batch
        payload = {
            "tenant_id": TENANT_ID,
            "trips": [{"trip_id": "Z", "ref": TRACKER_ID_VALID, "start": "2026-08-18T08:00:00Z", "end": "2026-08-18T08:40:00Z"}]
        }
        resp = requests.post(
            f"{BASE_URL}/api/energy/v1/trips/energy:batch",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Trips batch returned {resp.status_code}")
            return
        
        data = resp.json()
        response_str = json.dumps(data)
        
        if '"measurement_type": "NONE"' in response_str or '"measurement_type":"NONE"' in response_str:
            log_test(section, test_name, False, "Found measurement_type='NONE' in trips batch")
            return
        
        if '"availability": "ERROR"' in response_str or '"availability":"ERROR"' in response_str:
            log_test(section, test_name, False, "Found availability='ERROR' in trips batch")
            return
        
        log_test(section, test_name, True, "No 'NONE' measurement_type or 'ERROR' availability in any v1 response")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_6a_real_navixy_all_trackers():
    """6a. GET all 12 trackers from mapping, then test each vehicle summary."""
    section = "6. REAL NAVIXY"
    test_name = "6a. All 12 trackers (response time < 10s each)"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        
        # Get mapping to list all 12 tracker_ids
        resp = requests.get(
            f"{BASE_URL}/api/energy/mapping",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Mapping endpoint returned {resp.status_code}")
            return
        
        data = resp.json()
        # Mapping endpoint returns {"tenant_id": "...", "mapping": [...]}
        mapping = data.get("mapping", []) if isinstance(data, dict) else data
        if not isinstance(mapping, list) or len(mapping) != 12:
            log_test(section, test_name, False, f"Expected 12 trackers in mapping, got {len(mapping) if isinstance(mapping, list) else 'not a list'}")
            return
        
        # Test each tracker
        tracker_results = []
        for entry in mapping:
            tracker_id = entry.get("tracker_id")
            if not tracker_id:
                log_test(section, test_name, False, f"Mapping entry missing tracker_id: {entry}")
                return
            
            start_time = time.time()
            resp = requests.get(
                f"{BASE_URL}/api/energy/v1/vehicles/{tracker_id}/summary",
                params={"tenant_id": TENANT_ID},
                headers=headers,
                timeout=10
            )
            elapsed = time.time() - start_time
            
            if resp.status_code not in [200, 404]:
                log_test(section, test_name, False, f"Tracker {tracker_id} returned {resp.status_code} (expected 200 or 404)")
                return
            
            if elapsed >= 10:
                log_test(section, test_name, False, f"Tracker {tracker_id} took {elapsed:.2f}s (>= 10s timeout)")
                return
            
            data = resp.json() if resp.status_code == 200 else {}
            powertrain = data.get("powertrain", "N/A")
            fuel_avail = data.get("metrics", {}).get("fuel_level", {}).get("availability", "N/A")
            
            tracker_results.append({
                "tracker_id": tracker_id,
                "http_code": resp.status_code,
                "powertrain": powertrain,
                "fuel_level_availability": fuel_avail,
                "response_time": f"{elapsed:.2f}s"
            })
        
        # Report summary
        details = f"All 12 trackers tested. Sample: {tracker_results[0]}, {tracker_results[1]}, {tracker_results[2]}"
        log_test(section, test_name, True, details)
        
        # Print detailed results
        print("\n=== DETAILED TRACKER RESULTS ===")
        for result in tracker_results:
            print(f"  Tracker {result['tracker_id']}: HTTP {result['http_code']}, powertrain={result['powertrain']}, fuel_level={result['fuel_level_availability']}, time={result['response_time']}")
        print("=================================\n")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_7a_regression_socle():
    """7a. Regression: socle endpoints still intact with token."""
    section = "7. REGRESSION"
    test_name = "7a. Socle endpoints (mapping, readiness, capabilities)"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        
        # GET /api/energy/mapping
        resp = requests.get(
            f"{BASE_URL}/api/energy/mapping",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Mapping returned {resp.status_code}")
            return
        
        data = resp.json()
        # Mapping endpoint returns {"tenant_id": "...", "mapping": [...]}
        mapping = data.get("mapping", []) if isinstance(data, dict) else data
        if len(mapping) != 12:
            log_test(section, test_name, False, f"Mapping has {len(mapping)} entries, expected 12")
            return
        
        # GET /api/energy/readiness
        resp = requests.get(
            f"{BASE_URL}/api/energy/readiness",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Readiness returned {resp.status_code}")
            return
        
        readiness = resp.json()
        if readiness.get("recommendation") != "NOT_READY_FOR_A_E":
            log_test(section, test_name, False, f"Readiness recommendation={readiness.get('recommendation')}, expected NOT_READY_FOR_A_E")
            return
        
        # GET /api/energy/trackers/3218549/capabilities (EV tracker)
        resp = requests.get(
            f"{BASE_URL}/api/energy/trackers/3218549/capabilities",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Capabilities returned {resp.status_code}")
            return
        
        capabilities = resp.json()
        caps_list = capabilities.get("capabilities", [])
        
        # Check all EV metrics are UNAVAILABLE
        ev_metric_keys = ["soc", "battery_capacity", "range_est", "charge_power", "energy_used", "consumption_kwh_100"]
        for cap in caps_list:
            if cap.get("metric_key") in ev_metric_keys:
                if cap.get("availability") != "UNAVAILABLE":
                    log_test(section, test_name, False, f"EV metric {cap.get('metric_key')}.availability={cap.get('availability')}, expected UNAVAILABLE")
                    return
        
        log_test(section, test_name, True, "Socle endpoints intact: mapping 12 entries, readiness NOT_READY_FOR_A_E, EV metrics UNAVAILABLE")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def ensure_data_exists():
    """Ensure data exists by calling POST /api/energy/sync."""
    print("\n=== ENSURING DATA EXISTS ===")
    print("Calling POST /api/energy/sync (may take ~60s)...")
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        start_time = time.time()
        resp = requests.post(
            f"{BASE_URL}/api/energy/sync",
            json={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=120
        )
        elapsed = time.time() - start_time
        
        if resp.status_code != 200:
            print(f"❌ Sync failed with status {resp.status_code}: {resp.text}")
            return False
        
        data = resp.json()
        print(f"✅ Sync completed in {elapsed:.1f}s")
        print(f"   Tenant: {data.get('tenant_id')}")
        print(f"   Trackers: {data.get('trackers_synced')}")
        print(f"   Vehicles: {data.get('vehicles_synced')}")
        print(f"   Anomalies: {data.get('anomalies_detected')}")
        print("============================\n")
        return True
    
    except Exception as e:
        print(f"❌ Sync exception: {str(e)}")
        return False


def print_summary():
    """Print test summary."""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Total tests: {test_results['passed'] + test_results['failed']}")
    print(f"✅ Passed: {test_results['passed']}")
    print(f"❌ Failed: {test_results['failed']}")
    print(f"Success rate: {test_results['passed'] / (test_results['passed'] + test_results['failed']) * 100:.1f}%")
    print("="*80)
    
    if test_results['failed'] > 0:
        print("\nFAILED TESTS:")
        for detail in test_results['details']:
            if not detail['passed']:
                print(f"  ❌ {detail['section']} | {detail['test']}")
                if detail['details']:
                    print(f"     {detail['details']}")
        print("="*80)


def main():
    """Run all tests."""
    print("="*80)
    print("LOGITRAK Energy v1 Comprehensive Test Suite")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Tenant: {TENANT_ID}")
    print(f"Valid tracker: {TRACKER_ID_VALID}")
    print(f"Invalid tracker: {TRACKER_ID_INVALID}")
    print("="*80 + "\n")
    
    # Ensure data exists first
    if not ensure_data_exists():
        print("❌ Failed to ensure data exists. Aborting tests.")
        sys.exit(1)
    
    # Run all tests
    print("=== RUNNING TESTS ===\n")
    
    # 1. CONTRACT ROUTES
    test_1a_health_public()
    test_1b_vehicle_summary_valid()
    test_1c_vehicle_summary_invalid()
    test_1d_fleet_summary()
    test_1e_trips_batch()
    
    # 2. AUTH
    test_2a_auth_no_token()
    test_2b_auth_wrong_token()
    test_2c_health_no_secret()
    
    # 3. TENANT ISOLATION / IDOR
    test_3a_tenant_isolation_nonexistent()
    test_3b_tenant_mismatch()
    test_3c_missing_tenant()
    test_3d_batch_cross_tenant()
    test_3e_batch_header_only()
    
    # 4. LIMITS / PARTIAL
    test_4a_batch_limit()
    test_4b_batch_partial()
    
    # 5. RULES
    test_5a_null_not_zero()
    test_5b_stale_preserved()
    test_5c_no_none_or_error()
    
    # 6. REAL NAVIXY
    test_6a_real_navixy_all_trackers()
    
    # 7. REGRESSION
    test_7a_regression_socle()
    
    # Print summary
    print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if test_results['failed'] == 0 else 1)


if __name__ == "__main__":
    main()
