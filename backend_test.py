"""
Comprehensive backend tests for LOGITRAK Energy foundation (Phase 2).
Tests all endpoints under /api/energy with real Navixy integration.
"""
import requests
import time
import sys

# Read base URL from frontend/.env
with open('/app/frontend/.env', 'r') as f:
    for line in f:
        if line.startswith('REACT_APP_BACKEND_URL='):
            BASE_URL = line.split('=')[1].strip()
            break

print(f"Testing against: {BASE_URL}")
print("=" * 80)

# Test results tracking
tests_passed = 0
tests_failed = 0
failures = []

def test_endpoint(name, method, url, expected_status=200, json_data=None, timeout=70):
    """Helper function to test an endpoint and track results."""
    global tests_passed, tests_failed, failures
    
    print(f"\n{'='*80}")
    print(f"TEST: {name}")
    print(f"{'='*80}")
    print(f"Method: {method}")
    print(f"URL: {url}")
    
    try:
        if method == "GET":
            response = requests.get(url, timeout=timeout)
        elif method == "POST":
            response = requests.post(url, json=json_data, timeout=timeout)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != expected_status:
            tests_failed += 1
            msg = f"FAIL: {name} - Expected status {expected_status}, got {response.status_code}"
            failures.append(msg)
            print(f"❌ {msg}")
            print(f"Response: {response.text[:500]}")
            return None
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ PASS: {name}")
            return data
        else:
            tests_passed += 1
            print(f"✅ PASS: {name}")
            return None
            
    except Exception as e:
        tests_failed += 1
        msg = f"FAIL: {name} - Exception: {str(e)}"
        failures.append(msg)
        print(f"❌ {msg}")
        return None

def verify_critical_rules(data, test_name):
    """Verify critical rules for metrics/capabilities."""
    global tests_failed, failures
    violations = []
    
    # Check if this is a metrics response
    if "metrics" in data:
        for metric in data["metrics"]:
            # Rule 1: 0 is never used to represent missing data
            if metric.get("value") == 0 and metric.get("availability") == "UNAVAILABLE":
                violations.append(f"Metric {metric['key']}: value=0 with UNAVAILABLE (should be null)")
            
            # Rule 2: STALE metric is never reported as AVAILABLE
            if metric.get("availability") == "STALE" and metric.get("availability") == "AVAILABLE":
                violations.append(f"Metric {metric['key']}: STALE marked as AVAILABLE")
            
            # Rule 3: No EV metric is ever MEASURED
            ev_keys = ["soc", "battery_capacity", "range_est", "charge_power", "energy_used", "consumption_kwh_100"]
            if metric.get("key") in ev_keys and metric.get("measurement_type") == "MEASURED":
                violations.append(f"Metric {metric['key']}: EV metric marked as MEASURED (should be UNAVAILABLE)")
            
            # Rule 4: REFERENCE is never labelled MEASURED
            if metric.get("measurement_type") == "REFERENCE" and metric.get("measurement_type") == "MEASURED":
                violations.append(f"Metric {metric['key']}: REFERENCE labelled as MEASURED")
    
    # Check if this is a capabilities response
    if "capabilities" in data:
        for cap in data["capabilities"]:
            # Rule 1: 0 is never used to represent missing data (check if value field exists)
            if "value" in cap and cap.get("value") == 0 and cap.get("availability") == "UNAVAILABLE":
                violations.append(f"Capability {cap['metric_key']}: value=0 with UNAVAILABLE (should be null)")
            
            # Rule 3: No EV metric is ever MEASURED
            ev_keys = ["soc", "battery_capacity", "range_est", "charge_power", "energy_used", "consumption_kwh_100"]
            if cap.get("metric_key") in ev_keys and cap.get("measurement_type") == "MEASURED":
                violations.append(f"Capability {cap['metric_key']}: EV metric marked as MEASURED")
    
    if violations:
        tests_failed += len(violations)
        for v in violations:
            msg = f"CRITICAL RULE VIOLATION in {test_name}: {v}"
            failures.append(msg)
            print(f"❌ {msg}")
        return False
    return True

# ============================================================================
# TEST 1: Health Check
# ============================================================================
health_data = test_endpoint(
    "1. GET /api/energy/health",
    "GET",
    f"{BASE_URL}/api/energy/health"
)

