#!/usr/bin/env python3
"""
Pipeline Validation Harness (Backend In-Process vs HTTP Endpoint)

Validates that for given draft GR fixture files:
1. Direct in-process call (`reasoning.llm_reasoner.check_conflict`) produces consistent
   ConflictFinding outputs when compared against `POST /reasoning/conflict`.
2. Input text integrity (SHA-256 hash) is tracked.
3. Differences between non-deterministic LLM runs are evaluated with tighter rules.

Saves backend execution results to `backend/scripts/fixtures_backend_output.json`.
Returns exit code 0 if all fixtures pass validation, or 1 if any critical mismatch occurs.
"""

import sys
import os
import json
import time
import hashlib
import re
from pathlib import Path
from typing import Dict, Any, Set

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

# Tighter tolerances than earlier harness (see planning.txt §6)
CONFIDENCE_TOLERANCE = float(os.getenv("VALIDATE_CONFIDENCE_TOLERANCE", "0.20"))
CLAUSE_COUNT_TOLERANCE = int(os.getenv("VALIDATE_CLAUSE_COUNT_TOLERANCE", "1"))
EXPLANATION_LEN_MIN_RATIO = float(os.getenv("VALIDATE_EXPLANATION_MIN_RATIO", "0.5"))
EXPLANATION_LEN_MAX_RATIO = float(os.getenv("VALIDATE_EXPLANATION_MAX_RATIO", "2.0"))
EXPLANATION_TOKEN_OVERLAP_MIN = float(
    os.getenv("VALIDATE_EXPLANATION_TOKEN_OVERLAP", "0.12")
)


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _token_set(text: str) -> Set[str]:
    return {
        t
        for t in re.split(r"\W+", text.lower())
        if len(t) >= 3
    }


def _token_overlap_ratio(a: str, b: str) -> float:
    ta, tb = _token_set(a), _token_set(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def compare_results(direct: Dict[str, Any], http: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare field-by-field between direct in-process result and HTTP API result.
    """
    conflicting_match = direct.get("conflicting") == http.get("conflicting")

    conf_diff = abs(float(direct.get("confidence", 0)) - float(http.get("confidence", 0)))
    confidence_match = conf_diff <= CONFIDENCE_TOLERANCE

    direct_grs = {
        g.get("gr_number_canonical") or g.get("label")
        for g in direct.get("affected_grs", [])
        if g.get("gr_number_canonical") or g.get("label")
    }
    http_grs = {
        g.get("gr_number_canonical") or g.get("label")
        for g in http.get("affected_grs", [])
        if g.get("gr_number_canonical") or g.get("label")
    }

    if not direct_grs and not http_grs:
        grs_match = True
    elif direct.get("conflicting") or http.get("conflicting"):
        grs_match = len(direct_grs.intersection(http_grs)) > 0
    else:
        grs_match = direct_grs == http_grs

    d_exp = direct.get("explanation", "").strip()
    h_exp = http.get("explanation", "").strip()
    if not d_exp and not h_exp:
        explanation_match = True
    elif d_exp and h_exp:
        len_ratio = len(d_exp) / max(len(h_exp), 1)
        overlap = _token_overlap_ratio(d_exp, h_exp)
        explanation_match = (
            EXPLANATION_LEN_MIN_RATIO <= len_ratio <= EXPLANATION_LEN_MAX_RATIO
            or overlap >= EXPLANATION_TOKEN_OVERLAP_MIN
        )
    else:
        explanation_match = False

    d_clauses = direct.get("conflicting_clauses", [])
    h_clauses = http.get("conflicting_clauses", [])
    clauses_match = abs(len(d_clauses) - len(h_clauses)) <= CLAUSE_COUNT_TOLERANCE

    # When either path reports conflict, require GR overlap and clause parity
    if direct.get("conflicting") or http.get("conflicting"):
        overall_pass = (
            conflicting_match
            and confidence_match
            and grs_match
            and clauses_match
            and explanation_match
        )
    else:
        overall_pass = conflicting_match and confidence_match

    return {
        "overall_pass": overall_pass,
        "fields": {
            "conflicting": {
                "pass": conflicting_match,
                "direct": direct.get("conflicting"),
                "http": http.get("conflicting"),
            },
            "confidence": {
                "pass": confidence_match,
                "direct": direct.get("confidence"),
                "http": http.get("confidence"),
                "diff": round(conf_diff, 4),
            },
            "affected_grs": {
                "pass": grs_match,
                "direct_count": len(direct_grs),
                "http_count": len(http_grs),
            },
            "explanation": {
                "pass": explanation_match,
                "direct_len": len(d_exp),
                "http_len": len(h_exp),
                "token_overlap": round(_token_overlap_ratio(d_exp, h_exp), 4),
            },
            "conflicting_clauses": {
                "pass": clauses_match,
                "direct_count": len(d_clauses),
                "http_count": len(h_clauses),
            },
        },
    }


def main():
    print("=" * 80)
    print("BACKEND PIPELINE VALIDATION HARNESS")
    print(f"Target API Endpoint: {API_ENDPOINT}")
    print(
        f"Tolerances: confidence±{CONFIDENCE_TOLERANCE}, "
        f"clauses±{CLAUSE_COUNT_TOLERANCE}, "
        f"explanation len [{EXPLANATION_LEN_MIN_RATIO},{EXPLANATION_LEN_MAX_RATIO}] "
        f"or token overlap ≥{EXPLANATION_TOKEN_OVERLAP_MIN}"
    )
    print("=" * 80)

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

    fixture_files = sorted(
        p for p in FIXTURES_DIR.glob("*.txt") if p.name != "golden_retrieval.json"
    )
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

        t0 = time.time()
        try:
            direct_obj = check_conflict(text)
            direct_dict = direct_obj.model_dump()
            direct_ms = (time.time() - t0) * 1000
        except Exception as e:
            print(f"[FAIL] Direct call error on {fix_name}: {e}")
            all_passed = False
            continue

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
