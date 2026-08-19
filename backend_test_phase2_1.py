"""
Comprehensive backend tests for LOGITRAK Energy Phase 2.1.
Tests regression (Phase 2) + new endpoints (mapping-proposals, ev-feasibility, 
mapping-changes, readiness) with real Navixy integration (READ-ONLY, paas_13588).
"""
import requests
import time
import sys
import json

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
            tests_passed += 1
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

def verify_field(data, field_path, expected_value=None, check_exists=True, test_name=""):
    """Verify a field exists and optionally matches expected value."""
    global tests_passed, tests_failed, failures
    
    keys = field_path.split('.')
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            if check_exists:
                tests_failed += 1
                msg = f"Field '{field_path}' not found in {test_name}"
                failures.append(msg)
                print(f"❌ {msg}")
            return False
    
    if expected_value is not None:
        if current == expected_value:
            tests_passed += 1
            print(f"✅ {field_path} = {current}")
            return True
        else:
            tests_failed += 1
            msg = f"Field '{field_path}' expected {expected_value}, got {current} in {test_name}"
            failures.append(msg)
            print(f"❌ {msg}")
            return False
    else:
        tests_passed += 1
        print(f"✅ {field_path} exists: {current}")
        return True

# ============================================================================
# A) REGRESSION TESTS (Phase 2 - must still pass)
# ============================================================================

print("\n" + "=" * 80)
print("A) REGRESSION TESTS (Phase 2)")
print("=" * 80)

# TEST 1: Health Check
health_data = test_endpoint(
    "1. GET /api/energy/health",
    "GET",
    f"{BASE_URL}/api/energy/health"
)

if health_data:
    verify_field(health_data, "status", "ok", test_name="health")
    verify_field(health_data, "navixy_configured", True, test_name="health")

# TEST 2: Sync (FIRST sync - may take ~60s)
print("\n⏳ Running FIRST sync (this may take up to 60 seconds)...")
sync_data_1 = test_endpoint(
    "2. POST /api/energy/sync (FIRST)",
    "POST",
    f"{BASE_URL}/api/energy/sync",
    timeout=70
)

if sync_data_1:
    print(f"Sync response: {json.dumps(sync_data_1, indent=2)}")

# Wait for data to be persisted
time.sleep(2)

# TEST 3: Mapping
mapping_data = test_endpoint(
    "3. GET /api/energy/mapping",
    "GET",
    f"{BASE_URL}/api/energy/mapping"
)

if mapping_data:
    mapping_list = mapping_data.get("mapping", [])
    if len(mapping_list) == 12:
        tests_passed += 1
        print(f"✅ Mapping has 12 entries")
    else:
        tests_failed += 1
        msg = f"Mapping expected 12 entries, got {len(mapping_list)}"
        failures.append(msg)
        print(f"❌ {msg}")
    
    # Find tracker 781479
    tracker_781479 = next((e for e in mapping_list if e.get("tracker_id") == 781479), None)
    if tracker_781479:
        verify_field(tracker_781479, "confidence", "HIGH", test_name="tracker 781479")
        verify_field(tracker_781479, "obd_vin", "WAUZZZ8V0JA152970", test_name="tracker 781479")
    else:
        tests_failed += 1
        msg = "Tracker 781479 not found in mapping"
        failures.append(msg)
        print(f"❌ {msg}")

# TEST 4: Anomalies
anomalies_data = test_endpoint(
    "4. GET /api/energy/anomalies",
    "GET",
    f"{BASE_URL}/api/energy/anomalies"
)

