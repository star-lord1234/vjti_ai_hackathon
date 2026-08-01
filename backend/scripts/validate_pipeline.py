#!/usr/bin/env python3
"""
Pipeline Validation Harness (Backend In-Process vs HTTP Endpoint)

Validates that for given draft GR fixture files:
1. Direct in-process call (`reasoning.llm_reasoner.check_conflict`) produces consistent
   ConflictFinding outputs when compared against `POST /reasoning/conflict`.
2. Input text integrity (SHA-256 hash) is tracked.
3. Differences between non-deterministic LLM runs are evaluated with fuzzy/semantic rules
   (exact match for `conflicting` boolean, fuzzy match for explanations).

Saves backend execution results to `backend/scripts/fixtures_backend_output.json`.
Returns exit code 0 if all fixtures pass validation, or 1 if any critical mismatch occurs.
"""

import sys
import os
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, Any

# Ensure backend root is in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import httpx
from reasoning.llm_reasoner import check_conflict

FIXTURES_DIR = SCRIPT_DIR / "fixtures"
OUTPUT_FILE = SCRIPT_DIR / "fixtures_backend_output.json"
API_ENDPOINT = "http://localhost:8000/reasoning/conflict"


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compare_results(direct: Dict[str, Any], http: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare field-by-field between direct in-process result and HTTP API result.
    Note: LLM calls are non-deterministic; explanation texts may vary slightly,
    but boolean status and affected GRs should be consistent.
    """
    # 1. Conflicting boolean: Must be exact match
    conflicting_match = direct.get("conflicting") == http.get("conflicting")

    # 2. Confidence: Must be within 0.45 tolerance
    conf_diff = abs(float(direct.get("confidence", 0)) - float(http.get("confidence", 0)))
    confidence_match = conf_diff <= 0.45

    # 3. Affected GRs: Check for overlap in GR canonical numbers or labels
    direct_grs = {g.get("gr_number_canonical") or g.get("label") for g in direct.get("affected_grs", [])}
    http_grs = {g.get("gr_number_canonical") or g.get("label") for g in http.get("affected_grs", [])}
    # Match if both are empty or if there is any intersection
    if not direct_grs and not http_grs:
        grs_match = True
    else:
        grs_match = len(direct_grs.intersection(http_grs)) > 0 or direct_grs == http_grs

    # 4. Explanation: Fuzzy check (both non-empty and length within 3x of each other)
    d_exp = direct.get("explanation", "").strip()
    h_exp = http.get("explanation", "").strip()
    if not d_exp and not h_exp:
        explanation_match = True
    elif d_exp and h_exp:
        len_ratio = len(d_exp) / max(len(h_exp), 1)
        explanation_match = 0.25 <= len_ratio <= 4.0
    else:
        explanation_match = False

    # 5. Conflicting Clauses: Count difference check
    d_clauses = direct.get("conflicting_clauses", [])
    h_clauses = http.get("conflicting_clauses", [])
    clauses_match = abs(len(d_clauses) - len(h_clauses)) <= 3

    overall_pass = conflicting_match and confidence_match and (grs_match or not direct.get("conflicting"))

    return {
        "overall_pass": overall_pass,
        "fields": {
            "conflicting": {"pass": conflicting_match, "direct": direct.get("conflicting"), "http": http.get("conflicting")},
            "confidence": {"pass": confidence_match, "direct": direct.get("confidence"), "http": http.get("confidence")},
            "affected_grs": {"pass": grs_match, "direct_count": len(direct_grs), "http_count": len(http_grs)},
            "explanation": {"pass": explanation_match, "direct_len": len(d_exp), "http_len": len(h_exp)},
            "conflicting_clauses": {"pass": clauses_match, "direct_count": len(d_clauses), "http_count": len(h_clauses)},
        },
    }


def main():
    print("=" * 80)
    print("BACKEND PIPELINE VALIDATION HARNESS")
    print(f"Target API Endpoint: {API_ENDPOINT}")
    print("=" * 80)

    # Verify HTTP backend is reachable first
    try:
        health_res = httpx.get("http://localhost:8000/health", timeout=5.0)
        if health_res.status_code != 200:
            print(f"[ERROR] Backend health check returned status {health_res.status_code}")
            sys.exit(1)
        print("[OK] FastAPI backend is live and healthy.\n")
    except Exception as e:
        print(f"[ERROR] Cannot connect to FastAPI backend at http://localhost:8000: {e}")
        print("Please start uvicorn server: 'uvicorn api.main:app --reload --host 0.0.0.0 --port 8000'")
        sys.exit(1)

    fixture_files = sorted(list(FIXTURES_DIR.glob("*.txt")))
    if not fixture_files:
        print(f"[ERROR] No fixture files found in {FIXTURES_DIR}")
        sys.exit(1)

    recorded_outputs = {}
    all_passed = True

    print(f"{'FIXTURE NAME':<30} | {'HASH (SHA256)':<12} | {'DIRECT (MS)':<11} | {'HTTP (MS)':<9} | {'STATUS'}")
    print("-" * 80)

    for fix_path in fixture_files:
        fix_name = fix_path.name
        text = fix_path.read_text(encoding="utf-8")
        text_hash = compute_sha256(text)
        short_hash = text_hash[:12]

        # 1. In-process direct call
        t0 = time.time()
        try:
            direct_obj = check_conflict(text)
            direct_dict = direct_obj.model_dump()
            direct_ms = (time.time() - t0) * 1000
        except Exception as e:
            print(f"[FAIL] Direct call error on {fix_name}: {e}")
            all_passed = False
            continue

        # 2. HTTP API call
        t1 = time.time()
        try:
            http_res = httpx.post(API_ENDPOINT, json={"draft_text": text}, timeout=60.0)
            http_ms = (time.time() - t1) * 1000
            if http_res.status_code != 200:
                print(f"[FAIL] HTTP error {http_res.status_code} on {fix_name}: {http_res.text}")
                all_passed = False
                continue
            http_dict = http_res.json()
        except Exception as e:
            print(f"[FAIL] HTTP request exception on {fix_name}: {e}")
            all_passed = False
            continue

        # 3. Field diff & fuzzy validation
        diff_res = compare_results(direct_dict, http_dict)
        status_str = "PASS" if diff_res["overall_pass"] else "FAIL"

        if not diff_res["overall_pass"]:
            all_passed = False

        print(f"{fix_name:<30} | {short_hash:<12} | {direct_ms:<11.1f} | {http_ms:<9.1f} | {status_str}")

        recorded_outputs[fix_name] = {
            "fixture_name": fix_name,
            "sha256": text_hash,
            "text_length": len(text),
            "timestamp": time.time(),
            "direct_latency_ms": round(direct_ms, 2),
            "http_latency_ms": round(http_ms, 2),
            "direct_response": direct_dict,
            "http_response": http_dict,
            "field_diff": diff_res,
        }

    # Save outputs for comparison script
    OUTPUT_FILE.write_text(json.dumps(recorded_outputs, indent=2), encoding="utf-8")
    print("-" * 80)
    print(f"Backend output recorded to: {OUTPUT_FILE}")

    if all_passed:
        print("\n>>> ALL FIXTURES PASSED BACKEND PIPELINE VALIDATION <<<\n")
        sys.exit(0)
    else:
        print("\n>>> CRITICAL MISMATCH DETECTED IN BACKEND PIPELINE <<< \n")
        sys.exit(1)


if __name__ == "__main__":
    main()
