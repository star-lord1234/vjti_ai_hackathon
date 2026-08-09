"""End-to-end full pipeline validation script."""

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.db import Database
from reasoning.llm_reasoner import check_conflict
from reasoning.template.checker import run_template_check
from reasoning.glossary.checker import run_glossary_check
from api.routes.drafts import save_and_recheck, DraftSaveRequest, create_draft, DraftCreateRequest, share_draft_with_department
from api.routes.forum import post_gr_comment, CreateCommentRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pipeline_test")



SAMPLE_GR_TEXT = """
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

def test_full_pipeline():
    logger.info("=== STEP 1: Testing Reasoning Engine & Conflict Analysis ===")
    analysis = check_conflict(SAMPLE_GR_TEXT, top_k=5)
    assert analysis is not None, "Analysis response is None"
    assert hasattr(analysis, "conflicting"), "Analysis missing 'conflicting' boolean"
    assert hasattr(analysis, "affected_grs"), "Analysis missing 'affected_grs'"
    assert hasattr(analysis, "conflicting_clauses"), "Analysis missing 'conflicting_clauses'"
    logger.info(f"Step 1 Passed! Conflicting: {analysis.conflicting}, Affected GRs: {len(analysis.affected_grs)}")


    logger.info("=== STEP 2: Testing Template & Glossary Checker ===")
    template_res = run_template_check(SAMPLE_GR_TEXT)
    assert template_res is not None, "Template check returned None"
    assert hasattr(template_res, "accuracy_score"), "Template check missing accuracy_score"
    logger.info(f"Step 2 Passed! Template Accuracy Score: {template_res.accuracy_score}%, Violations: {len(template_res.violations)}")



    glossary_res = run_glossary_check(SAMPLE_GR_TEXT)
    assert glossary_res is not None, "Glossary check returned None"
    logger.info(f"Step 2 Passed! Glossary findings: {len(glossary_res.findings)}")



    logger.info("=== STEP 3: Testing Draft Document Creation in DB ===")
    db = Database()
    doc_id = None
    try:
        draft = db.create_draft_document(
            filename="full_pipeline_test.txt",
            full_text=SAMPLE_GR_TEXT,
        )
        doc_id = draft if isinstance(draft, int) else draft.get("id")
        assert doc_id is not None, "Created draft ID is None"
        logger.info(f"Step 3 Passed! Draft Document ID: {doc_id}")

        logger.info("=== STEP 4: Testing Save & Incremental Recheck Endpoint ===")
        MODIFIED_TEXT = SAMPLE_GR_TEXT.replace("८.०० लाख", "१०.०० लाख")
        recheck_req = DraftSaveRequest(full_text=MODIFIED_TEXT, actor="Officer Deshmukh")
        recheck_res = save_and_recheck(doc_id, recheck_req)
        assert recheck_res is not None, "Recheck response is None"
        assert recheck_res.draft is not None, "Recheck response missing draft"
        assert recheck_res.clause_diff is not None, "Recheck response missing clause_diff"
        logger.info(f"Step 4 Passed! Clause diff: added={len(recheck_res.clause_diff.added)}, modified={len(recheck_res.clause_diff.modified)}, unchanged={len(recheck_res.clause_diff.unchanged)}")



        logger.info("=== STEP 5: Testing Department Forum Sharing & Q&A ===")
        db.share_draft_with_dept(doc_id, user_name="Sanjay Officer")
        forum_grs = db.get_in_progress_forum_grs()
        assert any(g["id"] == doc_id for g in forum_grs), "Shared GR not found in in-progress forum"

        comment = db.add_gr_comment(
            gr_document_id=doc_id,
            user_name="Anjali Employee",
            user_role="Desk Officer",
            user_department="Education",
            comment_type="question",
            content="Is 10 Lakh income cap approved?",
        )
        assert comment["id"] is not None, "Comment creation failed"
        logger.info("Step 5 Passed! Shared GR in forum and comment posted successfully.")

        logger.info("=== STEP 6: Testing Finalization & Auto-Unshare ===")
        db.finalize_draft(doc_id)
        forum_grs_after = db.get_in_progress_forum_grs()
        assert not any(g["id"] == doc_id for g in forum_grs_after), "Finalized GR was not removed from forum"
        logger.info("Step 6 Passed! Finalized GR auto-unshared successfully.")

        logger.info("🎉 FULL PIPELINE TEST PASSED SUCCESSFULLY 100% WITH ZERO ERRORS!")

    finally:
        if doc_id:
            db.cur.execute("DELETE FROM gr_documents WHERE id = %s", (doc_id,))
            db.conn.commit()
        db.close()

if __name__ == "__main__":
    test_full_pipeline()
