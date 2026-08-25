"""
Comprehensive Backend-to-Backend Bearer Authentication Test Suite
for LOGITRAK Energy API (Phase 2 + Auth Layer)

Tests:
A) Public health endpoint (no auth required, no secret exposure)
B) Bearer auth enforcement on /api/energy/mapping
C) All data routes require auth (401 without token, 200 with token)
D) Regression testing (data correctness with valid token)
E) Tenant isolation (with valid token)
F) Secret hygiene (no token leakage in responses)

Base URL: External REACT_APP_BACKEND_URL from /app/frontend/.env
All routes under /api
"""

import os
import requests
import json
from pathlib import Path

# Read configuration
frontend_env_path = Path("/app/frontend/.env")
backend_env_path = Path("/app/backend/.env")

# Parse .env files
def parse_env_file(path):
    env_vars = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key] = value.strip('"').strip("'")
    return env_vars

frontend_env = parse_env_file(frontend_env_path)
backend_env = parse_env_file(backend_env_path)

BASE_URL = frontend_env["REACT_APP_BACKEND_URL"]
VALID_TOKEN = backend_env["ENERGY_API_TOKEN"]

print(f"🔧 Base URL: {BASE_URL}")
print(f"🔐 Valid token loaded (length: {len(VALID_TOKEN)} chars)")
print(f"=" * 80)

# Test counters
total_tests = 0
passed_tests = 0
failed_tests = 0

def test_result(name, passed, details=""):
    global total_tests, passed_tests, failed_tests
    total_tests += 1
    if passed:
        passed_tests += 1
        print(f"✅ PASS: {name}")
    else:
        failed_tests += 1
        print(f"❌ FAIL: {name}")
    if details:
        print(f"   {details}")
    print()

# ============================================================================
# A) PUBLIC HEALTH ENDPOINT
# ============================================================================
print("\n" + "=" * 80)
print("A) PUBLIC HEALTH ENDPOINT (no auth required, no secret exposure)")
print("=" * 80 + "\n")

# Test A1: Health endpoint accessible without Authorization header
print("Test A1: GET /api/energy/health (no Authorization header)")
try:
    response = requests.get(f"{BASE_URL}/api/energy/health", timeout=10)
    data = response.json()
    
    # Check status code
    if response.status_code != 200:
        test_result("A1: Health endpoint returns 200", False, 
                   f"Expected 200, got {response.status_code}")
    else:
        # Check required fields
        required_fields = ["status", "contract_version", "navixy_configured", "auth_required", "stale_hours"]
        missing_fields = [f for f in required_fields if f not in data]
        
        if missing_fields:
            test_result("A1: Health endpoint has all required fields", False,
                       f"Missing fields: {missing_fields}")
        else:
            # Check status value
            if data["status"] != "ok":
                test_result("A1: Health status='ok'", False, f"Got status='{data['status']}'")
            else:
                test_result("A1: Health endpoint returns 200 with correct structure", True,
                           f"status={data['status']}, auth_required={data['auth_required']}, stale_hours={data['stale_hours']}")
        
        # Check that response does NOT contain the token or any secret field
        response_text = json.dumps(data).lower()
        secret_fields = ["token", "secret", "credential", "password", "key"]
        found_secrets = [f for f in secret_fields if f in response_text]
        
        # Also check if the actual token value is in the response
        token_leaked = VALID_TOKEN in json.dumps(data)
        
        if found_secrets or token_leaked:
            test_result("A1: Health endpoint does NOT expose secrets", False,
                       f"Found secret fields: {found_secrets}, Token leaked: {token_leaked}")
        else:
            test_result("A1: Health endpoint does NOT expose secrets", True,
                       "No secret fields or token value found in response")

except Exception as e:
    test_result("A1: Health endpoint accessible", False, f"Exception: {str(e)}")

# ============================================================================
# B) BEARER AUTH ENFORCEMENT ON /api/energy/mapping
# ============================================================================
print("\n" + "=" * 80)
print("B) BEARER AUTH ENFORCEMENT on /api/energy/mapping")
print("=" * 80 + "\n")

