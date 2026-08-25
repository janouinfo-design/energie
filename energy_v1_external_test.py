#!/usr/bin/env python3
"""
Energy v1 API External HTTP Testing
Tests the REAL EXTERNAL Energy v1 API over HTTPS (not localhost).
Verifies contract compliance, authentication, tenant isolation, and data structure.
"""
import os
import sys
import json
import requests
from typing import Dict, Any, List

# Configuration - EXTERNAL URL ONLY
BASE_URL = "https://energy-telemetry-1.preview.emergentagent.com"
TENANT_ID = "paas_13588"
TRACKER_ID_VALID = 781479
TRACKER_ID_INVALID = 999999

# Read token from environment (NEVER print it)
TOKEN = None
try:
    with open("/app/backend/.env", "r") as f:
        for line in f:
            if line.startswith("ENERGY_API_TOKEN="):
                TOKEN = line.split("=", 1)[1].strip().strip('"')
                break
except Exception as e:
    print(f"❌ Failed to read ENERGY_API_TOKEN from /app/backend/.env: {e}")
    sys.exit(1)

if not TOKEN:
    print("❌ ENERGY_API_TOKEN not found in /app/backend/.env")
    sys.exit(1)

# Test results tracking
results = {"passed": 0, "failed": 0, "tests": []}

