#!/usr/bin/env python3
"""
CONTRACT-COMPLIANCE verification of LOGITRAK Energy v1 (Journal-facing).
Tests the ACTUALLY-SERIALIZED JSON against the exact contract requirements.
"""
import os
import sys
import time
import json
import requests
from typing import Dict, Any, List, Optional

# Configuration
BASE_URL = "https://energy-telemetry-1.preview.emergentagent.com"
VALID_TOKEN = "3N5HmYTEbKf58YXgAM7LkTAzmVNa6nhBkO761jNhp_cSZsw7OuyH1M4OXSnf_QBM"
TENANT_ID = "paas_13588"

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


# ============================================================================
# SECTION 1: TRIPS BATCH EXACT FIELD NAMES
# ============================================================================

def test_1_trips_batch_exact_fields():
    """
    POST /api/energy/v1/trips/energy:batch with 2 trips (1 valid, 1 invalid).
    Verify EXACT field names in fuel and electric objects.
    """
    section = "1. TRIPS BATCH"
    test_name = "Exact field names in fuel and electric objects"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
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
        results = data.get("results", [])
        
        if len(results) != 2:
            log_test(section, test_name, False, f"Expected 2 results, got {len(results)}")
            return
        
        # Check Trip A
        trip_a = results[0]
        
        # Verify fuel object has EXACTLY these keys
        fuel = trip_a.get("fuel", {})
        expected_fuel_keys = {"fuel_liters", "consumption_l_100km"}
        actual_fuel_keys = set(fuel.keys())
        
        if actual_fuel_keys != expected_fuel_keys:
            log_test(section, test_name, False, 
                    f"Trip A fuel keys: {actual_fuel_keys}, expected: {expected_fuel_keys}")
            return
        
        # Verify electric object has EXACTLY these keys
        electric = trip_a.get("electric", {})
        expected_electric_keys = {"soc_start_pct", "soc_end_pct", "energy_kwh", "consumption_kwh_100km"}
        actual_electric_keys = set(electric.keys())
        
        if actual_electric_keys != expected_electric_keys:
            log_test(section, test_name, False, 
                    f"Trip A electric keys: {actual_electric_keys}, expected: {expected_electric_keys}")
            return
        
        # Verify all 6 values are metric envelopes with UNAVAILABLE and value=null
        all_metrics = {**fuel, **electric}
        for key, metric in all_metrics.items():
            if not isinstance(metric, dict):
                log_test(section, test_name, False, f"Trip A {key} is not a metric envelope: {metric}")
                return
            
            # Check required envelope fields
            required_fields = {"value", "unit", "unit_verified", "availability", 
                             "measurement_type", "source", "timestamp", "reason"}
            if not required_fields.issubset(metric.keys()):
                log_test(section, test_name, False, 
                        f"Trip A {key} missing envelope fields: {metric.keys()}")
                return
            
            # All should be UNAVAILABLE with value=null
            if metric.get("availability") != "UNAVAILABLE":
                log_test(section, test_name, False, 
                        f"Trip A {key}.availability={metric.get('availability')}, expected UNAVAILABLE")
                return
            
            if metric.get("value") is not None:
                log_test(section, test_name, False, 
                        f"Trip A {key}.value={metric.get('value')}, expected null")
                return
            
            # measurement_type must be null (NOT "NONE")
            if metric.get("measurement_type") is not None:
                log_test(section, test_name, False, 
                        f"Trip A {key}.measurement_type={metric.get('measurement_type')}, expected null")
                return
        
        # Verify Trip A status and tracker_id
        if trip_a.get("status") != "NO_ENERGY_DATA":
            log_test(section, test_name, False, 
                    f"Trip A status={trip_a.get('status')}, expected NO_ENERGY_DATA")
            return
        
        if trip_a.get("tracker_id") != 781479:
            log_test(section, test_name, False, 
                    f"Trip A tracker_id={trip_a.get('tracker_id')}, expected 781479")
            return
        
        if trip_a.get("powertrain") != "UNKNOWN":
            log_test(section, test_name, False, 
                    f"Trip A powertrain={trip_a.get('powertrain')}, expected UNKNOWN")
            return
        
        # Check Trip B
        trip_b = results[1]
        
        # Verify fuel and electric objects exist with same keys
        fuel_b = trip_b.get("fuel", {})
        electric_b = trip_b.get("electric", {})
        
        if set(fuel_b.keys()) != expected_fuel_keys:
            log_test(section, test_name, False, 
                    f"Trip B fuel keys: {set(fuel_b.keys())}, expected: {expected_fuel_keys}")
            return
        
        if set(electric_b.keys()) != expected_electric_keys:
            log_test(section, test_name, False, 
                    f"Trip B electric keys: {set(electric_b.keys())}, expected: {expected_electric_keys}")
            return
        
        # Verify Trip B status and tracker_id
        if trip_b.get("status") != "MAPPING_INVALID":
            log_test(section, test_name, False, 
                    f"Trip B status={trip_b.get('status')}, expected MAPPING_INVALID")
            return
        
        if trip_b.get("tracker_id") is not None:
            log_test(section, test_name, False, 
                    f"Trip B tracker_id={trip_b.get('tracker_id')}, expected null")
            return
        
        if trip_b.get("powertrain") != "UNKNOWN":
            log_test(section, test_name, False, 
                    f"Trip B powertrain={trip_b.get('powertrain')}, expected UNKNOWN")
            return
        
        # Verify litres and kWh are in SEPARATE objects (never merged)
        response_str = json.dumps(data)
        if "fuel_kwh" in response_str or "energy_l" in response_str or "electric_liters" in response_str:
            log_test(section, test_name, False, "Litres and kWh are merged (not separate)")
            return
        
        log_test(section, test_name, True, 
                f"Trip A: fuel keys={expected_fuel_keys}, electric keys={expected_electric_keys}, "
                f"all UNAVAILABLE/null, status=NO_ENERGY_DATA, tracker_id=781479. "
                f"Trip B: status=MAPPING_INVALID, tracker_id=null. Both powertrain=UNKNOWN.")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