# Test B2: No Authorization header -> 401
print("Test B2: GET /api/energy/mapping (no Authorization header)")
try:
    response = requests.get(f"{BASE_URL}/api/energy/mapping", timeout=10)
    if response.status_code == 401:
        test_result("B2: No Authorization header returns 401", True,
                   f"Status: {response.status_code}")
    else:
        test_result("B2: No Authorization header returns 401", False,
                   f"Expected 401, got {response.status_code}")
except Exception as e:
    test_result("B2: No Authorization header returns 401", False, f"Exception: {str(e)}")

# Test B3: Wrong token -> 401
print("Test B3: GET /api/energy/mapping (Authorization: Bearer wrongtoken)")
try:
    headers = {"Authorization": "Bearer wrongtoken"}
    response = requests.get(f"{BASE_URL}/api/energy/mapping", headers=headers, timeout=10)
    if response.status_code == 401:
        test_result("B3: Wrong token returns 401", True,
                   f"Status: {response.status_code}")
    else:
        test_result("B3: Wrong token returns 401", False,
                   f"Expected 401, got {response.status_code}")
except Exception as e:
    test_result("B3: Wrong token returns 401", False, f"Exception: {str(e)}")

# Test B4: Wrong scheme (Basic instead of Bearer) -> 401
print("Test B4: GET /api/energy/mapping (Authorization: Basic something)")
try:
    headers = {"Authorization": "Basic something"}
    response = requests.get(f"{BASE_URL}/api/energy/mapping", headers=headers, timeout=10)
    if response.status_code == 401:
        test_result("B4: Wrong scheme (Basic) returns 401", True,
                   f"Status: {response.status_code}")
    else:
        test_result("B4: Wrong scheme (Basic) returns 401", False,
                   f"Expected 401, got {response.status_code}")
except Exception as e:
    test_result("B4: Wrong scheme returns 401", False, f"Exception: {str(e)}")

# Test B5: Valid token -> 200 with correct data
print("Test B5: GET /api/energy/mapping (Authorization: Bearer <valid token>)")
try:
    headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
    response = requests.get(f"{BASE_URL}/api/energy/mapping", headers=headers, timeout=10)
    
    if response.status_code != 200:
        test_result("B5: Valid token returns 200", False,
                   f"Expected 200, got {response.status_code}")
    else:
        data = response.json()
        
        # Check structure
        if "tenant_id" not in data or "mapping" not in data:
            test_result("B5: Valid token returns correct structure", False,
                       f"Missing tenant_id or mapping in response")
        else:
            mapping = data["mapping"]
            if len(mapping) != 12:
                test_result("B5: Valid token returns 12 mapping entries", False,
                           f"Expected 12 entries, got {len(mapping)}")
            else:
                test_result("B5: Valid token returns 200 with correct data", True,
                           f"tenant_id={data['tenant_id']}, mapping entries={len(mapping)}")
except Exception as e:
    test_result("B5: Valid token returns 200", False, f"Exception: {str(e)}")

# ============================================================================
# C) ALL DATA ROUTES REQUIRE AUTH
# ============================================================================
print("\n" + "=" * 80)
print("C) ALL DATA ROUTES REQUIRE AUTH (401 without token, 200 with token)")
print("=" * 80 + "\n")

# Define all data routes to test
data_routes = [
    ("GET", "/api/energy/anomalies"),
    ("GET", "/api/energy/readiness"),
    ("GET", "/api/energy/mapping-proposals"),
    ("GET", "/api/energy/ev-feasibility"),
    ("GET", "/api/energy/mapping-changes"),
    ("GET", "/api/energy/sync-runs"),
    ("GET", "/api/energy/trackers/781479/metrics"),
    ("GET", "/api/energy/trackers/781479/capabilities"),
    ("POST", "/api/energy/sync"),
]

