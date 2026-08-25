#!/usr/bin/env python3
"""
Test Energy v1 trips batch endpoint - CRITICAL NESTING VERIFICATION
Verify that fuel and electric are DIRECTLY under result, NOT under result["energy"]
"""
import requests
import json
import os
import sys
from datetime import datetime

# Read environment variables
BACKEND_URL = "https://energy-telemetry-1.preview.emergentagent.com"
ENERGY_API_TOKEN = "3N5HmYTEbKf58YXgAM7LkTAzmVNa6nhBkO761jNhp_cSZsw7OuyH1M4OXSnf_QBM"

# NEVER print the token
print("=" * 80)
print("ENERGY V1 TRIPS BATCH - NESTING VERIFICATION TEST")
print("=" * 80)
print(f"Backend URL: {BACKEND_URL}")
print(f"Token: [REDACTED]")
print()

# Headers with Bearer token
headers = {
    "Authorization": f"Bearer {ENERGY_API_TOKEN}",
    "Content-Type": "application/json"
}

# Step 1: Ensure data exists - call sync endpoint
print("STEP 1: Ensuring data exists via POST /api/energy/sync")
print("-" * 80)
sync_url = f"{BACKEND_URL}/api/energy/sync"
sync_payload = {"tenant_id": "paas_13588"}

try:
    print(f"POST {sync_url}")
    print(f"Payload: {json.dumps(sync_payload, indent=2)}")
    sync_start = datetime.now()
    sync_response = requests.post(sync_url, json=sync_payload, headers=headers, timeout=120)
    sync_duration = (datetime.now() - sync_start).total_seconds()
    
    print(f"Status: {sync_response.status_code}")
    print(f"Duration: {sync_duration:.2f}s")
    
    if sync_response.status_code == 200:
        sync_data = sync_response.json()
        print(f"✅ Sync successful")
        print(f"   Tenant: {sync_data.get('tenant_id')}")
        print(f"   Trackers: {sync_data.get('trackers_synced')}")
        print(f"   Vehicles: {sync_data.get('vehicles_synced')}")
    else:
        print(f"❌ Sync failed: {sync_response.text}")
        sys.exit(1)
except Exception as e:
    print(f"❌ Sync error: {e}")
    sys.exit(1)

print()
print()

# Step 2: Test trips batch endpoint
print("STEP 2: Testing POST /api/energy/v1/trips/energy:batch")
print("-" * 80)
batch_url = f"{BACKEND_URL}/api/energy/v1/trips/energy:batch"
batch_payload = {
    "tenant_id": "paas_13588",
    "trips": [
        {
            "trip_id": "A",
            "ref": 781479,
            "start": "2026-08-18T08:00:00Z",
            "end": "2026-08-18T08:40:00Z"
        },
        {
            "trip_id": "B",
            "ref": 999999,
            "start": "x",
            "end": "y"
        }
    ]
}

try:
    print(f"POST {batch_url}")
    print(f"Payload: {json.dumps(batch_payload, indent=2)}")
    batch_response = requests.post(batch_url, json=batch_payload, headers=headers, timeout=30)
    
    print(f"Status: {batch_response.status_code}")
    
    if batch_response.status_code != 200:
        print(f"❌ Expected HTTP 200, got {batch_response.status_code}")
        print(f"Response: {batch_response.text}")
        sys.exit(1)
    
    print(f"✅ HTTP 200 received")
    
    # Parse response
    response_data = batch_response.json()
    
    # Print the EXACT serialized JSON for inspection
    print()
    print("EXACT SERIALIZED JSON RESPONSE:")
    print("=" * 80)
    print(json.dumps(response_data, indent=2))
    print("=" * 80)
    print()
    
except Exception as e:
    print(f"❌ Request error: {e}")
    sys.exit(1)

# ASSERTIONS
print()
print("ASSERTIONS:")
print("=" * 80)

all_passed = True

# Assertion 1: Top-level structure
print("\n1. Top-level structure")
print("-" * 40)
top_keys = list(response_data.keys())
print(f"   Observed top-level keys: {top_keys}")

if "contract_version" not in response_data:
    print(f"   ❌ FAIL: Missing 'contract_version' key")
    all_passed = False