if anomalies_data:
    counts = anomalies_data.get("counts", {})
    print(f"Anomaly counts: {counts}")
    
    # Verify expected anomaly types
    expected_types = ["NO_ENERGY_TELEMETRY", "TRACKER_WITHOUT_VEHICLE", 
                      "VEHICLE_WITHOUT_TRACKER", "VIN_ABSENT", "STALE_DATA"]
    for atype in expected_types:
        if atype in counts:
            tests_passed += 1
            print(f"✅ Anomaly type '{atype}' present: {counts[atype]}")
        else:
            print(f"ℹ️  Anomaly type '{atype}' not present")
    
    # Verify NO_ENERGY_TELEMETRY = 12
    verify_field(counts, "NO_ENERGY_TELEMETRY", 12, test_name="anomalies")

# TEST 5: Tracker 781479 Metrics
metrics_781479 = test_endpoint(
    "5. GET /api/energy/trackers/781479/metrics",
    "GET",
    f"{BASE_URL}/api/energy/trackers/781479/metrics"
)

if metrics_781479:
    metrics = {m["key"]: m for m in metrics_781479.get("metrics", [])}
    
    # Verify fuel_level
    if "fuel_level" in metrics:
        fuel = metrics["fuel_level"]
        verify_field(fuel, "measurement_type", "MEASURED", test_name="fuel_level")
        verify_field(fuel, "source", "NAVIXY_OBD", test_name="fuel_level")
    
    # Verify odometer
    if "odometer" in metrics:
        verify_field(metrics["odometer"], "availability", "AVAILABLE", test_name="odometer")
    
    # Verify board_voltage (CRITICAL: value must be null, not 0)
    if "board_voltage" in metrics:
        bv = metrics["board_voltage"]
        verify_field(bv, "availability", "UNAVAILABLE", test_name="board_voltage")
        if bv.get("value") is None:
            tests_passed += 1
            print("✅ board_voltage value is null (not 0)")
        else:
            tests_failed += 1
            msg = f"CRITICAL: board_voltage value should be null, got {bv.get('value')}"
            failures.append(msg)
            print(f"❌ {msg}")

# TEST 6: Tracker 3218549 Capabilities (EV)
capabilities_3218549 = test_endpoint(
    "6. GET /api/energy/trackers/3218549/capabilities",
    "GET",
    f"{BASE_URL}/api/energy/trackers/3218549/capabilities"
)

if capabilities_3218549:
    capabilities = {c["metric_key"]: c for c in capabilities_3218549.get("capabilities", [])}
    ev_metrics = ["soc", "battery_capacity", "range_est", "charge_power", "energy_used", "consumption_kwh_100"]
    
    for ev_key in ev_metrics:
        if ev_key in capabilities:
            cap = capabilities[ev_key]
            if cap.get("availability") == "UNAVAILABLE":
                tests_passed += 1
                print(f"✅ {ev_key} is UNAVAILABLE")
            else:
                tests_failed += 1
                msg = f"CRITICAL: {ev_key} should be UNAVAILABLE, got {cap.get('availability')}"
                failures.append(msg)
                print(f"❌ {msg}")

# ============================================================================
# B) NEW ENDPOINTS (Phase 2.1)
# ============================================================================

print("\n" + "=" * 80)
print("B) NEW ENDPOINTS (Phase 2.1)")
print("=" * 80)

# TEST 7: Mapping Proposals
proposals_data = test_endpoint(
    "7. GET /api/energy/mapping-proposals",
    "GET",
    f"{BASE_URL}/api/energy/mapping-proposals"
)

