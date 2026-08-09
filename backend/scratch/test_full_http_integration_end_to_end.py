"""Integration test running full end-to-end API pipeline via FastAPI TestClient."""

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from api.main import app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("http_integration_test")

SAMPLE_DRAFT_TEXT = """
महाराष्ट्र शासन
उच्च व तंत्र शिक्षण विभाग
प्रस्तावना:
राज्यातील शासकीय व बिगर शासकीय अनुदानित महाविद्यालयांमधील अराखीव प्रवर्गातील (EWS/SEBC) विद्यार्थ्यांच्या शैक्षणिक शुल्कात सवलत देण्याची बाब शासनाच्या विचाराधीन होती.

शासन निर्णय:
१. राज्यातील सर्व मान्यताप्राप्त शासकीय महाविद्यालयात अराखीव प्रवर्गातील विद्यार्थ्यांना ५०% शिक्षण शुल्क माफी लागू राहील.
२. पालकांचे वार्षिक उत्पन्न मर्यादा रुपये ८.०० लाख (रुपये आठ लाख) पेक्षा जास्त नसावे.
३. या योजनेचा लाभ घेण्यासाठी विद्यार्थ्याने महाडीबीटी (MahaDBT) पोर्टलवर ऑनलाईन अर्ज करणे बंधनकारक राहील.
४. सदर शासन निर्णय निर्गमित झाल्याच्या दिनांकापासून लागू राहील.

महाराष्ट्राचे राज्यपाल यांच्या आदेशानुसार व नावाने,
(संजय देशमुख)
सह सचिव, महाराष्ट्र शासन.
"""

def test_full_http_integration():
    client = TestClient(app)

    logger.info("=== STEP 1: Testing GET /health Endpoint ===")
    res_health = client.get("/health")
    assert res_health.status_code == 200, f"Health check failed: {res_health.text}"
    health_data = res_health.json()
    assert health_data.get("status") in ("ok", "degraded"), f"Unexpected health status: {health_data}"
    logger.info(f"Step 1 Passed! Health Status: {health_data.get('status')}, Postgres DB: {health_data.get('db')}")

    logger.info("=== STEP 2: Testing POST /drafts Endpoint ===")
    res_create = client.post("/drafts", json={
        "filename": "http_pipeline_test.txt",
        "full_text": SAMPLE_DRAFT_TEXT,
    })
    assert res_create.status_code == 200, f"Create draft failed: {res_create.text}"

    draft_data = res_create.json()
    draft_id = draft_data["id"]
    assert draft_id is not None, "Created draft ID is None"
    logger.info(f"Step 2 Passed! Created Draft ID: {draft_id}, Version: {draft_data.get('version_number')}")

    logger.info("=== STEP 3: Testing POST /reasoning/analyze Endpoint ===")
    res_analyze = client.post("/reasoning/analyze", json={
        "draft_text": SAMPLE_DRAFT_TEXT,
        "top_k": 5,
    })
    assert res_analyze.status_code == 200, f"Analyze draft failed: {res_analyze.text}"

    analyze_data = res_analyze.json()
    assert "conflict_check" in analyze_data, "Missing conflict_check in analysis"
    assert "template_check" in analyze_data, "Missing template_check in analysis"
    assert "glossary_check" in analyze_data, "Missing glossary_check in analysis"
    logger.info(f"Step 3 Passed! Conflict status: {analyze_data['conflict_check']['status']}, Template score: {analyze_data['template_check']['accuracy_score']}%")

    logger.info("=== STEP 4: Testing POST /drafts/{id}/save-and-recheck Endpoint ===")
    MODIFIED_TEXT = SAMPLE_DRAFT_TEXT.replace("८.०० लाख", "१०.०० लाख")
    res_recheck = client.post(f"/drafts/{draft_id}/save-and-recheck", json={
        "full_text": MODIFIED_TEXT,
        "actor": "Drafting Officer Sanjay Deshmukh",
    })
    assert res_recheck.status_code == 200, f"Save and recheck failed: {res_recheck.text}"
    recheck_data = res_recheck.json()
    assert "clause_diff" in recheck_data, "Missing clause_diff in recheck response"
    diff = recheck_data["clause_diff"]
    logger.info(f"Step 4 Passed! Rechecked Version: {recheck_data['draft']['version_number']}, Diff added={len(diff['added'])}, modified={len(diff['modified'])}, unchanged={len(diff['unchanged'])}")

    logger.info("=== STEP 5: Testing POST /drafts/{id}/share with Department ===")
    res_share = client.post(f"/drafts/{draft_id}/share?user_name=Officer%20Deshmukh")
    assert res_share.status_code == 200, f"Share draft failed: {res_share.text}"

    res_forum = client.get("/forum/in-progress")
    assert res_forum.status_code == 200, f"Get forum in-progress failed: {res_forum.text}"
    forum_list = res_forum.json()
    assert any(item["id"] == draft_id for item in forum_list), "Shared draft not found in forum in-progress list"
    logger.info(f"Step 5 Passed! Draft #{draft_id} present in active Department Forum feed.")

    logger.info("=== STEP 6: Testing Q&A Question & Answer Threading ===")
    res_question = client.post(f"/forum/{draft_id}/comments", json={
        "user_name": "Anjali Kulkarni",
        "user_role": "Desk Officer",
        "user_department": "Education Dept",
        "comment_type": "question",
        "content": "Is the 10 Lakh income limit applicable for academic year 2026-27?",
    })
    assert res_question.status_code == 201, f"Post question failed: {res_question.text}"
    q_data = res_question.json()
    q_id = q_data["id"]

    res_answer = client.post(f"/forum/{draft_id}/comments", json={
        "parent_id": q_id,
        "user_name": "Sanjay Deshmukh",
        "user_role": "Drafting Officer",
        "user_department": "Higher Education Dept",
        "comment_type": "answer",
        "content": "Yes, Section 2 applies from the date of publication.",
    })
    assert res_answer.status_code == 201, f"Post answer failed: {res_answer.text}"
    a_data = res_answer.json()
    assert a_data["parent_id"] == q_id, "Answer parent_id mismatch"

    res_detail = client.get(f"/forum/{draft_id}")
    assert res_detail.status_code == 200, f"Get shared GR detail failed: {res_detail.text}"
    detail_data = res_detail.json()
    comments = detail_data["comments"]
    assert len(comments) >= 2, "Expected at least 2 comments"
    logger.info(f"Step 6 Passed! Q&A Thread verified with question #{q_id} and nested answer #{a_data['id']}.")

    logger.info("=== STEP 7: Testing POST /drafts/{id}/finalize & Auto-Unshare ===")
    res_finalize = client.post(f"/drafts/{draft_id}/finalize")
    assert res_finalize.status_code == 200, f"Finalize draft failed: {res_finalize.text}"

    res_forum_after = client.get("/forum/in-progress")
    forum_list_after = res_forum_after.json()
    assert not any(item["id"] == draft_id for item in forum_list_after), "Finalized GR was not removed from forum"
    logger.info("Step 7 Passed! Finalized GR auto-unshared from active forum.")

    logger.info("🎉 FULL END-TO-END HTTP INTEGRATION TEST PASSED 100% WITH ZERO ERRORS!")

if __name__ == "__main__":
    test_full_http_integration()