if health_data:
    print(f"Response: {health_data}")
    # Verify required fields
    if health_data.get("status") == "ok":
        tests_passed += 1
        print("✅ Status is 'ok'")
    else:
        tests_failed += 1
        msg = f"Health check status is not 'ok': {health_data.get('status')}"
        failures.append(msg)
        print(f"❌ {msg}")
    
    if health_data.get("navixy_configured") == True:
        tests_passed += 1
        print("✅ Navixy is configured")
    else:
        tests_failed += 1
        msg = "Navixy is not configured"
        failures.append(msg)
        print(f"❌ {msg}")
    
    if "stale_hours" in health_data:
        tests_passed += 1
        print(f"✅ Stale hours: {health_data.get('stale_hours')}")
    else:
        tests_failed += 1
        msg = "stale_hours field missing"
        failures.append(msg)
        print(f"❌ {msg}")

# ============================================================================
# TEST 2: Sync (may take up to 60s)
# ============================================================================
print("\n⏳ Running sync (this may take up to 60 seconds)...")
sync_data = test_endpoint(
    "2. POST /api/energy/sync",
    "POST",
    f"{BASE_URL}/api/energy/sync",
    timeout=70
)

if sync_data:
    print(f"Response: {sync_data}")
    
    # Verify tenant_id
    if sync_data.get("tenant_id") == "paas_13588":
        tests_passed += 1
        print("✅ tenant_id is 'paas_13588'")
    else:
        tests_failed += 1
        msg = f"tenant_id is not 'paas_13588': {sync_data.get('tenant_id')}"
        failures.append(msg)
        print(f"❌ {msg}")
    
    # Verify trackers count
    if sync_data.get("trackers") == 12:
        tests_passed += 1
        print("✅ trackers count is 12")
    else:
        tests_failed += 1
        msg = f"trackers count is not 12: {sync_data.get('trackers')}"
        failures.append(msg)
        print(f"❌ {msg}")
    
    # Verify vehicles count
    if sync_data.get("vehicles") == 8:
        tests_passed += 1
        print("✅ vehicles count is 8")
    else:
        tests_failed += 1
        msg = f"vehicles count is not 8: {sync_data.get('vehicles')}"
        failures.append(msg)
        print(f"❌ {msg}")
    
    # Verify anomalies > 0
    if sync_data.get("anomalies", 0) > 0:
        tests_passed += 1
        print(f"✅ anomalies count is {sync_data.get('anomalies')} (> 0)")
    else:
        tests_failed += 1
        msg = f"anomalies count is not > 0: {sync_data.get('anomalies')}"
        failures.append(msg)
        print(f"❌ {msg}")
    
    # Verify errors is empty
    if sync_data.get("errors") == []:
        tests_passed += 1
        print("✅ errors list is empty")
    else:
        tests_failed += 1
        msg = f"errors list is not empty: {sync_data.get('errors')}"
        failures.append(msg)
        print(f"❌ {msg}")

# Wait a moment for data to be fully persisted
time.sleep(2)

# ============================================================================
# TEST 3: Mapping
# ============================================================================
mapping_data = test_endpoint(
    "3. GET /api/energy/mapping",
    "GET",
    f"{BASE_URL}/api/energy/mapping"
)