if proposals_data:
    print(f"\nProposals response structure: {json.dumps({k: type(v).__name__ for k, v in proposals_data.items()}, indent=2)}")
    
    # Verify structure
    verify_field(proposals_data, "counts", check_exists=True, test_name="proposals")
    verify_field(proposals_data, "proposals", check_exists=True, test_name="proposals")
    
    proposals = proposals_data.get("proposals", [])
    counts = proposals_data.get("counts", {})
    
    print(f"\nProposal counts by classification: {counts}")
    print(f"Total proposals: {len(proposals)}")
    
    # Verify each proposal has required fields
    required_fields = ["anomaly", "classification", "tracker_id", "vehicle_id", 
                       "current_label", "vehicle_vin", "obd_vin", "proposed_match",
                       "evidence", "recommended_action", "confidence"]
    
    if proposals:
        sample_proposal = proposals[0]
        print(f"\nSample proposal: {json.dumps(sample_proposal, indent=2)}")
        
        all_valid = True
        for field in required_fields:
            if field not in sample_proposal:
                tests_failed += 1
                msg = f"Proposal missing required field: {field}"
                failures.append(msg)
                print(f"❌ {msg}")
                all_valid = False
        
        if all_valid:
            tests_passed += 1
            print("✅ All required fields present in proposals")
        
        # CRITICAL: Verify NO proposal is derived solely from label
        label_based_proposals = []
        for p in proposals:
            evidence = p.get("evidence", [])
            evidence_str = " ".join(evidence).lower()
            # Check if evidence mentions label/name but not VIN/vehicle identifiers
            if ("label" in evidence_str or "name" in evidence_str) and \
               ("vin" not in evidence_str and "vehicle" not in evidence_str.replace("vehicle_id", "")):
                label_based_proposals.append(p)
        
        if label_based_proposals:
            tests_failed += 1
            msg = f"CRITICAL: {len(label_based_proposals)} proposals derived from label (should use VIN/vehicle identifiers only)"
            failures.append(msg)
            print(f"❌ {msg}")
            print(f"Label-based proposals: {json.dumps(label_based_proposals[:2], indent=2)}")
        else:
            tests_passed += 1
            print("✅ No proposals derived solely from label")
        
        # Verify classification values
        valid_classifications = ["SAFE_TO_REVIEW", "AMBIGUOUS", "INSUFFICIENT_DATA"]
        invalid_classifications = [p for p in proposals if p.get("classification") not in valid_classifications]
        if invalid_classifications:
            tests_failed += 1
            msg = f"Invalid classifications found: {[p.get('classification') for p in invalid_classifications]}"
            failures.append(msg)
            print(f"❌ {msg}")
        else:
            tests_passed += 1
            print(f"✅ All classifications valid: {list(counts.keys())}")
        
        # Given vehicle.vin is empty, expect INSUFFICIENT_DATA (none SAFE_TO_REVIEW)
        safe_proposals = [p for p in proposals if p.get("classification") == "SAFE_TO_REVIEW"]
        if safe_proposals:
            print(f"⚠️  WARNING: {len(safe_proposals)} SAFE_TO_REVIEW proposals found (expected 0 since vehicle.vin is empty)")
            print(f"Sample SAFE_TO_REVIEW: {json.dumps(safe_proposals[0], indent=2)}")
        else:
            tests_passed += 1
            print("✅ No SAFE_TO_REVIEW proposals (correct, since vehicle.vin is empty)")

# TEST 8: EV Feasibility
ev_feas_data = test_endpoint(
    "8. GET /api/energy/ev-feasibility",
    "GET",
    f"{BASE_URL}/api/energy/ev-feasibility"
)