elif response_data["contract_version"] != "1.0":
    print(f"   ❌ FAIL: contract_version = {response_data['contract_version']}, expected '1.0'")
    all_passed = False
else:
    print(f"   ✅ PASS: contract_version = '1.0'")

if "results" not in response_data:
    print(f"   ❌ FAIL: Missing 'results' key")
    all_passed = False
elif not isinstance(response_data["results"], list):
    print(f"   ❌ FAIL: 'results' is not a list")
    all_passed = False
elif len(response_data["results"]) != 2:
    print(f"   ❌ FAIL: 'results' has {len(response_data['results'])} items, expected 2")
    all_passed = False
else:
    print(f"   ✅ PASS: 'results' is a list with 2 items")

# Assertion 2: Result item structure - CRITICAL NESTING CHECK
print("\n2. Result item structure - CRITICAL NESTING CHECK")
print("-" * 40)

results = response_data.get("results", [])

for idx, result in enumerate(results):
    print(f"\n   Result[{idx}] (trip_id={result.get('trip_id')}):")
    result_keys = list(result.keys())
    print(f"   Observed keys: {result_keys}")
    
    # Check for required keys at the SAME LEVEL
    required_keys = ["trip_id", "availability", "reason", "powertrain", "fuel", "electric", "contract_version"]
    missing_keys = [k for k in required_keys if k not in result]
    
    if missing_keys:
        print(f"   ❌ FAIL: Missing keys: {missing_keys}")
        all_passed = False
    else:
        print(f"   ✅ PASS: All required keys present at same level")
    
    # CRITICAL: Check that there is NO "energy" wrapper key
    if "energy" in result:
        print(f"   ❌ FAIL: CRITICAL - 'energy' wrapper key EXISTS in result (should be ABSENT)")
        print(f"   ❌ This means fuel and electric are nested under result['energy'], not directly under result")
        all_passed = False
    else:
        print(f"   ✅ PASS: CRITICAL - NO 'energy' wrapper key (fuel and electric are DIRECTLY under result)")
    
    # Check contract_version
    if result.get("contract_version") != "1.0":
        print(f"   ❌ FAIL: result['contract_version'] = {result.get('contract_version')}, expected '1.0'")
        all_passed = False
    else:
        print(f"   ✅ PASS: result['contract_version'] = '1.0'")
    
    # Check availability
    availability = result.get("availability")
    if availability not in ["AVAILABLE", "STALE", "UNAVAILABLE"]:
        print(f"   ❌ FAIL: availability = {availability}, expected one of AVAILABLE|STALE|UNAVAILABLE")
        all_passed = False
    else:
        print(f"   ✅ PASS: availability = {availability} (valid)")
    
    # Check powertrain
    powertrain = result.get("powertrain")
    valid_powertrains = ["ICE", "HEV", "PHEV", "BEV", "UNKNOWN", None]
    if powertrain not in valid_powertrains:
        print(f"   ❌ FAIL: powertrain = {powertrain}, expected one of ICE|HEV|PHEV|BEV|UNKNOWN|null")
        all_passed = False
    else:
        print(f"   ✅ PASS: powertrain = {powertrain} (valid)")

# Assertion 3: Fuel and electric object structure
print("\n3. Fuel and electric object structure")
print("-" * 40)

for idx, result in enumerate(results):
    print(f"\n   Result[{idx}] (trip_id={result.get('trip_id')}):")
    
    # Check fuel object
    fuel = result.get("fuel")
    if not isinstance(fuel, dict):
        print(f"   ❌ FAIL: 'fuel' is not a dict")
        all_passed = False
    else:
        fuel_keys = set(fuel.keys())
        expected_fuel_keys = {"fuel_liters", "consumption_l_100km"}
        if fuel_keys != expected_fuel_keys:
            print(f"   ❌ FAIL: fuel keys = {fuel_keys}, expected EXACTLY {expected_fuel_keys}")
            all_passed = False
        else:
            print(f"   ✅ PASS: fuel has EXACTLY keys {expected_fuel_keys}")
    
    # Check electric object
    electric = result.get("electric")
    if not isinstance(electric, dict):
        print(f"   ❌ FAIL: 'electric' is not a dict")
        all_passed = False
    else:
        electric_keys = set(electric.keys())
        expected_electric_keys = {"soc_start_pct", "soc_end_pct", "energy_kwh", "consumption_kwh_100km"}
        if electric_keys != expected_electric_keys:
            print(f"   ❌ FAIL: electric keys = {electric_keys}, expected EXACTLY {expected_electric_keys}")
            all_passed = False
        else:
            print(f"   ✅ PASS: electric has EXACTLY keys {expected_electric_keys}")