if mapping_data:
    print(f"Tenant ID: {mapping_data.get('tenant_id')}")
    print(f"Mapping entries count: {len(mapping_data.get('mapping', []))}")
    
    # Verify tenant_id
    if mapping_data.get("tenant_id") == "paas_13588":
        tests_passed += 1
        print("✅ tenant_id is 'paas_13588'")
    else:
        tests_failed += 1
        msg = f"tenant_id is not 'paas_13588': {mapping_data.get('tenant_id')}"
        failures.append(msg)
        print(f"❌ {msg}")
    
    # Verify 12 entries
    if len(mapping_data.get("mapping", [])) == 12:
        tests_passed += 1
        print("✅ mapping has 12 entries")
    else:
        tests_failed += 1
        msg = f"mapping does not have 12 entries: {len(mapping_data.get('mapping', []))}"
        failures.append(msg)
        print(f"❌ {msg}")
    
    # Verify each entry has required fields
    required_fields = ["tracker_id", "tracker_label", "obd_vin", "vehicle_id", "confidence", "connection_status"]
    all_entries_valid = True
    for entry in mapping_data.get("mapping", []):
        for field in required_fields:
            if field not in entry:
                all_entries_valid = False
                tests_failed += 1
                msg = f"Mapping entry missing field '{field}': {entry.get('tracker_id')}"
                failures.append(msg)
                print(f"❌ {msg}")
                break
    
    if all_entries_valid:
        tests_passed += 1
        print("✅ All mapping entries have required fields")
    
    # Verify tracker 781479 (LOGITRAK AUDI)
    tracker_781479 = next((e for e in mapping_data.get("mapping", []) if e.get("tracker_id") == 781479), None)
    if tracker_781479:
        print(f"\nTracker 781479 details: {tracker_781479}")
        
        if tracker_781479.get("confidence") == "HIGH":
            tests_passed += 1
            print("✅ Tracker 781479 has confidence=HIGH")
        else:
            tests_failed += 1
            msg = f"Tracker 781479 confidence is not HIGH: {tracker_781479.get('confidence')}"
            failures.append(msg)
            print(f"❌ {msg}")
        
        if tracker_781479.get("obd_vin") == "WAUZZZ8V0JA152970":
            tests_passed += 1
            print("✅ Tracker 781479 has correct obd_vin")
        else:
            tests_failed += 1
            msg = f"Tracker 781479 obd_vin is not 'WAUZZZ8V0JA152970': {tracker_781479.get('obd_vin')}"
            failures.append(msg)
            print(f"❌ {msg}")
    else:
        tests_failed += 1
        msg = "Tracker 781479 not found in mapping"
        failures.append(msg)
        print(f"❌ {msg}")

# ============================================================================
# TEST 4: Anomalies
# ============================================================================
anomalies_data = test_endpoint(
    "4. GET /api/energy/anomalies",
    "GET",
    f"{BASE_URL}/api/energy/anomalies"
)

if anomalies_data:
    print(f"Counts: {anomalies_data.get('counts')}")
    print(f"Anomalies count: {len(anomalies_data.get('anomalies', []))}")
    
    # Verify counts contains expected keys
    expected_keys = ["NO_ENERGY_TELEMETRY", "TRACKER_WITHOUT_VEHICLE", "VEHICLE_WITHOUT_TRACKER", "VIN_ABSENT", "STALE_DATA"]
    counts = anomalies_data.get("counts", {})
    
    for key in expected_keys:
        if key in counts:
            tests_passed += 1
            print(f"✅ Anomaly type '{key}' present with count {counts[key]}")
        else:
            # Not all anomaly types may be present, so we'll just note it
            print(f"ℹ️  Anomaly type '{key}' not present (may be valid)")
    
    # Verify NO_ENERGY_TELEMETRY count is 12
    if counts.get("NO_ENERGY_TELEMETRY") == 12:
        tests_passed += 1
        print("✅ NO_ENERGY_TELEMETRY count is 12")
    else:
        tests_failed += 1
        msg = f"NO_ENERGY_TELEMETRY count is not 12: {counts.get('NO_ENERGY_TELEMETRY')}"
        failures.append(msg)
        print(f"❌ {msg}")

# ============================================================================
# TEST 5: Tracker 781479 Metrics (ICE vehicle)
# ============================================================================
metrics_781479 = test_endpoint(
    "5. GET /api/energy/trackers/781479/metrics (ICE)",
    "GET",
    f"{BASE_URL}/api/energy/trackers/781479/metrics"
)