if ev_feas_data:
    print(f"\nEV Feasibility response structure: {json.dumps({k: type(v).__name__ for k, v in ev_feas_data.items()}, indent=2)}")
    
    # Verify structure
    verify_field(ev_feas_data, "summary", check_exists=True, test_name="ev-feasibility")
    verify_field(ev_feas_data, "assessments", check_exists=True, test_name="ev-feasibility")
    
    summary = ev_feas_data.get("summary", {})
    assessments = ev_feas_data.get("assessments", [])
    
    print(f"\nSummary: {json.dumps(summary, indent=2)}")
    print(f"Total assessments: {len(assessments)}")
    
    # Verify device_families
    device_families = summary.get("device_families", {})
    print(f"Device families: {device_families}")
    
    # Expected: fmc130:6, fmb003:4, phone:2
    expected_families = {"fmc130": 6, "fmb003": 4, "phone": 2}
    families_match = device_families == expected_families
    if families_match:
        tests_passed += 1
        print(f"✅ Device families match expected: {expected_families}")
    else:
        tests_failed += 1
        msg = f"Device families mismatch. Expected {expected_families}, got {device_families}"
        failures.append(msg)
        print(f"❌ {msg}")
    
    # Verify ev_collectable_now = 0
    verify_field(summary, "ev_collectable_now", 0, test_name="ev-feasibility summary")
    
    # Verify assessments by device family
    if assessments:
        fmc130_trackers = [a for a in assessments if a.get("device_family") == "fmc130"]
        fmb003_trackers = [a for a in assessments if a.get("device_family") == "fmb003"]
        phone_trackers = [a for a in assessments if a.get("device_family") == "phone"]
        
        print(f"\nFMC130 trackers: {len(fmc130_trackers)}")
        print(f"FMB003 trackers: {len(fmb003_trackers)}")
        print(f"Phone trackers: {len(phone_trackers)}")
        
        # Verify FMC130: soc metric channel == NEEDS_HARDWARE, confidence MEDIUM
        if fmc130_trackers:
            sample_fmc130 = fmc130_trackers[0]
            print(f"\nSample FMC130 assessment: {json.dumps(sample_fmc130, indent=2)}")
            
            soc_metric = next((m for m in sample_fmc130.get("metrics", []) if m.get("metric") == "soc"), None)
            if soc_metric:
                if soc_metric.get("channel") == "NEEDS_HARDWARE":
                    tests_passed += 1
                    print("✅ FMC130 soc channel is NEEDS_HARDWARE")
                else:
                    tests_failed += 1
                    msg = f"FMC130 soc channel expected NEEDS_HARDWARE, got {soc_metric.get('channel')}"
                    failures.append(msg)
                    print(f"❌ {msg}")
                
                if soc_metric.get("confidence") == "MEDIUM":
                    tests_passed += 1
                    print("✅ FMC130 soc confidence is MEDIUM")
                else:
                    tests_failed += 1
                    msg = f"FMC130 soc confidence expected MEDIUM, got {soc_metric.get('confidence')}"
                    failures.append(msg)
                    print(f"❌ {msg}")
        
        # Verify FMB003: soc metric channel == NOT_VERIFIABLE, confidence LOW
        if fmb003_trackers:
            sample_fmb003 = fmb003_trackers[0]
            print(f"\nSample FMB003 assessment: {json.dumps(sample_fmb003, indent=2)}")
            
            soc_metric = next((m for m in sample_fmb003.get("metrics", []) if m.get("metric") == "soc"), None)
            if soc_metric:
                if soc_metric.get("channel") == "NOT_VERIFIABLE":
                    tests_passed += 1
                    print("✅ FMB003 soc channel is NOT_VERIFIABLE")
                else:
                    tests_failed += 1
                    msg = f"FMB003 soc channel expected NOT_VERIFIABLE, got {soc_metric.get('channel')}"
                    failures.append(msg)
                    print(f"❌ {msg}")
                
                if soc_metric.get("confidence") == "LOW":
                    tests_passed += 1
                    print("✅ FMB003 soc confidence is LOW")
                else:
                    tests_failed += 1
                    msg = f"FMB003 soc confidence expected LOW, got {soc_metric.get('confidence')}"
                    failures.append(msg)
                    print(f"❌ {msg}")
        
        # Verify Phone: soc metric channel == NOT_SUPPORTED
        if phone_trackers:
            sample_phone = phone_trackers[0]
            print(f"\nSample Phone assessment: {json.dumps(sample_phone, indent=2)}")
            
            soc_metric = next((m for m in sample_phone.get("metrics", []) if m.get("metric") == "soc"), None)
            if soc_metric:
                if soc_metric.get("channel") == "NOT_SUPPORTED":
                    tests_passed += 1
                    print("✅ Phone soc channel is NOT_SUPPORTED")
                else:
                    tests_failed += 1
                    msg = f"Phone soc channel expected NOT_SUPPORTED, got {soc_metric.get('channel')}"
                    failures.append(msg)
                    print(f"❌ {msg}")
        
        # CRITICAL: Verify no assessment claims metric is NATIVE/available now
        native_assessments = []
        for a in assessments:
            for m in a.get("metrics", []):
                if m.get("channel") in ("NATIVE", "VIA_CAN") and not a.get("ev_sensors_configured"):
                    native_assessments.append({"tracker_id": a.get("tracker_id"), "metric": m.get("metric"), "channel": m.get("channel")})
        
        if native_assessments:
            tests_failed += 1
            msg = f"CRITICAL: {len(native_assessments)} metrics claim NATIVE/VIA_CAN without sensors configured"
            failures.append(msg)
            print(f"❌ {msg}")
            print(f"Invalid assessments: {json.dumps(native_assessments[:3], indent=2)}")
        else:
            tests_passed += 1
            print("✅ No assessment claims metric is NATIVE/available without sensors")

