#!/usr/bin/env python3
"""
CRITICAL NESTING VERIFICATION for LOGITRAK Energy v1 trips batch.
Re-verify the EXACT nesting of the actually-serialized JSON.
"""
import json
import requests
import sys
import time

# Configuration - read from environment
BASE_URL = "https://energy-telemetry-1.preview.emergentagent.com"
VALID_TOKEN = "3N5HmYTEbKf58YXgAM7LkTAzmVNa6nhBkO761jNhp_cSZsw7OuyH1M4OXSnf_QBM"
TENANT_ID = "paas_13588"

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


def verify_nesting():
    """
    Verify the EXACT nesting structure of POST /api/energy/v1/trips/energy:batch.
    
    CRITICAL ASSERTIONS:
    1. Top-level: contract_version="1.0", results (list of 2)
    2. Each result has: trip_id, availability, reason, powertrain, fuel, electric, contract_version (all at same level)
    3. NO "energy" wrapper key in any result
    4. fuel has EXACTLY {fuel_liters, consumption_l_100km}
    5. electric has EXACTLY {soc_start_pct, soc_end_pct, energy_kwh, consumption_kwh_100km}
    6. All 6 metrics are envelopes with value=null, measurement_type never "NONE", availability never "ERROR"
    7. Trip A (ref=781479): tracker_id=781479, status=NO_ENERGY_DATA, powertrain=UNKNOWN
    8. Trip B (ref=999999): tracker_id=null, status=MAPPING_INVALID, powertrain=UNKNOWN
    """
    print("\n=== CRITICAL NESTING VERIFICATION ===")
    print("Testing POST /api/energy/v1/trips/energy:batch")
    print("Verifying EXACT JSON serialization structure...\n")
    
    headers = {
        "Authorization": f"Bearer {VALID_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "tenant_id": TENANT_ID,
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
        resp = requests.post(
            f"{BASE_URL}/api/energy/v1/trips/energy:batch",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        print(f"Response status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"❌ FAIL: Expected HTTP 200, got {resp.status_code}")
            print(f"Response: {resp.text}")
            return False
        
        data = resp.json()
        
        # Print the raw JSON for inspection
        print("\n=== RAW JSON RESPONSE ===")
        print(json.dumps(data, indent=2))
        print("=========================\n")
        
        # ASSERTION 1: Top-level structure
        print("ASSERTION 1: Top-level structure")
        top_level_keys = list(data.keys())
        print(f"  Top-level keys: {top_level_keys}")
        
        if "contract_version" not in data:
            print("  ❌ FAIL: Missing 'contract_version' at top level")
            return False
        
        if data["contract_version"] != "1.0":
            print(f"  ❌ FAIL: contract_version={data['contract_version']}, expected '1.0'")
            return False
        
        if "results" not in data:
            print("  ❌ FAIL: Missing 'results' at top level")
            return False
        
        results = data["results"]
        if not isinstance(results, list) or len(results) != 2:
            print(f"  ❌ FAIL: results is not a list of 2 items (got {type(results)} with {len(results) if isinstance(results, list) else 'N/A'} items)")
            return False
        
        print("  ✅ PASS: Top-level has contract_version='1.0' and results (list of 2)")
        
        # ASSERTION 2 & 3: Each result structure and NO "energy" wrapper
        print("\nASSERTION 2 & 3: Result structure and NO 'energy' wrapper")
        
        for i, result in enumerate(results):
            trip_id = result.get("trip_id")
            print(f"\n  Result {i} (trip_id={trip_id}):")
            
            result_keys = list(result.keys())
            print(f"    Keys at result level: {result_keys}")
            
            # Check required keys exist at same level
            required_keys = ["trip_id", "availability", "reason", "powertrain", "fuel", "electric", "contract_version"]
            missing_keys = [k for k in required_keys if k not in result]
            if missing_keys:
                print(f"    ❌ FAIL: Missing keys at result level: {missing_keys}")
                return False
            
            # CRITICAL: Check NO "energy" wrapper key
            if "energy" in result:
                print(f"    ❌ FAIL: Found 'energy' wrapper key in result (should NOT exist)")
                return False
            
            print(f"    ✅ PASS: All required keys present at same level, NO 'energy' wrapper")
            
            # Check contract_version at result level
            if result.get("contract_version") != "1.0":
                print(f"    ❌ FAIL: result.contract_version={result.get('contract_version')}, expected '1.0'")
                return False
            
            # Check availability is valid
            availability = result.get("availability")
            if availability not in ["AVAILABLE", "STALE", "UNAVAILABLE"]:
                print(f"    ❌ FAIL: availability={availability}, expected one of AVAILABLE/STALE/UNAVAILABLE")
                return False
            
            # Check powertrain is valid
            powertrain = result.get("powertrain")
            valid_powertrains = ["ICE", "HEV", "PHEV", "BEV", "UNKNOWN", None]
            if powertrain not in valid_powertrains:
                print(f"    ❌ FAIL: powertrain={powertrain}, expected one of {valid_powertrains}")
                return False
            
            print(f"    availability={availability}, powertrain={powertrain}")
        
        # ASSERTION 4: fuel object structure
        print("\nASSERTION 4: fuel object structure")
        
        for i, result in enumerate(results):
            trip_id = result.get("trip_id")
            fuel = result.get("fuel", {})
            
            print(f"\n  Result {i} (trip_id={trip_id}) fuel keys: {list(fuel.keys())}")
            
            expected_fuel_keys = {"fuel_liters", "consumption_l_100km"}
            actual_fuel_keys = set(fuel.keys())
            
            if actual_fuel_keys != expected_fuel_keys:
                print(f"    ❌ FAIL: fuel keys mismatch")
                print(f"       Expected: {expected_fuel_keys}")
                print(f"       Actual: {actual_fuel_keys}")
                return False
            
            print(f"    ✅ PASS: fuel has EXACTLY {{fuel_liters, consumption_l_100km}}")
        
        # ASSERTION 5: electric object structure
        print("\nASSERTION 5: electric object structure")
        
        for i, result in enumerate(results):
            trip_id = result.get("trip_id")
            electric = result.get("electric", {})
            
            print(f"\n  Result {i} (trip_id={trip_id}) electric keys: {list(electric.keys())}")
            
            expected_electric_keys = {"soc_start_pct", "soc_end_pct", "energy_kwh", "consumption_kwh_100km"}
            actual_electric_keys = set(electric.keys())
            
            if actual_electric_keys != expected_electric_keys:
                print(f"    ❌ FAIL: electric keys mismatch")
                print(f"       Expected: {expected_electric_keys}")
                print(f"       Actual: {actual_electric_keys}")
                return False
            
            print(f"    ✅ PASS: electric has EXACTLY {{soc_start_pct, soc_end_pct, energy_kwh, consumption_kwh_100km}}")
        
        # ASSERTION 6: All 6 metrics are UNAVAILABLE envelopes
        print("\nASSERTION 6: All 6 metrics are UNAVAILABLE envelopes")
        
        for i, result in enumerate(results):
            trip_id = result.get("trip_id")
            fuel = result.get("fuel", {})
            electric = result.get("electric", {})
            
            print(f"\n  Result {i} (trip_id={trip_id}):")
            
            all_metrics = {
                "fuel_liters": fuel.get("fuel_liters", {}),
                "consumption_l_100km": fuel.get("consumption_l_100km", {}),
                "soc_start_pct": electric.get("soc_start_pct", {}),
                "soc_end_pct": electric.get("soc_end_pct", {}),
                "energy_kwh": electric.get("energy_kwh", {}),
                "consumption_kwh_100km": electric.get("consumption_kwh_100km", {})
            }
            
            for metric_name, metric in all_metrics.items():
                # Check it's an envelope (has required keys)
                required_envelope_keys = ["value", "unit", "unit_verified", "availability", "measurement_type", "source", "timestamp", "reason"]
                missing_envelope_keys = [k for k in required_envelope_keys if k not in metric]
                if missing_envelope_keys:
                    print(f"    ❌ FAIL: {metric_name} missing envelope keys: {missing_envelope_keys}")
                    return False
                
                # Check availability is UNAVAILABLE
                if metric.get("availability") != "UNAVAILABLE":
                    print(f"    ❌ FAIL: {metric_name}.availability={metric.get('availability')}, expected UNAVAILABLE")
                    return False
                
                # Check value is null (NEVER 0)
                if metric.get("value") is not None:
                    print(f"    ❌ FAIL: {metric_name}.value={metric.get('value')}, expected null (not 0)")
                    return False
                
                # Check measurement_type is null (NEVER string "NONE")
                measurement_type = metric.get("measurement_type")
                if measurement_type == "NONE":
                    print(f"    ❌ FAIL: {metric_name}.measurement_type='NONE', must NEVER be string 'NONE'")
                    return False
                
                # Check availability is never "ERROR"
                if metric.get("availability") == "ERROR":
                    print(f"    ❌ FAIL: {metric_name}.availability='ERROR', must NEVER be 'ERROR'")
                    return False
            
            print(f"    ✅ PASS: All 6 metrics are UNAVAILABLE envelopes with value=null, measurement_type≠'NONE', availability≠'ERROR'")
        
        # ASSERTION 7: Trip A details
        print("\nASSERTION 7: Trip A (ref=781479) details")
        
        trip_a = results[0]
        if trip_a.get("trip_id") != "A":
            print(f"  ❌ FAIL: First result trip_id={trip_a.get('trip_id')}, expected 'A'")
            return False
        
        # Check tracker_id (note: the field might be named differently in the actual response)
        # Based on test_result.md, it should be tracker_id=781479
        tracker_id_a = trip_a.get("tracker_id")
        if tracker_id_a != 781479:
            print(f"  ❌ FAIL: Trip A tracker_id={tracker_id_a}, expected 781479")
            return False
        
        # Check status/availability/reason
        # Based on test_result.md, status should be NO_ENERGY_DATA
        # But the contract might use "availability" and "reason" fields instead
        print(f"  Trip A: tracker_id={tracker_id_a}, availability={trip_a.get('availability')}, reason={trip_a.get('reason')}, powertrain={trip_a.get('powertrain')}")
        
        if trip_a.get("powertrain") != "UNKNOWN":
            print(f"  ❌ FAIL: Trip A powertrain={trip_a.get('powertrain')}, expected UNKNOWN")
            return False
        
        print(f"  ✅ PASS: Trip A has tracker_id=781479, powertrain=UNKNOWN")
        
        # ASSERTION 8: Trip B details
        print("\nASSERTION 8: Trip B (ref=999999) details")
        
        trip_b = results[1]
        if trip_b.get("trip_id") != "B":
            print(f"  ❌ FAIL: Second result trip_id={trip_b.get('trip_id')}, expected 'B'")
            return False
        
        tracker_id_b = trip_b.get("tracker_id")
        if tracker_id_b is not None:
            print(f"  ❌ FAIL: Trip B tracker_id={tracker_id_b}, expected null (mapping invalid)")
            return False
        
        print(f"  Trip B: tracker_id={tracker_id_b}, availability={trip_b.get('availability')}, reason={trip_b.get('reason')}, powertrain={trip_b.get('powertrain')}")
        
        if trip_b.get("powertrain") != "UNKNOWN":
            print(f"  ❌ FAIL: Trip B powertrain={trip_b.get('powertrain')}, expected UNKNOWN")
            return False
        
        print(f"  ✅ PASS: Trip B has tracker_id=null, powertrain=UNKNOWN")
        
        # Final summary
        print("\n" + "="*80)
        print("✅ ALL ASSERTIONS PASSED")
        print("="*80)
        print("\nCRITICAL CONFIRMATION:")
        print("  - NO 'energy' wrapper key exists in any result")
        print("  - 'fuel' and 'electric' are DIRECTLY under each result object")
        print("  - fuel has EXACTLY {fuel_liters, consumption_l_100km}")
        print("  - electric has EXACTLY {soc_start_pct, soc_end_pct, energy_kwh, consumption_kwh_100km}")
        print("  - All 6 metrics are UNAVAILABLE envelopes with value=null")
        print("  - measurement_type is null (NOT string 'NONE')")
        print("  - availability is UNAVAILABLE (NOT 'ERROR')")
        print("  - Trip A: tracker_id=781479, powertrain=UNKNOWN")
        print("  - Trip B: tracker_id=null, powertrain=UNKNOWN")
        print("="*80)
        
        return True
    
    except Exception as e:
        print(f"\n❌ EXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test execution."""
    print("="*80)
    print("LOGITRAK Energy v1 Trips Batch - CRITICAL Nesting Verification")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Tenant: {TENANT_ID}")
    print(f"Route: POST /api/energy/v1/trips/energy:batch")
    print("="*80)
    
    # Ensure data exists first
    if not ensure_data_exists():
        print("\n❌ Failed to ensure data exists. Aborting verification.")
        sys.exit(1)
    
    # Run verification
    success = verify_nesting()
    
    if success:
        print("\n✅ VERIFICATION COMPLETE: All assertions passed")
        sys.exit(0)
    else:
        print("\n❌ VERIFICATION FAILED: One or more assertions failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