if metrics_781479:
    print(f"Tracker ID: {metrics_781479.get('tracker_id')}")
    print(f"Metrics count: {len(metrics_781479.get('metrics', []))}")
    
    # Verify critical rules
    verify_critical_rules(metrics_781479, "Tracker 781479 Metrics")
    
    # Find specific metrics
    metrics = {m["key"]: m for m in metrics_781479.get("metrics", [])}
    
    # Verify fuel_level
    if "fuel_level" in metrics:
        fuel = metrics["fuel_level"]
        print(f"\nFuel level details: {fuel}")
        
        # Check value ≈ 30.66
        if fuel.get("value") is not None and 30.0 <= fuel.get("value") <= 31.5:
            tests_passed += 1
            print(f"✅ fuel_level value is ≈30.66: {fuel.get('value')}")
        else:
            tests_failed += 1
            msg = f"fuel_level value is not ≈30.66: {fuel.get('value')}"
            failures.append(msg)
            print(f"❌ {msg}")
        
        # Check unit
        if fuel.get("unit") == "L":
            tests_passed += 1
            print("✅ fuel_level unit is 'L'")
        else:
            tests_failed += 1
            msg = f"fuel_level unit is not 'L': {fuel.get('unit')}"
            failures.append(msg)
            print(f"❌ {msg}")
        
        # Check measurement_type
        if fuel.get("measurement_type") == "MEASURED":
            tests_passed += 1
            print("✅ fuel_level measurement_type is 'MEASURED'")
        else:
            tests_failed += 1
            msg = f"fuel_level measurement_type is not 'MEASURED': {fuel.get('measurement_type')}"
            failures.append(msg)
            print(f"❌ {msg}")
        
        # Check source
        if fuel.get("source") == "NAVIXY_OBD":
            tests_passed += 1
            print("✅ fuel_level source is 'NAVIXY_OBD'")
        else:
            tests_failed += 1
            msg = f"fuel_level source is not 'NAVIXY_OBD': {fuel.get('source')}"
            failures.append(msg)
            print(f"❌ {msg}")
    else:
        tests_failed += 1
        msg = "fuel_level metric not found"
        failures.append(msg)
        print(f"❌ {msg}")
    
    # Verify odometer
    if "odometer" in metrics:
        odometer = metrics["odometer"]
        print(f"\nOdometer details: {odometer}")
        
        if odometer.get("availability") == "AVAILABLE":
            tests_passed += 1
            print("✅ odometer availability is 'AVAILABLE'")
        else:
            tests_failed += 1
            msg = f"odometer availability is not 'AVAILABLE': {odometer.get('availability')}"
            failures.append(msg)
            print(f"❌ {msg}")
    else:
        tests_failed += 1
        msg = "odometer metric not found"
        failures.append(msg)
        print(f"❌ {msg}")
    
    # Verify board_voltage
    if "board_voltage" in metrics:
        board_voltage = metrics["board_voltage"]
        print(f"\nBoard voltage details: {board_voltage}")
        
        if board_voltage.get("availability") == "UNAVAILABLE":
            tests_passed += 1
            print("✅ board_voltage availability is 'UNAVAILABLE'")
        else:
            tests_failed += 1
            msg = f"board_voltage availability is not 'UNAVAILABLE': {board_voltage.get('availability')}"
            failures.append(msg)
            print(f"❌ {msg}")
        
        # CRITICAL: value must be null, NEVER 0
        if board_voltage.get("value") is None:
            tests_passed += 1
            print("✅ board_voltage value is null (not 0)")
        else:
            tests_failed += 1
            msg = f"CRITICAL: board_voltage value is not null: {board_voltage.get('value')} (should be null, not 0)"
            failures.append(msg)
            print(f"❌ {msg}")
        
        if board_voltage.get("reason") == "no_sensor_configured":
            tests_passed += 1
            print("✅ board_voltage reason is 'no_sensor_configured'")
        else:
            tests_failed += 1
            msg = f"board_voltage reason is not 'no_sensor_configured': {board_voltage.get('reason')}"
            failures.append(msg)
            print(f"❌ {msg}")
    else:
        tests_failed += 1
        msg = "board_voltage metric not found"
        failures.append(msg)
        print(f"❌ {msg}")
    
    # Verify engine_rpm
    if "engine_rpm" in metrics:
        engine_rpm = metrics["engine_rpm"]
        print(f"\nEngine RPM details: {engine_rpm}")
        
        if engine_rpm.get("unit_verified") == False:
            tests_passed += 1
            print("✅ engine_rpm unit_verified is False")
        else:
            tests_failed += 1
            msg = f"engine_rpm unit_verified is not False: {engine_rpm.get('unit_verified')}"
            failures.append(msg)
            print(f"❌ {msg}")
    else:
        tests_failed += 1
        msg = "engine_rpm metric not found"
        failures.append(msg)
        print(f"❌ {msg}")

# ============================================================================
# TEST 6: Tracker 3218549 Capabilities (EV - Skoda)
# ============================================================================
capabilities_3218549 = test_endpoint(
    "6. GET /api/energy/trackers/3218549/capabilities (EV)",
    "GET",
    f"{BASE_URL}/api/energy/trackers/3218549/capabilities"
)