for method, route in data_routes:
    route_name = route.split("/")[-1] if "/" in route else route
    
    # Test without token -> 401
    print(f"Test C: {method} {route} (no token)")
    try:
        if method == "GET":
            response = requests.get(f"{BASE_URL}{route}", timeout=10)
        else:  # POST
            response = requests.post(f"{BASE_URL}{route}", timeout=10)
        
        if response.status_code == 401:
            test_result(f"C: {method} {route} without token returns 401", True,
                       f"Status: {response.status_code}")
        else:
            test_result(f"C: {method} {route} without token returns 401", False,
                       f"Expected 401, got {response.status_code}")
    except Exception as e:
        test_result(f"C: {method} {route} without token", False, f"Exception: {str(e)}")
    
    # Test with valid token -> 200
    print(f"Test C: {method} {route} (with valid token)")
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        if method == "GET":
            response = requests.get(f"{BASE_URL}{route}", headers=headers, timeout=10)
        else:  # POST
            response = requests.post(f"{BASE_URL}{route}", headers=headers, timeout=30)
        
        if response.status_code == 200:
            test_result(f"C: {method} {route} with valid token returns 200", True,
                       f"Status: {response.status_code}")
        else:
            test_result(f"C: {method} {route} with valid token returns 200", False,
                       f"Expected 200, got {response.status_code}, Response: {response.text[:200]}")
    except Exception as e:
        test_result(f"C: {method} {route} with valid token", False, f"Exception: {str(e)}")

# ============================================================================
# D) REGRESSION TESTING (data correctness with auth)
# ============================================================================
print("\n" + "=" * 80)
print("D) REGRESSION TESTING (data must be unchanged/correct with auth)")
print("=" * 80 + "\n")

headers = {"Authorization": f"Bearer {VALID_TOKEN}"}

# Test D6: GET /api/energy/mapping -> 12 entries, tracker 781479 details
print("Test D6: GET /api/energy/mapping (regression)")
try:
    response = requests.get(f"{BASE_URL}/api/energy/mapping", headers=headers, timeout=10)
    data = response.json()
    mapping = data.get("mapping", [])
    
    if len(mapping) != 12:
        test_result("D6: Mapping has 12 entries", False, f"Expected 12, got {len(mapping)}")
    else:
        # Find tracker 781479
        tracker_781479 = next((t for t in mapping if t.get("tracker_id") == 781479), None)
        
        if not tracker_781479:
            test_result("D6: Tracker 781479 exists in mapping", False, "Tracker 781479 not found")
        else:
            confidence = tracker_781479.get("confidence")
            obd_vin = tracker_781479.get("obd_vin")
            
            if confidence != "HIGH":
                test_result("D6: Tracker 781479 confidence=HIGH", False, f"Got confidence={confidence}")
            elif obd_vin != "WAUZZZ8V0JA152970":
                test_result("D6: Tracker 781479 obd_vin correct", False, f"Got obd_vin={obd_vin}")
            else:
                test_result("D6: Mapping regression passed", True,
                           f"12 entries, tracker 781479: confidence=HIGH, obd_vin=WAUZZZ8V0JA152970")
except Exception as e:
    test_result("D6: Mapping regression", False, f"Exception: {str(e)}")

# Test D7: GET /api/energy/trackers/781479/metrics -> fuel_level details
print("Test D7: GET /api/energy/trackers/781479/metrics (regression)")
try:
    response = requests.get(f"{BASE_URL}/api/energy/trackers/781479/metrics", headers=headers, timeout=10)
    data = response.json()
    metrics_list = data.get("metrics", [])
    
    # Convert list to dict for easier lookup
    metrics = {m["key"]: m for m in metrics_list}
    
    fuel_level = metrics.get("fuel_level", {})
    board_voltage = metrics.get("board_voltage", {})
    
    # Check fuel_level
    fl_measurement = fuel_level.get("measurement_type")
    fl_source = fuel_level.get("source")
    fl_availability = fuel_level.get("availability")
    fl_value = fuel_level.get("value")
    
    if fl_measurement != "MEASURED":
        test_result("D7: fuel_level measurement_type=MEASURED", False, f"Got {fl_measurement}")
    elif fl_source != "NAVIXY_OBD":
        test_result("D7: fuel_level source=NAVIXY_OBD", False, f"Got {fl_source}")
    elif fl_availability != "STALE":
        test_result("D7: fuel_level availability=STALE", False, f"Got {fl_availability}")
    elif fl_value != 30.66:
        test_result("D7: fuel_level value=30.66", False, f"Got {fl_value}")
    else:
        test_result("D7: fuel_level regression passed", True,
                   f"MEASURED/NAVIXY_OBD, availability=STALE, value=30.66")
    
    # Check board_voltage (should be UNAVAILABLE with null value, NOT 0)
    bv_availability = board_voltage.get("availability")
    bv_value = board_voltage.get("value")
    
    if bv_availability != "UNAVAILABLE":
        test_result("D7: board_voltage availability=UNAVAILABLE", False, f"Got {bv_availability}")
    elif bv_value is not None:
        test_result("D7: board_voltage value=null (not 0)", False, f"Got value={bv_value}")
    else:
        test_result("D7: board_voltage regression passed", True,
                   "availability=UNAVAILABLE, value=null (never 0)")
