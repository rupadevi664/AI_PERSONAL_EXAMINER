import os
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.services.examiner import (
    normalize_text,
    calculate_text_similarity,
    is_question_repetitive,
    calculate_next_difficulty
)
from app.services import memory

from sqlalchemy.pool import StaticPool

# In-memory SQLite with StaticPool so all threads/sessions share the same DB
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


class TestExaminerEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=test_engine)

    def test_text_normalization(self):
        raw = "  What is a Python List?!  "
        normalized = normalize_text(raw)
        self.assertEqual(normalized, "what is a python list")

    def test_anti_repetition_exact_duplicate(self):
        q1 = "What is a Python list?"
        q2 = "what is a python list"
        sim = calculate_text_similarity(q1, q2)
        self.assertGreaterEqual(sim, 0.95)

        is_rep, reason = is_question_repetitive(q1, [q2])
        self.assertTrue(is_rep)
        self.assertIn("duplicate", reason.lower())

    def test_anti_repetition_fuzzy_similarity(self):
        q1 = "Explain the difference between a list and a tuple in Python."
        q2 = "Explain the difference between Python list and tuple."
        is_rep, reason = is_question_repetitive(q1, [q2], threshold=0.70)
        self.assertTrue(is_rep)

        distinct_q = "How does Python garbage collection handle cyclic references?"
        is_rep_distinct, _ = is_question_repetitive(distinct_q, [q2], threshold=0.70)
        self.assertFalse(is_rep_distinct)

    def test_adaptive_difficulty_progression(self):
        # 1. High score increases difficulty
        next_diff = calculate_next_difficulty("easy", 9.0, [8.5, 9.0])
        self.assertEqual(next_diff, "medium")

        next_diff_hard = calculate_next_difficulty("medium", 9.5, [9.0, 8.0])
        self.assertEqual(next_diff_hard, "hard")

        # Hard does not go past hard
        next_diff_cap = calculate_next_difficulty("hard", 10.0, [9.0, 9.0])
        self.assertEqual(next_diff_cap, "hard")

        # 2. Average score maintains difficulty
        next_diff_maintain = calculate_next_difficulty("medium", 6.5, [6.0, 7.0])
        self.assertEqual(next_diff_maintain, "medium")

        # 3. Low score drops difficulty
        next_diff_drop = calculate_next_difficulty("hard", 3.0, [4.0, 2.0])
        self.assertEqual(next_diff_drop, "medium")

        next_diff_drop_easy = calculate_next_difficulty("medium", 2.0, [3.0, 3.5])
        self.assertEqual(next_diff_drop_easy, "easy")

    def test_full_exam_lifecycle_api(self):
        # 1. Start Exam
        start_res = self.client.post("/exam/start", json={
            "name": "Rupa Test",
            "topic": "Python",
            "difficulty": "easy"
        })
        self.assertEqual(start_res.status_code, 201)
        start_data = start_res.json()
        user_id = start_data["user_id"]
        self.assertEqual(start_data["name"], "Rupa Test")
        self.assertEqual(start_data["topic"], "Python")

        # 2. Generate First Question
        q_res = self.client.post("/exam/question", json={
            "user_id": user_id,
            "topic": "Python",
            "difficulty": "easy"
        })
        self.assertEqual(q_res.status_code, 200)
        q_data = q_res.json()
        question_id = q_data["id"]
        self.assertIn("Python", q_data["topic"])
        self.assertTrue(len(q_data["question_text"]) > 10)

        # 3. Submit High-Scoring Answer
        ans_res = self.client.post("/exam/answer", json={
            "user_id": user_id,
            "question_id": question_id,
            "answer_text": "A list in Python is a mutable ordered sequence of elements, indexed by integers. It allows dynamic resizing and insertion."
        })
        self.assertEqual(ans_res.status_code, 200)
        eval_data = ans_res.json()
        self.assertGreaterEqual(eval_data["score"], 7.0)
        self.assertTrue(len(eval_data["correct_points"]) > 0)

        # 4. Check History Endpoint
        hist_res = self.client.get(f"/exam/history/{user_id}")
        self.assertEqual(hist_res.status_code, 200)
        history = hist_res.json()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["question_id"], question_id)

        # 5. Check Progress Endpoint
        prog_res = self.client.get(f"/exam/progress/{user_id}")
        self.assertEqual(prog_res.status_code, 200)
        progress = prog_res.json()
        self.assertTrue(len(progress) >= 1)
        self.assertEqual(progress[0]["topic"], "Python")

        # 6. Check Analysis ("What My Examiner Learned About Me") Endpoint
        analysis_res = self.client.get(f"/exam/analysis/{user_id}")
        self.assertEqual(analysis_res.status_code, 200)
        analysis_data = analysis_res.json()
        self.assertEqual(analysis_data["user_id"], user_id)
        self.assertIn("next_exam_strategy", analysis_data)
        self.assertTrue(len(analysis_data["ai_observation"]) > 0)

    def test_mastered_concept_avoidance_tracking(self):
        """Verify that when a concept is mastered, easy questions on it are avoided and counted."""
        # 1. Start exam for another user
        start_res = self.client.post("/exam/start", json={
            "name": "Alex Mastery",
            "topic": "Python",
            "difficulty": "easy"
        })
        user_id = start_res.json()["user_id"]

        # 2. Get first question
        q1_res = self.client.post("/exam/question", json={
            "user_id": user_id,
            "topic": "Python",
            "difficulty": "easy"
        })
        q1_data = q1_res.json()
        concept = q1_data["concept"]

        # 3. Submit high score (10.0) so concept is formally mastered
        ans_res = self.client.post("/exam/answer", json={
            "user_id": user_id,
            "question_id": q1_data["id"],
            "answer_text": "Lists in Python are dynamic, mutable arrays supporting O(1) random access and append, whereas tuples are immutable. Complexity is O(n) for removal."
        })
        eval_data = ans_res.json()
        self.assertTrue(eval_data["concept_mastered"])

        # 4. Request another question in Python at easy difficulty
        q2_res = self.client.post("/exam/question", json={
            "user_id": user_id,
            "topic": "Python",
            "difficulty": "easy"
        })
        q2_data = q2_res.json()

        # The new question must NOT repeat q1
        self.assertNotEqual(q1_data["question_text"], q2_data["question_text"])

        # Check that user progress records show the mastered concept
        prog_res = self.client.get(f"/exam/progress/{user_id}")
        prog_data = prog_res.json()
        self.assertTrue(len(prog_data) > 0)
        self.assertIn(concept.strip().title(), [c.strip().title() for c in prog_data[0]["mastered_concepts"]])

    def test_reset_and_export_endpoints(self):
        """Verify export generation and progress reset."""
        # 1. Start exam
        start_res = self.client.post("/exam/start", json={
            "name": "Jordan Dev",
            "topic": "System Design",
            "difficulty": "medium"
        })
        user_id = start_res.json()["user_id"]

        # 2. Get and answer question
        q_res = self.client.post("/exam/question", json={
            "user_id": user_id,
            "topic": "System Design",
            "difficulty": "medium"
        })
        q_id = q_res.json()["id"]

        self.client.post("/exam/answer", json={
            "user_id": user_id,
            "question_id": q_id,
            "answer_text": "We use Cache-Aside with Redis to reduce database read latency, handling cache stampede with distributed mutex locks."
        })

        # 3. Test Export Markdown endpoint
        export_res = self.client.get(f"/exam/export/{user_id}")
        self.assertEqual(export_res.status_code, 200)
        export_data = export_res.json()
        self.assertIn("Jordan Dev", export_data["markdown"])
        self.assertIn("AI Examiner Observation", export_data["markdown"])

        # 4. Test Download endpoint
        download_res = self.client.get(f"/exam/export/{user_id}/download")
        self.assertEqual(download_res.status_code, 200)
        self.assertIn("attachment", download_res.headers.get("Content-Disposition", ""))

        # 5. Test Reset endpoint for specific topic
        reset_res = self.client.post("/exam/reset", json={
            "user_id": user_id,
            "topic": "System Design"
        })
        self.assertEqual(reset_res.status_code, 200)
        self.assertTrue(reset_res.json()["success"])

        # History should now be empty for that topic
        hist_res = self.client.get(f"/exam/history/{user_id}")
        self.assertEqual(len(hist_res.json()), 0)

    def test_code_sandbox_python_success(self):
        from app.services.code_runner import execute_code_sandbox
        code = "def add(a, b):\n    return a + b\nprint('SUM:', add(10, 25))"
        result = execute_code_sandbox(code, language="python", timeout=4.0)
        self.assertTrue(result["success"])
        self.assertIn("SUM: 35", result["stdout"])
        self.assertEqual(result["exit_code"], 0)
        self.assertGreater(result["execution_time_ms"], 0)

    def test_code_sandbox_syntax_error(self):
        from app.services.code_runner import execute_code_sandbox
        code = "def broken(\n    print('missing paren')"
        result = execute_code_sandbox(code, language="python", timeout=4.0)
        self.assertFalse(result["success"])
        self.assertIn("SyntaxError", result["stderr"])
        self.assertNotEqual(result["exit_code"], 0)

    def test_code_sandbox_timeout_guard(self):
        from app.services.code_runner import execute_code_sandbox
        code = "while True:\n    pass"
        result = execute_code_sandbox(code, language="python", timeout=1.0)
        self.assertFalse(result["success"])
        self.assertIn("timed out", result["stderr"].lower())
        self.assertEqual(result["exit_code"], -1)

    def test_run_code_api_endpoint(self):
        # 1. Python run via HTTP API
        res = self.client.post("/exam/run-code", json={
            "code": "print('FASTAPI_SANDBOX_OK')",
            "language": "python",
            "timeout_seconds": 3.0
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertIn("FASTAPI_SANDBOX_OK", data["stdout"])
        self.assertEqual(data["exit_code"], 0)

        # 2. JavaScript run via HTTP API (Node.js)
        res_js = self.client.post("/exam/run-code", json={
            "code": "console.log('JS_SANDBOX_OUTPUT: ' + (40 + 2));",
            "language": "javascript",
            "timeout_seconds": 3.0
        })
        self.assertEqual(res_js.status_code, 200)
        data_js = res_js.json()
        self.assertTrue(data_js["success"])
        self.assertIn("JS_SANDBOX_OUTPUT: 42", data_js["stdout"])


if __name__ == "__main__":
    unittest.main()