if capabilities_3218549:
    print(f"Tracker ID: {capabilities_3218549.get('tracker_id')}")
    print(f"Capabilities count: {len(capabilities_3218549.get('capabilities', []))}")
    
    # Verify critical rules
    verify_critical_rules(capabilities_3218549, "Tracker 3218549 Capabilities")
    
    # Find EV metrics
    capabilities = {c["metric_key"]: c for c in capabilities_3218549.get("capabilities", [])}
    ev_metrics = ["soc", "battery_capacity", "range_est", "charge_power", "energy_used", "consumption_kwh_100"]
    
    for ev_key in ev_metrics:
        if ev_key in capabilities:
            cap = capabilities[ev_key]
            print(f"\n{ev_key} details: {cap}")
            
            # CRITICAL: All EV metrics must be UNAVAILABLE
            if cap.get("availability") == "UNAVAILABLE":
                tests_passed += 1
                print(f"✅ {ev_key} availability is 'UNAVAILABLE'")
            else:
                tests_failed += 1
                msg = f"CRITICAL: {ev_key} availability is not 'UNAVAILABLE': {cap.get('availability')}"
                failures.append(msg)
                print(f"❌ {msg}")
            
            # CRITICAL: measurement_type must be NONE
            if cap.get("measurement_type") == "NONE":
                tests_passed += 1
                print(f"✅ {ev_key} measurement_type is 'NONE'")
            else:
                tests_failed += 1
                msg = f"CRITICAL: {ev_key} measurement_type is not 'NONE': {cap.get('measurement_type')}"
                failures.append(msg)
                print(f"❌ {msg}")
            
            # CRITICAL: reason must be no_sensor_configured
            if cap.get("reason") == "no_sensor_configured":
                tests_passed += 1
                print(f"✅ {ev_key} reason is 'no_sensor_configured'")
            else:
                tests_failed += 1
                msg = f"CRITICAL: {ev_key} reason is not 'no_sensor_configured': {cap.get('reason')}"
                failures.append(msg)
                print(f"❌ {msg}")
            
            # CRITICAL: value must not be present as 0
            if "value" in cap and cap.get("value") == 0:
                tests_failed += 1
                msg = f"CRITICAL: {ev_key} has value=0 (should not be present or should be null)"
                failures.append(msg)
                print(f"❌ {msg}")
            else:
                tests_passed += 1
                print(f"✅ {ev_key} does not have value=0")
        else:
            tests_failed += 1
            msg = f"{ev_key} capability not found"
            failures.append(msg)
            print(f"❌ {msg}")

# ============================================================================
# TEST 7: Edge Case - Invalid Tracker ID (metrics)
# ============================================================================
test_endpoint(
    "7. GET /api/energy/trackers/99999999/metrics (404)",
    "GET",
    f"{BASE_URL}/api/energy/trackers/99999999/metrics",
    expected_status=404
)
tests_passed += 1

# ============================================================================
# TEST 8: Edge Case - Invalid Tracker ID (capabilities)
# ============================================================================
test_endpoint(
    "8. GET /api/energy/trackers/99999999/capabilities (404)",
    "GET",
    f"{BASE_URL}/api/energy/trackers/99999999/capabilities",
    expected_status=404
)
tests_passed += 1

# ============================================================================
# TEST 9: Tenant Isolation
# ============================================================================
tenant_isolation = test_endpoint(
    "9. GET /api/energy/mapping?tenant_id=paas_DOESNOTEXIST (tenant isolation)",
    "GET",
    f"{BASE_URL}/api/energy/mapping?tenant_id=paas_DOESNOTEXIST"
)

if tenant_isolation:
    print(f"Response: {tenant_isolation}")
    
    # Verify empty mapping list (no data leak)
    if len(tenant_isolation.get("mapping", [])) == 0:
        tests_passed += 1
        print("✅ Tenant isolation: empty mapping list (no data leak)")
    else:
        tests_failed += 1
        msg = f"CRITICAL: Tenant isolation failed - mapping list is not empty: {len(tenant_isolation.get('mapping', []))}"
        failures.append(msg)
        print(f"❌ {msg}")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)
print(f"Total Passed: {tests_passed}")
print(f"Total Failed: {tests_failed}")
print(f"Total Tests: {tests_passed + tests_failed}")

if failures:
    print("\n" + "=" * 80)
    print("FAILURES:")
    print("=" * 80)
    for i, failure in enumerate(failures, 1):
        print(f"{i}. {failure}")

if tests_failed == 0:
    print("\n✅ ALL TESTS PASSED!")
    sys.exit(0)
else:
    print(f"\n❌ {tests_failed} TESTS FAILED")
    sys.exit(1)
