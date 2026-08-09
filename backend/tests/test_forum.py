"""Unit tests for Department Collaboration Forum API endpoints."""

import uuid
from database.db import Database


def test_forum_sharing_and_comments():
    db = Database()
    doc_id = None
    try:
        # Create a test draft
        unique_name = f"test_forum_gr_{uuid.uuid4().hex[:8]}.txt"
        doc_id = db.create_draft_document(
            filename=unique_name,
            full_text="१. अराखीव प्रवर्गातील विद्यार्थ्यांना ५०% शुल्क माफी.",
        )



        # 1. Initially should not be in in-progress forum
        in_progress_before = db.get_in_progress_forum_grs()
        before_ids = [g["id"] for g in in_progress_before]
        assert doc_id not in before_ids

        # 2. Share with department
        db.share_draft_with_dept(doc_id, user_name="Sanjay Officer")
        in_progress_after = db.get_in_progress_forum_grs()
        after_ids = [g["id"] for g in in_progress_after]
        assert doc_id in after_ids

        # 3. Post a question
        question = db.add_gr_comment(
            gr_document_id=doc_id,
            user_name="Anjali Reviewer",
            user_role="Desk Officer",
            user_department="Higher & Technical Education Dept",
            comment_type="question",
            content="Is the income limit set at 8 Lakhs?",
        )
        assert question["id"] is not None
        assert question["content"] == "Is the income limit set at 8 Lakhs?"
        assert question["is_resolved"] is False

        # Post an answer to the question
        answer = db.add_gr_comment(
            gr_document_id=doc_id,
            parent_id=question["id"],
            user_name="Sanjay Officer",
            user_role="Drafting Officer",
            user_department="Higher & Technical Education Dept",
            comment_type="answer",
            content="Yes, per Section 2 of the draft, income ceiling is Rs 8 Lakhs.",
        )
        assert answer["id"] is not None
        assert answer["parent_id"] == question["id"]
        assert answer["comment_type"] == "answer"

        # Fetch comments and verify nested structure association
        comments = db.get_gr_comments(doc_id)
        assert len(comments) >= 2
        q_item = [c for c in comments if c["id"] == question["id"]][0]
        a_item = [c for c in comments if c["id"] == answer["id"]][0]
        assert a_item["parent_id"] == q_item["id"]

        # 4. Resolve comment
        db.toggle_comment_resolution(question["id"], True)
        comments_updated = db.get_gr_comments(doc_id)
        target = [c for c in comments_updated if c["id"] == question["id"]][0]
        assert target["is_resolved"] is True


        # 5. Finalize & Export GR -> should auto-remove from in-progress forum
        db.finalize_draft(doc_id)
        in_progress_final = db.get_in_progress_forum_grs()
        final_ids = [g["id"] for g in in_progress_final]
        assert doc_id not in final_ids

    except Exception:
        db.conn.rollback()
        raise
    finally:
        if doc_id:
            try:
                db.cur.execute("DELETE FROM gr_documents WHERE id = %s", (doc_id,))
                db.conn.commit()
            except Exception:
                pass
        db.close()