# ============================================================================
# SECTION 2: FLEET SUMMARY EXACT 6 METRICS
# ============================================================================

def test_2_fleet_summary_exact_metrics():
    """
    GET /api/energy/v1/fleet/summary?tenant_id=paas_13588
    Verify metrics object has EXACTLY 6 keys.
    """
    section = "2. FLEET SUMMARY"
    test_name = "Exact 6 metrics in metrics object"
    
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
        metrics = data.get("metrics", {})
        
        # Verify EXACTLY these 6 keys
        expected_keys = {
            "thermal_consumption_l_100km",
            "electric_consumption_kwh_100km",
            "fuel_liters_total",
            "electric_kwh_total",
            "obd_coverage_pct",
            "vehicles_with_data"
        }
        actual_keys = set(metrics.keys())
        
        if actual_keys != expected_keys:
            log_test(section, test_name, False, 
                    f"Metrics keys: {actual_keys}, expected: {expected_keys}")
            return
        
        # Verify each is a metric envelope
        for key, metric in metrics.items():
            if not isinstance(metric, dict):
                log_test(section, test_name, False, f"{key} is not a metric envelope: {metric}")
                return
            
            required_fields = {"value", "unit", "unit_verified", "availability", 
                             "measurement_type", "source", "timestamp", "reason"}
            if not required_fields.issubset(metric.keys()):
                log_test(section, test_name, False, 
                        f"{key} missing envelope fields: {metric.keys()}")
                return
        
        # Verify obd_coverage_pct
        obd_cov = metrics.get("obd_coverage_pct", {})
        if obd_cov.get("availability") != "AVAILABLE":
            log_test(section, test_name, False, 
                    f"obd_coverage_pct.availability={obd_cov.get('availability')}, expected AVAILABLE")
            return
        
        if obd_cov.get("measurement_type") != "ESTIMATED":
            log_test(section, test_name, False, 
                    f"obd_coverage_pct.measurement_type={obd_cov.get('measurement_type')}, expected ESTIMATED")
            return
        
        if obd_cov.get("source") != "CALCULATED":
            log_test(section, test_name, False, 
                    f"obd_coverage_pct.source={obd_cov.get('source')}, expected CALCULATED")
            return
        
        if obd_cov.get("unit") != "%":
            log_test(section, test_name, False, 
                    f"obd_coverage_pct.unit={obd_cov.get('unit')}, expected %")
            return
        
        if not isinstance(obd_cov.get("value"), (int, float)) or obd_cov.get("value") is None:
            log_test(section, test_name, False, 
                    f"obd_coverage_pct.value={obd_cov.get('value')}, expected a number (not null)")
            return
        
        # Verify vehicles_with_data
        veh_data = metrics.get("vehicles_with_data", {})
        if veh_data.get("availability") != "AVAILABLE":
            log_test(section, test_name, False, 
                    f"vehicles_with_data.availability={veh_data.get('availability')}, expected AVAILABLE")
            return
        
        if not isinstance(veh_data.get("value"), int):
            log_test(section, test_name, False, 
                    f"vehicles_with_data.value={veh_data.get('value')}, expected an integer")
            return
        
        # Verify thermal_consumption_l_100km, electric_consumption_kwh_100km, 
        # fuel_liters_total, electric_kwh_total are UNAVAILABLE with value=null
        unavailable_keys = [
            "thermal_consumption_l_100km",
            "electric_consumption_kwh_100km",
            "fuel_liters_total",
            "electric_kwh_total"
        ]
        
        for key in unavailable_keys:
            metric = metrics.get(key, {})
            if metric.get("availability") != "UNAVAILABLE":
                log_test(section, test_name, False, 
                        f"{key}.availability={metric.get('availability')}, expected UNAVAILABLE")
                return
            
            if metric.get("value") is not None:
                log_test(section, test_name, False, 
                        f"{key}.value={metric.get('value')}, expected null (NOT 0)")
                return
            
            # measurement_type must be null (NOT "NONE")
            if metric.get("measurement_type") is not None:
                log_test(section, test_name, False, 
                        f"{key}.measurement_type={metric.get('measurement_type')}, expected null")
                return
        
        # Verify litres and kWh are NOT summed into one field
        response_str = json.dumps(data)
        if "total_energy" in response_str or "combined_fuel" in response_str:
            log_test(section, test_name, False, "Litres and kWh are summed into one field")
            return
        
        log_test(section, test_name, True, 
                f"Metrics keys: {expected_keys}. "
                f"obd_coverage_pct: AVAILABLE/ESTIMATED/CALCULATED/{obd_cov.get('unit')}/{obd_cov.get('value')}. "
                f"vehicles_with_data: AVAILABLE/{veh_data.get('value')}. "
                f"thermal/electric/fuel/electric_kwh: UNAVAILABLE/null.")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