def log_test(name: str, passed: bool, details: str = ""):
    """Log test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    msg = f"{status} | {name}"
    if details:
        msg += f"\n     {details}"
    print(msg)
    results["tests"].append({"name": name, "passed": passed, "details": details})
    if passed:
        results["passed"] += 1
    else:
        results["failed"] += 1

def verify_no_secret_leak(data: Any, test_name: str) -> bool:
    """Verify token is not exposed in response."""
    data_str = json.dumps(data) if isinstance(data, dict) else str(data)
    if TOKEN in data_str:
        log_test(test_name, False, f"SECURITY VIOLATION: Token exposed in response")
        return False
    return True

print("="*80)
print("Energy v1 API - EXTERNAL HTTP Testing")
print("="*80)
print(f"Base URL: {BASE_URL}")
print(f"Tenant: {TENANT_ID}")
print(f"Token: [REDACTED - loaded from .env]")
print("="*80 + "\n")

# ============================================================================
# 1. HEALTH CHECK (NO TOKEN)
# ============================================================================
print("1. HEALTH CHECK (NO TOKEN)")
print("-" * 80)

try:
    resp = requests.get(f"{BASE_URL}/api/energy/v1/health", timeout=10)
    
    # Check HTTP status
    if resp.status_code != 200:
        log_test("1. Health - HTTP 200", False, f"Got {resp.status_code}")
    else:
        log_test("1. Health - HTTP 200", True, f"Status: {resp.status_code}")
    
    # Check content-type
    content_type = resp.headers.get("content-type", "")
    if "application/json" not in content_type:
        log_test("1. Health - Content-Type", False, f"Got '{content_type}', expected 'application/json'")
    else:
        log_test("1. Health - Content-Type", True, f"Content-Type: {content_type}")
    
    # Check JSON body
    data = resp.json()
    
    # Check status=ok
    if data.get("status") != "ok":
        log_test("1. Health - status=ok", False, f"Got status='{data.get('status')}'")
    else:
        log_test("1. Health - status=ok", True)
    
    # Check contract_version=v1
    if data.get("contract_version") != "v1":
        log_test("1. Health - contract_version=v1", False, f"Got contract_version='{data.get('contract_version')}'")
    else:
        log_test("1. Health - contract_version=v1", True)
    
    # Check no secret in body
    if not verify_no_secret_leak(data, "1. Health - No secret in body"):
        pass
    else:
        log_test("1. Health - No secret in body", True)

except Exception as e:
    log_test("1. Health - Exception", False, str(e))

print()

# ============================================================================
# 2. ROUTE PRESENCE (NO TOKEN -> 401, NOT 404)
# ============================================================================
print("2. ROUTE PRESENCE (NO TOKEN -> 401, NOT 404)")
print("-" * 80)

routes_to_test = [
    ("GET", f"{BASE_URL}/api/energy/v1/fleet/summary?tenant_id={TENANT_ID}", None),
    ("GET", f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary?tenant_id={TENANT_ID}", None),
    ("POST", f"{BASE_URL}/api/energy/v1/trips/energy:batch", {"tenant_id": TENANT_ID, "trips": []}),
]

for method, url, body in routes_to_test:
    try:
        if method == "GET":
            resp = requests.get(url, timeout=10)
        else:
            resp = requests.post(url, json=body, timeout=10)
        
        route_name = url.split("/api/energy/v1/")[1].split("?")[0]
        if resp.status_code == 401:
            log_test(f"2. Route presence - {method} {route_name} -> 401", True, f"Route mounted and secured")
        elif resp.status_code == 404:
            log_test(f"2. Route presence - {method} {route_name} -> 401", False, f"Got 404 (route not mounted)")
        else:
            log_test(f"2. Route presence - {method} {route_name} -> 401", False, f"Got {resp.status_code}")
    except Exception as e:
        log_test(f"2. Route presence - {method} {route_name}", False, str(e))

print()

# ============================================================================
# 3. SYNC DATA (ensure data exists)
# ============================================================================
print("3. SYNC DATA (ensure data exists)")
print("-" * 80)

try:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    print("Calling POST /api/energy/sync (may take ~60s)...")
    resp = requests.post(
        f"{BASE_URL}/api/energy/sync",
        json={"tenant_id": TENANT_ID},
        headers=headers,
        timeout=120
    )
    
    if resp.status_code != 200:
        log_test("3. Sync - HTTP 200", False, f"Got {resp.status_code}: {resp.text}")
    else:
        data = resp.json()
        log_test("3. Sync - HTTP 200", True, f"Synced {data.get('trackers_synced')} trackers, {data.get('vehicles_synced')} vehicles")
except Exception as e:
    log_test("3. Sync - Exception", False, str(e))

print()

# ============================================================================
# 4. BATCH ENDPOINT (VALID TOKEN)
# ============================================================================
print("4. BATCH ENDPOINT (VALID TOKEN)")
print("-" * 80)

try:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    payload = {
        "tenant_id": TENANT_ID,
        "trips": [
            {
                "trip_id": "REAL1",
                "ref": TRACKER_ID_VALID,
                "start": "2026-08-18T08:00:00Z",
                "end": "2026-08-18T08:40:00Z"
            },
            {
                "trip_id": "REAL2",
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
    
    # Check HTTP 200
    if resp.status_code != 200:
        log_test("4. Batch - HTTP 200", False, f"Got {resp.status_code}: {resp.text}")
    else:
        log_test("4. Batch - HTTP 200", True)
        
        data = resp.json()
        
        # Check top-level contract_version
        if data.get("contract_version") != "1.0":
            log_test("4. Batch - contract_version=1.0", False, f"Got '{data.get('contract_version')}'")
        else:
            log_test("4. Batch - contract_version=1.0", True)
        
        # Check results is a list of 2
        results_list = data.get("results", [])
        if len(results_list) != 2:
            log_test("4. Batch - results list of 2", False, f"Got {len(results_list)} results")
        else:
            log_test("4. Batch - results list of 2", True)
            
            # Check EACH result structure
            for i, result in enumerate(results_list):
                trip_id = result.get("trip_id")
                
                # CRITICAL: Check NO 'energy' wrapper
                if "energy" in result:
                    log_test(f"4. Batch - REAL{i+1} NO 'energy' wrapper", False, f"Found 'energy' key in result")
                else:
                    log_test(f"4. Batch - REAL{i+1} NO 'energy' wrapper", True, "fuel and electric are DIRECT children")
                
                # Check required keys at same level
                required_keys = ["trip_id", "availability", "reason", "powertrain", "fuel", "electric", "contract_version"]
                missing_keys = [k for k in required_keys if k not in result]
                if missing_keys:
                    log_test(f"4. Batch - REAL{i+1} required keys", False, f"Missing keys: {missing_keys}")
                else:
                    log_test(f"4. Batch - REAL{i+1} required keys", True, f"All keys present at same level")
                
                # Check fuel object has EXACTLY {fuel_liters, consumption_l_100km}
                fuel = result.get("fuel", {})
                fuel_keys = set(fuel.keys())
                expected_fuel_keys = {"fuel_liters", "consumption_l_100km"}
                if fuel_keys != expected_fuel_keys:
                    log_test(f"4. Batch - REAL{i+1} fuel keys", False, f"Got {fuel_keys}, expected {expected_fuel_keys}")
                else:
                    log_test(f"4. Batch - REAL{i+1} fuel keys EXACTLY {{fuel_liters, consumption_l_100km}}", True)
                
                # Check electric object has EXACTLY {soc_start_pct, soc_end_pct, energy_kwh, consumption_kwh_100km}
                electric = result.get("electric", {})
                electric_keys = set(electric.keys())
                expected_electric_keys = {"soc_start_pct", "soc_end_pct", "energy_kwh", "consumption_kwh_100km"}
                if electric_keys != expected_electric_keys:
                    log_test(f"4. Batch - REAL{i+1} electric keys", False, f"Got {electric_keys}, expected {expected_electric_keys}")
                else:
                    log_test(f"4. Batch - REAL{i+1} electric keys EXACTLY {{soc_start_pct, soc_end_pct, energy_kwh, consumption_kwh_100km}}", True)
                
                # Check all 6 metrics are UNAVAILABLE with value=null
                all_metrics = {**fuel, **electric}
                for metric_name, metric_envelope in all_metrics.items():
                    # Check availability=UNAVAILABLE
                    if metric_envelope.get("availability") != "UNAVAILABLE":
                        log_test(f"4. Batch - REAL{i+1} {metric_name} UNAVAILABLE", False, f"Got availability='{metric_envelope.get('availability')}'")
                    
                    # Check value=null (NEVER 0)
                    if metric_envelope.get("value") is not None:
                        log_test(f"4. Batch - REAL{i+1} {metric_name} value=null", False, f"Got value={metric_envelope.get('value')} (expected null, NEVER 0)")
                    
                    # Check measurement_type is null (NEVER "NONE")
                    if metric_envelope.get("measurement_type") == "NONE":
                        log_test(f"4. Batch - REAL{i+1} {metric_name} measurement_type", False, f"Got 'NONE' (must NEVER appear)")
                    
                    # Check availability is NEVER "ERROR"
                    if metric_envelope.get("availability") == "ERROR":
                        log_test(f"4. Batch - REAL{i+1} {metric_name} availability", False, f"Got 'ERROR' (must NEVER appear)")
                
                # Summary check for all 6 metrics
                all_unavailable = all(m.get("availability") == "UNAVAILABLE" for m in all_metrics.values())
                all_null = all(m.get("value") is None for m in all_metrics.values())
                no_none = all(m.get("measurement_type") != "NONE" for m in all_metrics.values())
                no_error = all(m.get("availability") != "ERROR" for m in all_metrics.values())
                
                if all_unavailable and all_null and no_none and no_error:
                    log_test(f"4. Batch - REAL{i+1} all 6 metrics UNAVAILABLE/null/no NONE/no ERROR", True)
                
                # Check tracker_id
                if i == 0:  # REAL1
                    if result.get("tracker_id") != TRACKER_ID_VALID:
                        log_test(f"4. Batch - REAL1 tracker_id={TRACKER_ID_VALID}", False, f"Got {result.get('tracker_id')}")
                    else:
                        log_test(f"4. Batch - REAL1 tracker_id={TRACKER_ID_VALID}", True)
                else:  # REAL2
                    if result.get("tracker_id") is not None:
                        log_test(f"4. Batch - REAL2 tracker_id=null", False, f"Got {result.get('tracker_id')} (mapping invalid)")
                    else:
                        log_test(f"4. Batch - REAL2 tracker_id=null (mapping invalid)", True)
                
                # Check powertrain
                powertrain = result.get("powertrain")
                valid_powertrains = ["ICE", "HEV", "PHEV", "BEV", "UNKNOWN"]
                if powertrain not in valid_powertrains:
                    log_test(f"4. Batch - REAL{i+1} powertrain valid", False, f"Got '{powertrain}', expected one of {valid_powertrains}")
                else:
                    log_test(f"4. Batch - REAL{i+1} powertrain={powertrain}", True, f"Observed: {powertrain} (expected UNKNOWN)")

except Exception as e:
    log_test("4. Batch - Exception", False, str(e))

print()

# ============================================================================
# 5. FLEET SUMMARY (VALID TOKEN)
# ============================================================================
print("5. FLEET SUMMARY (VALID TOKEN)")
print("-" * 80)

try:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    resp = requests.get(
        f"{BASE_URL}/api/energy/v1/fleet/summary",
        params={"tenant_id": TENANT_ID},
        headers=headers,
        timeout=10
    )
    
    # Check HTTP 200
    if resp.status_code != 200:
        log_test("5. Fleet - HTTP 200", False, f"Got {resp.status_code}: {resp.text}")
    else:
        log_test("5. Fleet - HTTP 200", True)
        
        data = resp.json()
        
        # Check metrics has EXACTLY 6 keys
        metrics = data.get("metrics", {})
        metrics_keys = set(metrics.keys())
        expected_keys = {
            "thermal_consumption_l_100km",
            "electric_consumption_kwh_100km",
            "fuel_liters_total",
            "electric_kwh_total",
            "obd_coverage_pct",
            "vehicles_with_data"
        }
        
        if metrics_keys != expected_keys:
            log_test("5. Fleet - metrics EXACTLY 6 keys", False, f"Got {metrics_keys}, expected {expected_keys}")
        else:
            log_test("5. Fleet - metrics EXACTLY 6 keys", True, f"Keys: {expected_keys}")
        
        # Check obd_coverage_pct is AVAILABLE and numeric
        obd_coverage = metrics.get("obd_coverage_pct", {})
        if obd_coverage.get("availability") != "AVAILABLE":
            log_test("5. Fleet - obd_coverage_pct AVAILABLE", False, f"Got availability='{obd_coverage.get('availability')}'")
        else:
            log_test("5. Fleet - obd_coverage_pct AVAILABLE", True, f"value={obd_coverage.get('value')}")
        
        if not isinstance(obd_coverage.get("value"), (int, float)):
            log_test("5. Fleet - obd_coverage_pct numeric", False, f"Got value={obd_coverage.get('value')} (not numeric)")
        else:
            log_test("5. Fleet - obd_coverage_pct numeric", True)
        
        # Check 4 energy totals are UNAVAILABLE with value=null (NEVER 0)
        energy_metrics = ["thermal_consumption_l_100km", "electric_consumption_kwh_100km", "fuel_liters_total", "electric_kwh_total"]
        for metric_name in energy_metrics:
            metric = metrics.get(metric_name, {})
            
            if metric.get("availability") != "UNAVAILABLE":
                log_test(f"5. Fleet - {metric_name} UNAVAILABLE", False, f"Got availability='{metric.get('availability')}'")
            
            if metric.get("value") is not None:
                log_test(f"5. Fleet - {metric_name} value=null", False, f"Got value={metric.get('value')} (expected null, NEVER 0)")
        
        # Summary check
        all_energy_unavailable = all(metrics.get(m, {}).get("availability") == "UNAVAILABLE" for m in energy_metrics)
        all_energy_null = all(metrics.get(m, {}).get("value") is None for m in energy_metrics)
        
        if all_energy_unavailable and all_energy_null:
            log_test("5. Fleet - 4 energy totals UNAVAILABLE/null (NEVER 0)", True)

except Exception as e:
    log_test("5. Fleet - Exception", False, str(e))

print()

# ============================================================================
# 6. VEHICLE SUMMARY (VALID TOKEN)
# ============================================================================
print("6. VEHICLE SUMMARY (VALID TOKEN)")
print("-" * 80)

try:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    resp = requests.get(
        f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary",
        params={"tenant_id": TENANT_ID},
        headers=headers,
        timeout=10
    )
    
    # Check HTTP 200
    if resp.status_code != 200:
        log_test("6. Vehicle - HTTP 200", False, f"Got {resp.status_code}: {resp.text}")
    else:
        log_test("6. Vehicle - HTTP 200", True)
        
        data = resp.json()
        
        # Check metrics has EXACTLY 2 keys
        metrics = data.get("metrics", {})
        metrics_keys = set(metrics.keys())
        expected_keys = {"fuel_liters_total", "energy_kwh_total"}
        
        if metrics_keys != expected_keys:
            log_test("6. Vehicle - metrics EXACTLY 2 keys", False, f"Got {metrics_keys}, expected {expected_keys}")
        else:
            log_test("6. Vehicle - metrics EXACTLY {{fuel_liters_total, energy_kwh_total}}", True)
        
        # Report powertrain
        powertrain = data.get("powertrain")
        log_test(f"6. Vehicle - powertrain={powertrain}", True, f"Observed: {powertrain}")
        
        # Report metric details
        fuel_total = metrics.get("fuel_liters_total", {})
        energy_total = metrics.get("energy_kwh_total", {})
        
        log_test(f"6. Vehicle - fuel_liters_total", True, 
                f"availability={fuel_total.get('availability')}, value={fuel_total.get('value')}, measurement_type={fuel_total.get('measurement_type')}")
        log_test(f"6. Vehicle - energy_kwh_total", True,
                f"availability={energy_total.get('availability')}, value={energy_total.get('value')}, measurement_type={energy_total.get('measurement_type')}")

except Exception as e:
    log_test("6. Vehicle - Exception", False, str(e))

print()

# ============================================================================
# 7. AUTH NEGATIVE (WRONG TOKEN)
# ============================================================================
print("7. AUTH NEGATIVE (WRONG TOKEN)")
print("-" * 80)

try:
    headers = {"Authorization": "Bearer wrong"}
    resp = requests.get(
        f"{BASE_URL}/api/energy/v1/fleet/summary",
        params={"tenant_id": TENANT_ID},
        headers=headers,
        timeout=10
    )
    
    if resp.status_code != 401:
        log_test("7. Auth - wrong token -> 401", False, f"Got {resp.status_code}")
    else:
        log_test("7. Auth - wrong token -> 401", True)

except Exception as e:
    log_test("7. Auth - Exception", False, str(e))

print()

# ============================================================================
# 8. TENANT ISOLATION
# ============================================================================
print("8. TENANT ISOLATION")
print("-" * 80)

# 8a. Non-existent tenant -> 404
try:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    resp = requests.get(
        f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary",
        params={"tenant_id": "paas_DOESNOTEXIST"},
        headers=headers,
        timeout=10
    )
    
    if resp.status_code != 404:
        log_test("8a. Tenant isolation - non-existent tenant -> 404", False, f"Got {resp.status_code} (no cross-tenant leak)")
    else:
        log_test("8a. Tenant isolation - non-existent tenant -> 404", True, "No cross-tenant leak")

except Exception as e:
    log_test("8a. Tenant isolation - Exception", False, str(e))

# 8b. Tenant mismatch -> 400
try:
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "X-Tenant-Id": "paas_OTHER"
    }
    resp = requests.get(
        f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary",
        params={"tenant_id": TENANT_ID},
        headers=headers,
        timeout=10
    )
    
    if resp.status_code != 400:
        log_test("8b. Tenant isolation - mismatch -> 400", False, f"Got {resp.status_code}")
    else:
        log_test("8b. Tenant isolation - mismatch -> 400", True)

except Exception as e:
    log_test("8b. Tenant isolation - Exception", False, str(e))

print()

# ============================================================================
# 9. NULL != 0 VERIFICATION
# ============================================================================
print("9. NULL != 0 VERIFICATION")
print("-" * 80)

try:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    
    # Check batch
    payload = {
        "tenant_id": TENANT_ID,
        "trips": [{"trip_id": "NULL_CHECK", "ref": TRACKER_ID_VALID, "start": "2026-08-18T08:00:00Z", "end": "2026-08-18T08:40:00Z"}]
    }
    resp = requests.post(
        f"{BASE_URL}/api/energy/v1/trips/energy:batch",
        json=payload,
        headers=headers,
        timeout=10
    )
    
    if resp.status_code == 200:
        data = resp.json()
        result = data.get("results", [{}])[0]
        fuel = result.get("fuel", {})
        electric = result.get("electric", {})
        all_metrics = {**fuel, **electric}
        
        has_zero = any(m.get("value") == 0 for m in all_metrics.values() if m.get("availability") == "UNAVAILABLE")
        if has_zero:
            log_test("9. Null != 0 - batch UNAVAILABLE metrics", False, "Found value=0 for UNAVAILABLE metric (should be null)")
        else:
            log_test("9. Null != 0 - batch UNAVAILABLE metrics", True, "All UNAVAILABLE metrics have value=null (NEVER 0)")
    
    # Check fleet
    resp = requests.get(
        f"{BASE_URL}/api/energy/v1/fleet/summary",
        params={"tenant_id": TENANT_ID},
        headers=headers,
        timeout=10
    )
    
    if resp.status_code == 200:
        data = resp.json()
        metrics = data.get("metrics", {})
        
        has_zero = any(m.get("value") == 0 for m in metrics.values() if m.get("availability") == "UNAVAILABLE")
        if has_zero:
            log_test("9. Null != 0 - fleet UNAVAILABLE metrics", False, "Found value=0 for UNAVAILABLE metric (should be null)")
        else:
            log_test("9. Null != 0 - fleet UNAVAILABLE metrics", True, "All UNAVAILABLE metrics have value=null (NEVER 0)")
    
    # Check vehicle
    resp = requests.get(
        f"{BASE_URL}/api/energy/v1/vehicles/{TRACKER_ID_VALID}/summary",
        params={"tenant_id": TENANT_ID},
        headers=headers,
        timeout=10
    )
    
    if resp.status_code == 200:
        data = resp.json()
        metrics = data.get("metrics", {})
        
        has_zero = any(m.get("value") == 0 for m in metrics.values() if m.get("availability") == "UNAVAILABLE")
        if has_zero:
            log_test("9. Null != 0 - vehicle UNAVAILABLE metrics", False, "Found value=0 for UNAVAILABLE metric (should be null)")
        else:
            log_test("9. Null != 0 - vehicle UNAVAILABLE metrics", True, "All UNAVAILABLE metrics have value=null (NEVER 0)")

except Exception as e:
    log_test("9. Null != 0 - Exception", False, str(e))

print()

# ============================================================================
# SUMMARY
# ============================================================================
print("="*80)
print("TEST SUMMARY")
print("="*80)
print(f"Total: {results['passed'] + results['failed']}")
print(f"✅ Passed: {results['passed']}")
print(f"❌ Failed: {results['failed']}")
if results['passed'] + results['failed'] > 0:
    print(f"Success rate: {results['passed'] / (results['passed'] + results['failed']) * 100:.1f}%")
print("="*80)

if results['failed'] > 0:
    print("\nFAILED TESTS:")
    for test in results['tests']:
        if not test['passed']:
            print(f"  ❌ {test['name']}")
            if test['details']:
                print(f"     {test['details']}")
    print("="*80)

sys.exit(0 if results['failed'] == 0 else 1)