# TEST 9: Mapping Changes (after first sync)
changes_data_1 = test_endpoint(
    "9. GET /api/energy/mapping-changes (after first sync)",
    "GET",
    f"{BASE_URL}/api/energy/mapping-changes"
)

changes_count_1 = 0
if changes_data_1:
    changes = changes_data_1.get("changes", [])
    changes_count_1 = len(changes)
    print(f"\nMapping changes after first sync: {changes_count_1}")
    
    # After first sync, expect NEW_ASSOCIATION changes
    if changes_count_1 > 0:
        tests_passed += 1
        print(f"✅ Found {changes_count_1} change events after first sync")
        
        # Check for NEW_ASSOCIATION type
        new_assoc = [c for c in changes if c.get("type") == "NEW_ASSOCIATION"]
        print(f"NEW_ASSOCIATION events: {len(new_assoc)}")
        if new_assoc:
            print(f"Sample NEW_ASSOCIATION: {json.dumps(new_assoc[0], indent=2)}")
    else:
        print(f"ℹ️  No change events after first sync (may be valid if no associations)")

# TEST 10: Idempotency - Second Sync
print("\n⏳ Running SECOND sync for idempotency test...")
sync_data_2 = test_endpoint(
    "10. POST /api/energy/sync (SECOND - idempotency)",
    "POST",
    f"{BASE_URL}/api/energy/sync",
    timeout=70
)

if sync_data_2:
    print(f"Second sync response: {json.dumps(sync_data_2, indent=2)}")

time.sleep(2)

# TEST 11: Mapping Changes (after second sync - idempotency check)
changes_data_2 = test_endpoint(
    "11. GET /api/energy/mapping-changes (after second sync)",
    "GET",
    f"{BASE_URL}/api/energy/mapping-changes"
)

if changes_data_2:
    changes_count_2 = len(changes_data_2.get("changes", []))
    print(f"\nMapping changes after second sync: {changes_count_2}")
    print(f"Changes count before: {changes_count_1}")
    print(f"Changes count after: {changes_count_2}")
    
    # CRITICAL: Count should NOT increase (idempotency)
    if changes_count_2 == changes_count_1:
        tests_passed += 1
        print(f"✅ IDEMPOTENCY PASS: No phantom changes (count unchanged: {changes_count_1})")
    else:
        tests_failed += 1
        msg = f"CRITICAL: IDEMPOTENCY FAIL: Changes increased from {changes_count_1} to {changes_count_2} (expected no change)"
        failures.append(msg)
        print(f"❌ {msg}")

# TEST 12: Readiness
readiness_data = test_endpoint(
    "12. GET /api/energy/readiness",
    "GET",
    f"{BASE_URL}/api/energy/readiness"
)