except Exception as e:
    test_result("D7: Tracker 781479 metrics regression", False, f"Exception: {str(e)}")

# Test D8: GET /api/energy/trackers/3218549/capabilities -> all EV metrics UNAVAILABLE
print("Test D8: GET /api/energy/trackers/3218549/capabilities (EV regression)")
try:
    response = requests.get(f"{BASE_URL}/api/energy/trackers/3218549/capabilities", headers=headers, timeout=10)
    data = response.json()
    capabilities_list = data.get("capabilities", [])
    
    # Convert list to dict for easier lookup
    capabilities = {c["metric_key"]: c for c in capabilities_list}
    
    ev_metrics = ["soc", "battery_capacity", "range_est", "charge_power", "energy_used", "consumption_kwh_100"]
    all_unavailable = True
    
    for metric in ev_metrics:
        metric_data = capabilities.get(metric, {})
        availability = metric_data.get("availability")
        if availability != "UNAVAILABLE":
            all_unavailable = False
            test_result(f"D8: EV metric {metric} is UNAVAILABLE", False, f"Got {availability}")
            break
    
    if all_unavailable:
        test_result("D8: All EV metrics UNAVAILABLE regression passed", True,
                   "All 6 EV metrics correctly marked as UNAVAILABLE")
except Exception as e:
    test_result("D8: EV capabilities regression", False, f"Exception: {str(e)}")

# Test D9: GET /api/energy/readiness -> recommendation NOT_READY_FOR_A_E
print("Test D9: GET /api/energy/readiness (regression)")
try:
    response = requests.get(f"{BASE_URL}/api/energy/readiness", headers=headers, timeout=10)
    data = response.json()
    
    recommendation = data.get("recommendation")
    kpis = data.get("kpis", {})
    ev_energy_coverage = kpis.get("ev_energy_coverage")
    
    if recommendation != "NOT_READY_FOR_A_E":
        test_result("D9: Readiness recommendation=NOT_READY_FOR_A_E", False, f"Got {recommendation}")
    elif ev_energy_coverage != 0.0:
        test_result("D9: Readiness ev_energy_coverage=0.0", False, f"Got {ev_energy_coverage}")
    else:
        test_result("D9: Readiness regression passed", True,
                   f"recommendation=NOT_READY_FOR_A_E, ev_energy_coverage=0.0")
except Exception as e:
    test_result("D9: Readiness regression", False, f"Exception: {str(e)}")

# ============================================================================
# E) TENANT ISOLATION (with valid token)
# ============================================================================
print("\n" + "=" * 80)
print("E) TENANT ISOLATION (with valid token)")
print("=" * 80 + "\n")

# Test E10: GET /api/energy/mapping?tenant_id=paas_DOESNOTEXIST -> empty mapping
print("Test E10: GET /api/energy/mapping?tenant_id=paas_DOESNOTEXIST")
try:
    response = requests.get(f"{BASE_URL}/api/energy/mapping?tenant_id=paas_DOESNOTEXIST", 
                           headers=headers, timeout=10)
    
    if response.status_code != 200:
        test_result("E10: Non-existent tenant returns 200", False, f"Got {response.status_code}")
    else:
        data = response.json()
        mapping = data.get("mapping", [])
        
        if len(mapping) != 0:
            test_result("E10: Non-existent tenant returns empty mapping", False,
                       f"Expected empty, got {len(mapping)} entries (data leak from paas_13588)")
        else:
            test_result("E10: Tenant isolation - empty mapping for non-existent tenant", True,
                       "No data leak from paas_13588")
except Exception as e:
    test_result("E10: Tenant isolation - mapping", False, f"Exception: {str(e)}")