# ============================================================================
# SECTION 3: VEHICLE SUMMARY EXACT 2 METRICS
# ============================================================================

def test_3_vehicle_summary_exact_metrics():
    """
    GET /api/energy/v1/vehicles/781479/summary?tenant_id=paas_13588
    Verify metrics object has EXACTLY 2 keys.
    """
    section = "3. VEHICLE SUMMARY"
    test_name = "Exact 2 metrics in metrics object"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/781479/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Expected 200, got {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        metrics = data.get("metrics", {})
        
        # Verify EXACTLY these 2 keys
        expected_keys = {"fuel_liters_total", "energy_kwh_total"}
        actual_keys = set(metrics.keys())
        
        if actual_keys != expected_keys:
            log_test(section, test_name, False, 
                    f"Metrics keys: {actual_keys}, expected: {expected_keys}")
            return
        
        # Verify fuel_liters_total
        fuel = metrics.get("fuel_liters_total", {})
        
        # Check value is approximately 28.0
        fuel_value = fuel.get("value")
        if fuel_value is None or not (27 < fuel_value < 29):
            log_test(section, test_name, False, 
                    f"fuel_liters_total.value={fuel_value}, expected ≈28.0")
            return
        
        if fuel.get("unit") != "L":
            log_test(section, test_name, False, 
                    f"fuel_liters_total.unit={fuel.get('unit')}, expected L")
            return
        
        if fuel.get("availability") != "STALE":
            log_test(section, test_name, False, 
                    f"fuel_liters_total.availability={fuel.get('availability')}, expected STALE")
            return
        
        if fuel.get("measurement_type") != "MEASURED":
            log_test(section, test_name, False, 
                    f"fuel_liters_total.measurement_type={fuel.get('measurement_type')}, expected MEASURED")
            return
        
        if fuel.get("source") != "NAVIXY_CAN":
            log_test(section, test_name, False, 
                    f"fuel_liters_total.source={fuel.get('source')}, expected NAVIXY_CAN")
            return
        
        # Verify energy_kwh_total
        energy = metrics.get("energy_kwh_total", {})
        
        if energy.get("availability") != "UNAVAILABLE":
            log_test(section, test_name, False, 
                    f"energy_kwh_total.availability={energy.get('availability')}, expected UNAVAILABLE")
            return
        
        if energy.get("value") is not None:
            log_test(section, test_name, False, 
                    f"energy_kwh_total.value={energy.get('value')}, expected null")
            return
        
        # measurement_type must be null (NOT "NONE")
        if energy.get("measurement_type") is not None:
            log_test(section, test_name, False, 
                    f"energy_kwh_total.measurement_type={energy.get('measurement_type')}, expected null")
            return
        
        log_test(section, test_name, True, 
                f"Metrics keys: {expected_keys}. "
                f"fuel_liters_total: value≈{fuel_value:.1f}, unit=L, availability=STALE, "
                f"measurement_type=MEASURED, source=NAVIXY_CAN. "
                f"energy_kwh_total: UNAVAILABLE/null.")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


# ============================================================================
# SECTION 4: TENANT STRICT
# ============================================================================

def test_4a_tenant_mismatch_batch():
    """4a. Batch: body tenant_id=paas_13588 AND header X-Tenant-Id: paas_OTHER -> 400."""
    section = "4. TENANT STRICT"
    test_name = "4a. Batch tenant mismatch (400)"
    
    try:
        headers = {
            "Authorization": f"Bearer {VALID_TOKEN}",
            "X-Tenant-Id": "paas_OTHER"
        }
        payload = {
            "tenant_id": TENANT_ID,
            "trips": [{"trip_id": "X", "ref": 781479, "start": "2026-08-18T08:00:00Z", "end": "2026-08-18T08:40:00Z"}]
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
        
        log_test(section, test_name, True, "Batch tenant mismatch returns 400")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_4b_tenant_mismatch_fleet():
    """4b. Fleet: query tenant_id=paas_13588 AND header X-Tenant-Id: paas_OTHER -> 400."""
    section = "4. TENANT STRICT"
    test_name = "4b. Fleet tenant mismatch (400)"
    
    try:
        headers = {
            "Authorization": f"Bearer {VALID_TOKEN}",
            "X-Tenant-Id": "paas_OTHER"
        }
        
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/fleet/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 400:
            log_test(section, test_name, False, f"Expected 400, got {resp.status_code}: {resp.text}")
            return
        
        log_test(section, test_name, True, "Fleet tenant mismatch returns 400")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_4c_tenant_mismatch_vehicle():
    """4c. Vehicle: query tenant_id=paas_13588 AND header X-Tenant-Id: paas_OTHER -> 400."""
    section = "4. TENANT STRICT"
    test_name = "4c. Vehicle tenant mismatch (400)"
    
    try:
        headers = {
            "Authorization": f"Bearer {VALID_TOKEN}",
            "X-Tenant-Id": "paas_OTHER"
        }
        
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/781479/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != 400:
            log_test(section, test_name, False, f"Expected 400, got {resp.status_code}: {resp.text}")
            return
        
        log_test(section, test_name, True, "Vehicle tenant mismatch returns 400")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_4d_tenant_matching():
    """4d. Matching both (query/body=paas_13588 AND header=paas_13588) -> 200."""
    section = "4. TENANT STRICT"
    test_name = "4d. Matching tenant (200)"
    
    try:
        headers = {
            "Authorization": f"Bearer {VALID_TOKEN}",
            "X-Tenant-Id": TENANT_ID
        }
        
        # Test batch
        payload = {
            "tenant_id": TENANT_ID,
            "trips": [{"trip_id": "Y", "ref": 781479, "start": "2026-08-18T08:00:00Z", "end": "2026-08-18T08:40:00Z"}]
        }
        resp = requests.post(
            f"{BASE_URL}/api/energy/v1/trips/energy:batch",
            json=payload,
            headers=headers,
            timeout=10
        )
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Batch returned {resp.status_code}, expected 200")
            return
        
        # Test fleet
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/fleet/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Fleet returned {resp.status_code}, expected 200")
            return
        
        log_test(section, test_name, True, "Matching tenant returns 200 for all routes")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_4e_tenant_single_mechanism():
    """4e. Single mechanism only (batch with body tenant only, fleet with query tenant only) -> 200."""
    section = "4. TENANT STRICT"
    test_name = "4e. Single mechanism (200)"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        
        # Batch with body tenant only (no header)
        payload = {
            "tenant_id": TENANT_ID,
            "trips": [{"trip_id": "Z", "ref": 781479, "start": "2026-08-18T08:00:00Z", "end": "2026-08-18T08:40:00Z"}]
        }
        resp = requests.post(
            f"{BASE_URL}/api/energy/v1/trips/energy:batch",
            json=payload,
            headers=headers,
            timeout=10
        )
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Batch with body tenant only returned {resp.status_code}, expected 200")
            return
        
        # Fleet with query tenant only (no header)
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/fleet/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Fleet with query tenant only returned {resp.status_code}, expected 200")
            return
        
        log_test(section, test_name, True, "Single mechanism returns 200 for all routes")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


# ============================================================================
# SECTION 5: HEALTH
# ============================================================================

def test_5a_health_without_token():
    """5a. GET /api/energy/v1/health WITHOUT token -> 200, contract_version=v1, no secret field."""
    section = "5. HEALTH"
    test_name = "5a. Health without token (200)"
    
    try:
        resp = requests.get(f"{BASE_URL}/api/energy/v1/health", timeout=10)
        
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Expected 200, got {resp.status_code}")
            return
        
        data = resp.json()
        
        if data.get("contract_version") != "v1":
            log_test(section, test_name, False, 
                    f"contract_version={data.get('contract_version')}, expected v1")
            return
        
        # Check no secret field
        if any(k in data for k in ["token", "secret", "api_key", "bearer", "ENERGY_API_TOKEN"]):
            log_test(section, test_name, False, "Response contains secret field")
            return
        
        # Check no secret value exposed
        response_str = json.dumps(data)
        if VALID_TOKEN in response_str:
            log_test(section, test_name, False, "Token value exposed in response")
            return
        
        log_test(section, test_name, True, 
                f"contract_version=v1, status={data.get('status')}, no secret field")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_5b_health_with_token():
    """5b. GET /api/energy/v1/health WITH a Bearer token -> still 200 (must not error)."""
    section = "5. HEALTH"
    test_name = "5b. Health with token (200)"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        resp = requests.get(f"{BASE_URL}/api/energy/v1/health", headers=headers, timeout=10)
        
        if resp.status_code != 200:
            log_test(section, test_name, False, f"Expected 200, got {resp.status_code}")
            return
        
        log_test(section, test_name, True, "Health with token returns 200")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


# ============================================================================
# SECTION 6: RULES
# ============================================================================

def test_6a_no_none_measurement_type():
    """6a. Scan ALL responses: confirm 'NONE' never appears as measurement_type."""
    section = "6. RULES"
    test_name = "6a. No 'NONE' measurement_type"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        
        # Collect all responses
        responses = []
        
        # Vehicle summary
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/781479/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            responses.append(("vehicle_summary", resp.json()))
        
        # Fleet summary
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/fleet/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            responses.append(("fleet_summary", resp.json()))
        
        # Trips batch
        payload = {
            "tenant_id": TENANT_ID,
            "trips": [{"trip_id": "TEST", "ref": 781479, "start": "2026-08-18T08:00:00Z", "end": "2026-08-18T08:40:00Z"}]
        }
        resp = requests.post(
            f"{BASE_URL}/api/energy/v1/trips/energy:batch",
            json=payload,
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            responses.append(("trips_batch", resp.json()))
        
        # Scan for "NONE" measurement_type
        for name, data in responses:
            response_str = json.dumps(data)
            if '"measurement_type": "NONE"' in response_str or '"measurement_type":"NONE"' in response_str:
                log_test(section, test_name, False, f"Found measurement_type='NONE' in {name}")
                return
        
        log_test(section, test_name, True, "No 'NONE' measurement_type in any response")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_6b_no_error_availability():
    """6b. Scan ALL responses: confirm 'ERROR' never appears as availability."""
    section = "6. RULES"
    test_name = "6b. No 'ERROR' availability"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        
        # Collect all responses
        responses = []
        
        # Vehicle summary
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/781479/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            responses.append(("vehicle_summary", resp.json()))
        
        # Fleet summary
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/fleet/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            responses.append(("fleet_summary", resp.json()))
        
        # Trips batch
        payload = {
            "tenant_id": TENANT_ID,
            "trips": [{"trip_id": "TEST", "ref": 781479, "start": "2026-08-18T08:00:00Z", "end": "2026-08-18T08:40:00Z"}]
        }
        resp = requests.post(
            f"{BASE_URL}/api/energy/v1/trips/energy:batch",
            json=payload,
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            responses.append(("trips_batch", resp.json()))
        
        # Scan for "ERROR" availability
        for name, data in responses:
            response_str = json.dumps(data)
            if '"availability": "ERROR"' in response_str or '"availability":"ERROR"' in response_str:
                log_test(section, test_name, False, f"Found availability='ERROR' in {name}")
                return
        
        log_test(section, test_name, True, "No 'ERROR' availability in any response")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


def test_6c_null_not_zero():
    """6c. Confirm null != 0 everywhere (UNAVAILABLE => value null)."""
    section = "6. RULES"
    test_name = "6c. null != 0 (UNAVAILABLE)"
    
    try:
        headers = {"Authorization": f"Bearer {VALID_TOKEN}"}
        
        # Vehicle summary
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/vehicles/781479/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            metrics = data.get("metrics", {})
            for key, metric in metrics.items():
                if metric.get("availability") == "UNAVAILABLE" and metric.get("value") == 0:
                    log_test(section, test_name, False, 
                            f"vehicle_summary {key}.value=0 for UNAVAILABLE (should be null)")
                    return
        
        # Fleet summary
        resp = requests.get(
            f"{BASE_URL}/api/energy/v1/fleet/summary",
            params={"tenant_id": TENANT_ID},
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            metrics = data.get("metrics", {})
            for key, metric in metrics.items():
                if metric.get("availability") == "UNAVAILABLE" and metric.get("value") == 0:
                    log_test(section, test_name, False, 
                            f"fleet_summary {key}.value=0 for UNAVAILABLE (should be null)")
                    return
        
        # Trips batch
        payload = {
            "tenant_id": TENANT_ID,
            "trips": [{"trip_id": "TEST", "ref": 781479, "start": "2026-08-18T08:00:00Z", "end": "2026-08-18T08:40:00Z"}]
        }
        resp = requests.post(
            f"{BASE_URL}/api/energy/v1/trips/energy:batch",
            json=payload,
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            for result in data.get("results", []):
                fuel = result.get("fuel", {})
                electric = result.get("electric", {})
                for key, metric in {**fuel, **electric}.items():
                    if metric.get("availability") == "UNAVAILABLE" and metric.get("value") == 0:
                        log_test(section, test_name, False, 
                                f"trips_batch {key}.value=0 for UNAVAILABLE (should be null)")
                        return
        
        log_test(section, test_name, True, "UNAVAILABLE metrics have value=null (never 0)")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


# ============================================================================
# SECTION 7: AUTH REGRESSION
# ============================================================================

def test_7_auth_regression():
    """7. Each v1 data route without token -> 401."""
    section = "7. AUTH REGRESSION"
    test_name = "All v1 data routes require token (401)"
    
    try:
        routes = [
            ("GET", f"{BASE_URL}/api/energy/v1/vehicles/781479/summary?tenant_id={TENANT_ID}", None),
            ("GET", f"{BASE_URL}/api/energy/v1/fleet/summary?tenant_id={TENANT_ID}", None),
            ("POST", f"{BASE_URL}/api/energy/v1/trips/energy:batch", 
             {"tenant_id": TENANT_ID, "trips": []}),
        ]
        
        for method, url, payload in routes:
            if method == "GET":
                resp = requests.get(url, timeout=10)
            else:
                resp = requests.post(url, json=payload, timeout=10)
            
            if resp.status_code != 401:
                log_test(section, test_name, False, 
                        f"{method} {url} returned {resp.status_code}, expected 401")
                return
        
        log_test(section, test_name, True, "All v1 data routes return 401 without token")
    
    except Exception as e:
        log_test(section, test_name, False, f"Exception: {str(e)}")


# ============================================================================
# MAIN
# ============================================================================

def print_summary():
    """Print test summary."""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    total = test_results['passed'] + test_results['failed']
    print(f"Total tests: {total}")
    print(f"✅ Passed: {test_results['passed']}")
    print(f"❌ Failed: {test_results['failed']}")
    if total > 0:
        print(f"Success rate: {test_results['passed'] / total * 100:.1f}%")
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
    """Run all contract compliance tests."""
    print("="*80)
    print("LOGITRAK Energy v1 CONTRACT-COMPLIANCE Test Suite")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Tenant: {TENANT_ID}")
    print("="*80 + "\n")
    
    # Ensure data exists first
    if not ensure_data_exists():
        print("❌ Failed to ensure data exists. Aborting tests.")
        sys.exit(1)
    
    # Run all tests
    print("=== RUNNING CONTRACT COMPLIANCE TESTS ===\n")
    
    # Section 1: TRIPS BATCH EXACT FIELD NAMES
    test_1_trips_batch_exact_fields()
    
    # Section 2: FLEET SUMMARY EXACT 6 METRICS
    test_2_fleet_summary_exact_metrics()
    
    # Section 3: VEHICLE SUMMARY EXACT 2 METRICS
    test_3_vehicle_summary_exact_metrics()
    
    # Section 4: TENANT STRICT
    test_4a_tenant_mismatch_batch()
    test_4b_tenant_mismatch_fleet()
    test_4c_tenant_mismatch_vehicle()
    test_4d_tenant_matching()
    test_4e_tenant_single_mechanism()
    
    # Section 5: HEALTH
    test_5a_health_without_token()
    test_5b_health_with_token()
    
    # Section 6: RULES
    test_6a_no_none_measurement_type()
    test_6b_no_error_availability()
    test_6c_null_not_zero()
    
    # Section 7: AUTH REGRESSION
    test_7_auth_regression()
    
    # Print summary
    print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if test_results['failed'] == 0 else 1)


if __name__ == "__main__":
    main()