if readiness_data:
    print(f"\nReadiness response: {json.dumps(readiness_data, indent=2)}")
    
    # Verify structure
    verify_field(readiness_data, "recommendation", check_exists=True, test_name="readiness")
    verify_field(readiness_data, "kpis", check_exists=True, test_name="readiness")
    verify_field(readiness_data, "reasons", check_exists=True, test_name="readiness")
    
    # Verify recommendation is NOT_READY_FOR_A_E
    verify_field(readiness_data, "recommendation", "NOT_READY_FOR_A_E", test_name="readiness")
    
    kpis = readiness_data.get("kpis", {})
    print(f"\nKPIs: {json.dumps(kpis, indent=2)}")
    
    # Verify expected KPI fields
    expected_kpis = ["pct_trackers_associated", "pct_vehicles_associated", 
                     "vin_coverage_physical", "thermal_energy_coverage", 
                     "ev_energy_coverage", "stale_trackers", "blocking_anomalies"]
    
    for kpi in expected_kpis:
        if kpi in kpis:
            tests_passed += 1
            print(f"✅ KPI '{kpi}' present: {kpis[kpi]}")
        else:
            tests_failed += 1
            msg = f"KPI '{kpi}' missing"
            failures.append(msg)
            print(f"❌ {msg}")
    
    # Verify pct_trackers_associated ≈ 25.0 (3/12 trackers associated)
    pct_assoc = kpis.get("pct_trackers_associated", 0)
    if 20.0 <= pct_assoc <= 30.0:
        tests_passed += 1
        print(f"✅ pct_trackers_associated is ~25%: {pct_assoc}")
    else:
        print(f"ℹ️  pct_trackers_associated is {pct_assoc}% (expected ~25%)")
    
    # Verify ev_energy_coverage = 0.0
    verify_field(kpis, "ev_energy_coverage", 0.0, test_name="readiness KPIs")
    
    # Verify blocking_anomalies = 0
    verify_field(kpis, "blocking_anomalies", 0, test_name="readiness KPIs")
    
    # Verify reasons is non-empty
    reasons = readiness_data.get("reasons", [])
    if reasons:
        tests_passed += 1
        print(f"✅ Reasons provided: {len(reasons)} items")
        for r in reasons:
            print(f"  - {r}")
    else:
        tests_failed += 1
        msg = "Reasons list is empty"
        failures.append(msg)
        print(f"❌ {msg}")

# ============================================================================
# C) TENANT ISOLATION & EDGE CASES
# ============================================================================

print("\n" + "=" * 80)
print("C) TENANT ISOLATION & EDGE CASES")
print("=" * 80)

# TEST 13: Tenant Isolation - Mapping Proposals
proposals_isolation = test_endpoint(
    "13. GET /api/energy/mapping-proposals?tenant_id=paas_NONE",
    "GET",
    f"{BASE_URL}/api/energy/mapping-proposals?tenant_id=paas_NONE"
)

if proposals_isolation:
    proposals = proposals_isolation.get("proposals", [])
    if len(proposals) == 0:
        tests_passed += 1
        print("✅ Tenant isolation: empty proposals (no leak)")
    else:
        tests_failed += 1
        msg = f"CRITICAL: Tenant isolation failed - proposals not empty: {len(proposals)}"
        failures.append(msg)
        print(f"❌ {msg}")

# TEST 14: Tenant Isolation - EV Feasibility
ev_feas_isolation = test_endpoint(
    "14. GET /api/energy/ev-feasibility?tenant_id=paas_NONE",
    "GET",
    f"{BASE_URL}/api/energy/ev-feasibility?tenant_id=paas_NONE"
)

if ev_feas_isolation:
    assessments = ev_feas_isolation.get("assessments", [])
    if len(assessments) == 0:
        tests_passed += 1
        print("✅ Tenant isolation: empty assessments (no leak)")
    else:
        tests_failed += 1
        msg = f"CRITICAL: Tenant isolation failed - assessments not empty: {len(assessments)}"
        failures.append(msg)
        print(f"❌ {msg}")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("TEST SUMMARY - PHASE 2.1")
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