# Assertion 4: Metric envelope structure
print("\n4. Metric envelope structure (all 6 metrics)")
print("-" * 40)

for idx, result in enumerate(results):
    print(f"\n   Result[{idx}] (trip_id={result.get('trip_id')}):")
    
    fuel = result.get("fuel", {})
    electric = result.get("electric", {})
    
    all_metrics = {
        "fuel_liters": fuel.get("fuel_liters"),
        "consumption_l_100km": fuel.get("consumption_l_100km"),
        "soc_start_pct": electric.get("soc_start_pct"),
        "soc_end_pct": electric.get("soc_end_pct"),
        "energy_kwh": electric.get("energy_kwh"),
        "consumption_kwh_100km": electric.get("consumption_kwh_100km")
    }
    
    for metric_name, metric_value in all_metrics.items():
        if not isinstance(metric_value, dict):
            print(f"   ❌ FAIL: {metric_name} is not a metric envelope (dict)")
            all_passed = False
            continue
        
        # Check required envelope keys
        required_envelope_keys = ["value", "unit", "unit_verified", "availability", "measurement_type", "source", "timestamp", "reason"]
        missing_envelope_keys = [k for k in required_envelope_keys if k not in metric_value]
        
        if missing_envelope_keys:
            print(f"   ❌ FAIL: {metric_name} missing envelope keys: {missing_envelope_keys}")
            all_passed = False
            continue
        
        # Check availability is UNAVAILABLE
        if metric_value.get("availability") != "UNAVAILABLE":
            print(f"   ❌ FAIL: {metric_name} availability = {metric_value.get('availability')}, expected UNAVAILABLE")
            all_passed = False
        
        # Check value is null (not 0)
        if metric_value.get("value") is not None:
            print(f"   ❌ FAIL: {metric_name} value = {metric_value.get('value')}, expected null (not 0)")
            all_passed = False
        
        # Check measurement_type is never the string "NONE"
        if metric_value.get("measurement_type") == "NONE":
            print(f"   ❌ FAIL: {metric_name} measurement_type = 'NONE' (string), should be null or other value")
            all_passed = False
        
        # Check availability is never "ERROR"
        if metric_value.get("availability") == "ERROR":
            print(f"   ❌ FAIL: {metric_name} availability = 'ERROR', should never be ERROR")
            all_passed = False
    
    print(f"   ✅ All 6 metrics are UNAVAILABLE envelopes with value=null")

# Assertion 5: Trip-specific checks
print("\n5. Trip-specific checks")
print("-" * 40)

for idx, result in enumerate(results):
    trip_id = result.get("trip_id")
    tracker_id = result.get("tracker_id")
    
    if trip_id == "A":
        if tracker_id != 781479:
            print(f"   ❌ FAIL: Trip A tracker_id = {tracker_id}, expected 781479")
            all_passed = False
        else:
            print(f"   ✅ PASS: Trip A tracker_id = 781479")
    
    elif trip_id == "B":
        if tracker_id is not None:
            print(f"   ❌ FAIL: Trip B tracker_id = {tracker_id}, expected null (mapping invalid)")
            all_passed = False
        else:
            print(f"   ✅ PASS: Trip B tracker_id = null (mapping invalid)")

# Final summary
print()
print("=" * 80)
print("FINAL SUMMARY")
print("=" * 80)

if all_passed:
    print("✅ ALL ASSERTIONS PASSED")
    print()
    print("CRITICAL VERIFICATION:")
    print("  ✅ NO 'energy' wrapper key exists in any result")
    print("  ✅ 'fuel' and 'electric' are DIRECTLY under result object")
    print("  ✅ Correct nesting structure confirmed")
    sys.exit(0)
else:
    print("❌ SOME ASSERTIONS FAILED")
    print()
    print("Review the detailed output above for specific failures")
    sys.exit(1)