# Test E11: GET /api/energy/trackers/781479/metrics?tenant_id=paas_DOESNOTEXIST -> 404
print("Test E11: GET /api/energy/trackers/781479/metrics?tenant_id=paas_DOESNOTEXIST")
try:
    response = requests.get(f"{BASE_URL}/api/energy/trackers/781479/metrics?tenant_id=paas_DOESNOTEXIST",
                           headers=headers, timeout=10)
    
    if response.status_code == 404:
        test_result("E11: Tenant isolation - tracker not found under wrong tenant", True,
                   "404 returned, no cross-tenant leak")
    else:
        test_result("E11: Tenant isolation - tracker returns 404", False,
                   f"Expected 404, got {response.status_code} (potential cross-tenant leak)")
except Exception as e:
    test_result("E11: Tenant isolation - tracker metrics", False, f"Exception: {str(e)}")

# Test E12: GET /api/energy/trackers/99999999/metrics -> 404
print("Test E12: GET /api/energy/trackers/99999999/metrics (invalid tracker)")
try:
    response = requests.get(f"{BASE_URL}/api/energy/trackers/99999999/metrics",
                           headers=headers, timeout=10)
    
    if response.status_code == 404:
        test_result("E12: Invalid tracker ID returns 404", True,
                   "Tracker not found as expected")
    else:
        test_result("E12: Invalid tracker ID returns 404", False,
                   f"Expected 404, got {response.status_code}")
except Exception as e:
    test_result("E12: Invalid tracker ID", False, f"Exception: {str(e)}")

# ============================================================================
# F) SECRET HYGIENE
# ============================================================================
print("\n" + "=" * 80)
print("F) SECRET HYGIENE (no token leakage in any response)")
print("=" * 80 + "\n")

# Test F13: Check health endpoint doesn't return token
print("Test F13: Health endpoint does not expose token")
try:
    response = requests.get(f"{BASE_URL}/api/energy/health", timeout=10)
    response_text = response.text
    
    if VALID_TOKEN in response_text:
        test_result("F13: Health endpoint does not expose token", False,
                   "Token value found in health response")
    else:
        test_result("F13: Health endpoint does not expose token", True,
                   "Token not found in response")
except Exception as e:
    test_result("F13: Health endpoint secret hygiene", False, f"Exception: {str(e)}")

# Test F13b: Check 401 error responses don't expose token
print("Test F13b: 401 error responses do not expose token")
try:
    response = requests.get(f"{BASE_URL}/api/energy/mapping", timeout=10)
    response_text = response.text
    
    if VALID_TOKEN in response_text:
        test_result("F13b: 401 response does not expose token", False,
                   "Token value found in 401 error response")
    else:
        test_result("F13b: 401 response does not expose token", True,
                   "Token not found in 401 response")
except Exception as e:
    test_result("F13b: 401 response secret hygiene", False, f"Exception: {str(e)}")

# Test F13c: Check authenticated responses don't expose token
print("Test F13c: Authenticated responses do not expose token")
try:
    response = requests.get(f"{BASE_URL}/api/energy/mapping", headers=headers, timeout=10)
    response_text = response.text
    
    if VALID_TOKEN in response_text:
        test_result("F13c: Authenticated response does not expose token", False,
                   "Token value found in authenticated response")
    else:
        test_result("F13c: Authenticated response does not expose token", True,
                   "Token not found in response")
except Exception as e:
    test_result("F13c: Authenticated response secret hygiene", False, f"Exception: {str(e)}")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)
print(f"Total tests: {total_tests}")
print(f"✅ Passed: {passed_tests}")
print(f"❌ Failed: {failed_tests}")
print(f"Success rate: {(passed_tests/total_tests*100):.1f}%")
print("=" * 80)

if failed_tests == 0:
    print("\n🎉 ALL TESTS PASSED! Backend-to-backend Bearer authentication is working correctly.")
    print("✅ Public health endpoint accessible without auth")
    print("✅ All data routes require valid Bearer token")
    print("✅ Regression tests passed (data unchanged)")
    print("✅ Tenant isolation working correctly")
    print("✅ No secret leakage detected")
else:
    print(f"\n⚠️  {failed_tests} test(s) failed. Please review the failures above.")

exit(0 if failed_tests == 0 else 1)
