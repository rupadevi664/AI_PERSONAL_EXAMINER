import os
import re
import json
import logging
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

from app.schemas import LLMQuestionOutput, LLMEvaluationOutput, LLMAnalysisOutput

load_dotenv()
logger = logging.getLogger("examiner.llm")


def clean_json_response(raw_text: str) -> str:
    """Extracts raw JSON string from potential Markdown code blocks or wrapping text."""
    text = raw_text.strip()
    # Match ```json ... ``` or ``` ... ```
    pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # If starting with { and ending with }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end+1].strip()
    return text


class LLMService:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "auto").lower()
        self.groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.custom_model = os.getenv("LLM_MODEL", "").strip()

    def _determine_active_provider(self) -> str:
        if self.provider != "auto" and self.provider:
            return self.provider
        if self.groq_api_key:
            return "groq"
        if self.gemini_api_key:
            return "gemini"
        if self.openai_api_key:
            return "openai"
        return "mock"

    def _call_groq(self, prompt: str) -> str:
        from groq import Groq
        client = Groq(api_key=self.groq_api_key)
        model_name = self.custom_model or "llama-3.3-70b-versatile"
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are an expert technical examiner. You strictly respond in valid JSON format."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        return completion.choices[0].message.content or "{}"

    def _call_gemini(self, prompt: str) -> str:
        from google import genai
        client = genai.Client(api_key=self.gemini_api_key)
        model_name = self.custom_model or "gemini-3.6-flash"
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        return response.text or "{}"

    def _call_openai(self, prompt: str) -> str:
        import httpx
        model_name = self.custom_model or "gpt-4o-mini"
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are an expert technical examiner. You strictly respond in valid JSON format."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"}
        }
        with httpx.Client(timeout=30.0) as client:
            res = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
            return data["choices"][0]["message"]["content"]

    def _call_active_llm(self, prompt: str) -> str:
        provider = self._determine_active_provider()
        try:
            if provider == "groq" and self.groq_api_key:
                return self._call_groq(prompt)
            elif provider == "gemini" and self.gemini_api_key:
                return self._call_gemini(prompt)
            elif provider == "openai" and self.openai_api_key:
                return self._call_openai(prompt)
            else:
                return ""
        except Exception as e:
            logger.warning(f"Error calling LLM provider '{provider}': {e}. Falling back to smart offline examiner.")
            return ""

    # =========================================================================
    # CORE EXAMINER METHODS
    # =========================================================================

    def generate_question(
        self,
        user_name: str,
        topic: str,
        difficulty: str,
        memory_context: Dict[str, Any]
    ) -> LLMQuestionOutput:
        """Generates a personalized question taking learner memory into account."""
        from app.prompts.examiner_prompt import QUESTION_GENERATION_PROMPT

        prompt = QUESTION_GENERATION_PROMPT.format(
            user_name=user_name,
            topic=topic,
            difficulty=difficulty,
            mastered_concepts=memory_context.get("mastered_concepts", "None"),
            weak_concepts=memory_context.get("weak_concepts", "None"),
            strengths=memory_context.get("strengths", "None"),
            avg_score=memory_context.get("avg_score", 0.0),
            recent_questions=memory_context.get("recent_questions", "None")
        )

        raw_output = self._call_active_llm(prompt)
        if raw_output:
            try:
                cleaned = clean_json_response(raw_output)
                parsed = json.loads(cleaned)
                return LLMQuestionOutput(**parsed)
            except Exception as parse_err:
                logger.warning(f"Failed to parse LLM question output: {parse_err}. Raw output was: {raw_output}")

        # Intelligent offline fallback engine with full memory awareness
        return self._offline_question_generator(topic, difficulty, memory_context)

    def evaluate_answer(
        self,
        topic: str,
        difficulty: str,
        concept: str,
        question_text: str,
        answer_text: str
    ) -> LLMEvaluationOutput:
        """Evaluates user answer, scores it, detects correct & missing points, and provides feedback."""
        from app.prompts.examiner_prompt import ANSWER_EVALUATION_PROMPT

        prompt = ANSWER_EVALUATION_PROMPT.format(
            topic=topic,
            difficulty=difficulty,
            concept=concept,
            question_text=question_text,
            answer_text=answer_text
        )

        raw_output = self._call_active_llm(prompt)
        if raw_output:
            try:
                cleaned = clean_json_response(raw_output)
                parsed = json.loads(cleaned)
                return LLMEvaluationOutput(**parsed)
            except Exception as parse_err:
                logger.warning(f"Failed to parse LLM evaluation output: {parse_err}. Raw: {raw_output}")

        # Intelligent offline evaluator
        return self._offline_answer_evaluator(topic, difficulty, concept, question_text, answer_text)

    def generate_learning_analysis(
        self,
        user_name: str,
        total_questions: int,
        overall_avg: float,
        strengths: List[str],
        weaknesses: List[str],
        mastered_concepts: List[str],
        recent_performance_summary: str
    ) -> LLMAnalysisOutput:
        """Generates deep pedagogical reflection for 'What My Examiner Learned About Me'."""
        from app.prompts.examiner_prompt import LEARNER_ANALYSIS_PROMPT

        prompt = LEARNER_ANALYSIS_PROMPT.format(
            user_name=user_name,
            total_questions=total_questions,
            overall_avg=overall_avg,
            strengths=", ".join(strengths) if strengths else "Still compiling data",
            weaknesses=", ".join(weaknesses) if weaknesses else "No major weaknesses detected yet",
            mastered_concepts=", ".join(mastered_concepts) if mastered_concepts else "None yet",
            performance_summary=recent_performance_summary or "No previous attempts"
        )

        raw_output = self._call_active_llm(prompt)
        if raw_output:
            try:
                cleaned = clean_json_response(raw_output)
                parsed = json.loads(cleaned)
                return LLMAnalysisOutput(**parsed)
            except Exception as parse_err:
                logger.warning(f"Failed to parse LLM analysis: {parse_err}")

        # Dynamic heuristic analysis based on actual data
        return self._offline_analysis_generator(user_name, total_questions, overall_avg, strengths, weaknesses, mastered_concepts)

    # =========================================================================
    # OFFLINE INTELLIGENT HEURISTIC ENGINE (Zero-Setup Guarantee)
    # =========================================================================

    def _offline_question_generator(
        self,
        topic: str,
        difficulty: str,
        memory_context: Dict[str, Any]
    ) -> LLMQuestionOutput:
        """
        Comprehensive knowledge bank mapped by topic, concept, and difficulty level.
        Respects mastered concepts (avoids basic level) and targets weak concepts.
        """
        t_key = topic.lower()
        diff = difficulty.lower()
        raw_mastered = [m.lower() for m in memory_context.get("raw_mastered", [])]
        raw_weak = [w.lower() for w in memory_context.get("raw_weak", [])]
        raw_recent = [q.lower() for q in memory_context.get("raw_recent", [])]

        catalog = self._get_question_catalog(t_key)

        # 1. Prioritize weak concepts if any exist
        weak_candidates = [
            q for q in catalog
            if q["difficulty"] == diff and any(w in q["concept"].lower() for w in raw_weak)
        ]

        # 2. Avoid mastered concepts if difficulty is easy
        candidates = weak_candidates if weak_candidates else [
            q for q in catalog
            if q["difficulty"] == diff and not (diff == "easy" and any(m in q["concept"].lower() for m in raw_mastered))
        ]

        # Fallback to any matching difficulty
        if not candidates:
            candidates = [q for q in catalog if q["difficulty"] == diff]

        if not candidates:
            candidates = catalog

        # Filter out questions already in recent history
        unasked = [c for c in candidates if not any(c["question"].lower() in r for r in raw_recent)]
        selected = unasked[0] if unasked else candidates[0]

        return LLMQuestionOutput(
            topic=topic,
            difficulty=selected["difficulty"],
            concept=selected["concept"],
            question=selected["question"]
        )

    def _offline_answer_evaluator(
        self,
        topic: str,
        difficulty: str,
        concept: str,
        question_text: str,
        answer_text: str
    ) -> LLMEvaluationOutput:
        """Evaluates student answer using linguistic keywords, length, and technical depth."""
        cleaned_ans = answer_text.strip()
        words = len(cleaned_ans.split())

        if words < 4:
            return LLMEvaluationOutput(
                score=2.0,
                correct_points=["Attempted to submit an answer"],
                missing_points=["Answer is too brief or lacks technical explanation", "Needs concrete code or scenario explanation"],
                feedback="Your answer was too brief. An examiner looks for in-depth reasoning, syntax, and conceptual justification.",
                recommended_difficulty="easy"
            )

        # Rubric checks
        c_lower = concept.lower()
        ans_lower = cleaned_ans.lower()

        score = 6.0
        correct: List[str] = []
        missing: List[str] = []

        # Length / completeness bonus
        if words >= 25:
            score += 1.5
            correct.append("Provided a structured and detailed explanation")
        else:
            missing.append("Could elaborate with more thorough context or real-world use cases")

        # Specific concept matches
        if "list" in c_lower:
            if "mutable" in ans_lower or "index" in ans_lower or "dynamic" in ans_lower:
                score += 1.5
                correct.append("Identified mutability and element ordering")
            if "time complexity" in ans_lower or "o(n)" in ans_lower or "o(1)" in ans_lower:
                score += 1.0
                correct.append("Noted computational complexity")
            else:
                missing.append("Did not specify the runtime time complexity (e.g. O(1) vs O(N))")

        elif "sql" in c_lower or "join" in c_lower:
            if "inner" in ans_lower or "left" in ans_lower or "match" in ans_lower or "table" in ans_lower:
                score += 1.5
                correct.append("Understood join matching conditions between relational tables")
            if "null" in ans_lower or "on" in ans_lower or "foreign key" in ans_lower:
                score += 1.0
                correct.append("Addressed join keys and NULL handling")
            else:
                missing.append("Did not mention NULL handling or join predicate index optimization")

        elif "oop" in c_lower or "class" in c_lower or "inherit" in c_lower:
            if "class" in ans_lower or "object" in ans_lower or "super" in ans_lower or "parent" in ans_lower:
                score += 1.5
                correct.append("Understood object-oriented hierarchy and class structures")
            if "polymorphism" in ans_lower or "encapsulation" in ans_lower or "override" in ans_lower:
                score += 1.0
                correct.append("Explained method overriding or encapsulation boundaries")
            else:
                missing.append("Could mention method resolution order (MRO) or method overriding")

        elif "dsa" in c_lower or "tree" in c_lower or "graph" in c_lower or "complexity" in c_lower:
            if "o(" in ans_lower or "time" in ans_lower or "space" in ans_lower or "recursion" in ans_lower:
                score += 2.0
                correct.append("Evaluated asymptotic complexity and data structure layout")
            else:
                missing.append("Missing explicit Big-O notation for time or auxiliary space complexity")

        elif "scale" in c_lower or "shard" in c_lower or "cache" in c_lower or "load" in c_lower or "cap" in c_lower:
            if "latency" in ans_lower or "throughput" in ans_lower or "partition" in ans_lower or "node" in ans_lower or "cluster" in ans_lower:
                score += 2.0
                correct.append("Analyzed distributed systems tradeoffs, latency, and fault tolerance")
            if "consistency" in ans_lower or "availability" in ans_lower or "redis" in ans_lower:
                score += 1.0
                correct.append("Addressed state replication and caching layer implications")
            else:
                missing.append("Could mention fault-tolerance, replication lag, or data durability guarantees")

        elif "docker" in c_lower or "kubernetes" in c_lower or "ci/cd" in c_lower or "deploy" in c_lower:
            if "container" in ans_lower or "image" in ans_lower or "pod" in ans_lower or "layer" in ans_lower:
                score += 2.0
                correct.append("Identified container isolation, orchestration primitives, and immutable infrastructure")
            if "pipeline" in ans_lower or "rollback" in ans_lower or "canary" in ans_lower or "health" in ans_lower:
                score += 1.0
                correct.append("Discussed deployment automation and resilience patterns")
            else:
                missing.append("Consider detailing health checks (liveness/readiness) and rollback automation")

        else:
            if len(ans_lower) > 50:
                score += 1.5
                correct.append(f"Addressed core tenets of {concept}")
            else:
                missing.append(f"Consider explaining edge cases and memory implications of {concept}")

        # Bonus for writing actual code or pseudo-code snippets
        has_code = any(k in cleaned_ans for k in ["def ", "return ", "class ", "import ", "for ", "while ", "if ", "SELECT ", "CREATE "]) or "```" in cleaned_ans
        if has_code:
            score = min(10.0, score + 1.0)
            correct.append("Provided concrete code/syntax implementation")

        final_score = min(10.0, max(1.0, round(score, 1)))

        # Recommended difficulty
        if final_score >= 8.0:
            rec_diff = "hard" if difficulty == "medium" else "medium"
        elif final_score >= 5.0:
            rec_diff = difficulty
        else:
            rec_diff = "easy" if difficulty == "medium" else "easy"

        feedback_msg = (
            f"Strong demonstration of {concept}! Your technical grasp is clear."
            if final_score >= 8.0
            else f"Decent grasp of {concept}, but practice including edge cases, code syntax, or Big-O complexity."
            if final_score >= 5.0
            else f"Review {concept} fundamentals. Focus on precise mechanics and write out small code snippets."
        )

        return LLMEvaluationOutput(
            score=final_score,
            correct_points=correct or [f"Understood general premise of {concept}"],
            missing_points=missing or ["Could include more production-level edge cases"],
            feedback=feedback_msg,
            recommended_difficulty=rec_diff
        )

    def _offline_analysis_generator(
        self,
        user_name: str,
        total_questions: int,
        overall_avg: float,
        strengths: List[str],
        weaknesses: List[str],
        mastered_concepts: List[str]
    ) -> LLMAnalysisOutput:
        s_str = ", ".join(strengths[:3]) if strengths else "fundamental syntax"
        w_str = ", ".join(weaknesses[:3]) if weaknesses else "niche edge cases"

        obs = (
            f"You exhibit strong conceptual fluency in {s_str}. "
            f"However, you tend to lose precision when asked for time/space complexity or practical production edge cases in {w_str}."
        )

        return LLMAnalysisOutput(
            observation=obs,
            weak_focus_percent=60 if weaknesses else 40,
            new_concepts_percent=30 if weaknesses else 45,
            revision_percent=10 if weaknesses else 15,
            learning_insights=(
                f"1. Spend 60% of your next session re-implementing {w_str} from scratch.\n"
                f"2. Always state time and space complexity upfront before providing code.\n"
                f"3. Leverage your strength in {s_str} to architect higher-level solutions."
            )
        )

    def _get_question_catalog(self, topic: str) -> List[Dict[str, str]]:
        """Rich predefined question library across topics and difficulty tiers."""
        libraries: Dict[str, List[Dict[str, str]]] = {
            "python": [
                # Easy
                {"difficulty": "easy", "concept": "Python Lists", "question": "What is a Python list, and how does it differ from a tuple in terms of mutability and memory usage?"},
                {"difficulty": "easy", "concept": "Dictionary Mechanics", "question": "How do Python dictionaries store key-value pairs, and what are the requirements for an object to be used as a dictionary key?"},
                {"difficulty": "easy", "concept": "String Formatting", "question": "Explain f-strings in Python. How do they compare in performance and readability to str.format() and % formatting?"},
                {"difficulty": "easy", "concept": "Functions & Scope", "question": "Explain the LEGB rule (Local, Enclosing, Global, Built-in) in Python variable scope resolution."},
                # Medium
                {"difficulty": "medium", "concept": "List Deduplication", "question": "How would you remove duplicate elements from a Python list while preserving the original order without using set()? Explain your approach and time complexity."},
                {"difficulty": "medium", "concept": "Decorators", "question": "What is a Python decorator? Write a conceptual decorator that measures the execution time of any function."},
                {"difficulty": "medium", "concept": "Generators & Iterators", "question": "What is the difference between an iterator and a generator in Python? How does the 'yield' keyword preserve function state?"},
                {"difficulty": "medium", "concept": "OOP Inheritance", "question": "Explain single vs multiple inheritance in Python. What is the Method Resolution Order (MRO) and how do you inspect it?"},
                # Hard
                {"difficulty": "hard", "concept": "GIL & Concurrency", "question": "Explain Python's Global Interpreter Lock (GIL). When should you choose multiprocessing over multithreading or asyncio for CPU-bound vs I/O-bound tasks?"},
                {"difficulty": "hard", "concept": "Metaclasses & Descriptors", "question": "What is a descriptor in Python (__get__, __set__, __delete__)? How do Python properties and ORM fields utilize the descriptor protocol?"},
                {"difficulty": "hard", "concept": "Memory Management & GC", "question": "How does CPython manage memory? Explain reference counting, cyclic garbage collection (generations 0, 1, 2), and when memory leaks can still occur."}
            ],
            "sql": [
                # Easy
                {"difficulty": "easy", "concept": "SELECT & WHERE", "question": "What is the purpose of the WHERE clause in SQL, and how does it differ from the HAVING clause?"},
                {"difficulty": "easy", "concept": "SQL Data Types", "question": "What is the difference between CHAR, VARCHAR, and TEXT data types in relational databases?"},
                {"difficulty": "easy", "concept": "Primary vs Foreign Key", "question": "Explain the difference between a Primary Key and a Unique constraint with a Foreign Key relationship."},
                # Medium
                {"difficulty": "medium", "concept": "SQL JOINs", "question": "Explain the practical difference between an INNER JOIN and a LEFT OUTER JOIN. Give an example where a LEFT JOIN returns rows with NULL values."},
                {"difficulty": "medium", "concept": "GROUP BY & Aggregates", "question": "Given an 'orders' table with customer_id, order_date, and total_amount, write a query to find customers who have spent over $1,000 in total."},
                {"difficulty": "medium", "concept": "Subqueries vs Joins", "question": "When is a correlated subquery preferable over a JOIN, and what is its performance implication on large tables?"},
                # Hard
                {"difficulty": "hard", "concept": "Window Functions", "question": "Explain SQL window functions (ROW_NUMBER(), RANK(), DENSE_RANK()). How would you find the 2nd highest salary in each department using DENSE_RANK() OVER (PARTITION BY ... ORDER BY ...)?"},
                {"difficulty": "hard", "concept": "B-Tree Indexing", "question": "Explain how B-Tree indexes work under the hood. Why does adding an index speed up SELECTs but slow down INSERTs and UPDATEs?"},
                {"difficulty": "hard", "concept": "ACID Transactions & Isolation", "question": "Describe the 4 ANSI SQL transaction isolation levels (Read Uncommitted, Read Committed, Repeatable Read, Serializable) and the anomalies they prevent."}
            ],
            "fastapi": [
                # Easy
                {"difficulty": "easy", "concept": "FastAPI Basics", "question": "What is FastAPI, and how does it leverage Python type hints to perform automated request validation and documentation?"},
                {"difficulty": "easy", "concept": "Path vs Query Parameters", "question": "Explain how FastAPI distinguishes between a path parameter and a query parameter in an endpoint signature."},
                # Medium
                {"difficulty": "medium", "concept": "Dependency Injection", "question": "How does FastAPI's Depends system work? Explain how you would implement a database session dependency using yield."},
                {"difficulty": "medium", "concept": "Pydantic Validation", "question": "How do Pydantic models validate incoming request payloads in FastAPI, and how do you handle custom field validation?"},
                {"difficulty": "medium", "concept": "Background Tasks", "question": "What are FastAPI BackgroundTasks and when should you use them versus a dedicated task broker like Celery or RQ?"},
                # Hard
                {"difficulty": "hard", "concept": "ASGI & Concurrency", "question": "Explain how Starlette and AnyIO handle async def vs plain def route handlers in FastAPI. Why can a blocking synchronous function in 'async def' choke the entire event loop?"},
                {"difficulty": "hard", "concept": "Custom Middleware & Exception Handlers", "question": "How do you implement custom ASGI middleware for request timing and global error handling without losing streaming responses?"}
            ],
            "django": [
                # Easy
                {"difficulty": "easy", "concept": "MVT Architecture", "question": "Explain Django's Model-View-Template (MVT) architecture and how it relates to traditional MVC."},
                {"difficulty": "easy", "concept": "Django ORM Basics", "question": "What is Django ORM and what command do you run to create and apply database migrations?"},
                # Medium
                {"difficulty": "medium", "concept": "QuerySet Optimization", "question": "Explain the difference between select_related and prefetch_related in Django ORM. How do they solve the N+1 queries problem?"},
                {"difficulty": "medium", "concept": "Django Middleware", "question": "How does Django's middleware processing order work during the request and response cycle?"},
                # Hard
                {"difficulty": "hard", "concept": "Signals vs Model Overrides", "question": "Why is overriding model.save() or using service layers often preferred over post_save signals in large-scale Django applications?"}
            ],
            "dsa": [
                # Easy
                {"difficulty": "easy", "concept": "Big-O Notation", "question": "Explain Big-O notation. What is the difference between O(1), O(log n), and O(n) time complexity?"},
                {"difficulty": "easy", "concept": "Arrays vs Linked Lists", "question": "Compare arrays and singly linked lists in terms of random access, insertion, and memory locality."},
                # Medium
                {"difficulty": "medium", "concept": "Two Pointer Technique", "question": "How does the two-pointer technique work to find two numbers in a sorted array that sum up to a target in O(N) time and O(1) space?"},
                {"difficulty": "medium", "concept": "Binary Search Trees", "question": "Explain the properties of a Binary Search Tree (BST). What happens to search efficiency when a BST becomes degenerate (unbalanced)?"},
                # Hard
                {"difficulty": "hard", "concept": "Dynamic Programming", "question": "Explain the concepts of optimal substructure and overlapping subproblems in Dynamic Programming. How does memoization (top-down) differ from tabulation (bottom-up)?"},
                {"difficulty": "hard", "concept": "Graph Algorithms", "question": "Compare Dijkstra's algorithm and Breadth-First Search (BFS). When can BFS be used to find shortest paths instead of Dijkstra's?"}
            ],
            "javascript": [
                # Easy
                {"difficulty": "easy", "concept": "var vs let vs const", "question": "Explain the differences between var, let, and const in JavaScript regarding hoisting and block scoping."},
                {"difficulty": "easy", "concept": "Data Types & Equality", "question": "What is the difference between '==' (loose equality) and '===' (strict equality) in JavaScript?"},
                # Medium
                {"difficulty": "medium", "concept": "Closures", "question": "What is a closure in JavaScript? Provide a real-world example of how closures enable data privacy."},
                {"difficulty": "medium", "concept": "Promises & Async/Await", "question": "How do Promises work in JavaScript? Explain the event loop call stack, microtask queue, and macrotask queue."},
                # Hard
                {"difficulty": "hard", "concept": "Prototypes & Inheritance", "question": "Explain JavaScript's prototypical inheritance. How does the prototype chain work when accessing a property on an object?"}
            ],
            "system design": [
                # Easy
                {"difficulty": "easy", "concept": "Horizontal vs Vertical Scaling", "question": "Explain the difference between horizontal and vertical scaling. What are the key bottlenecks of vertical scaling in database architectures?"},
                {"difficulty": "easy", "concept": "Load Balancing", "question": "What is a load balancer? Compare Round Robin, Least Connections, and IP Hash load balancing algorithms."},
                # Medium
                {"difficulty": "medium", "concept": "Caching Strategies", "question": "Explain Cache-Aside (Lazy Loading) vs Write-Through caching. What is the cache stampede (thundering herd) problem and how do you mitigate it?"},
                {"difficulty": "medium", "concept": "Database Sharding", "question": "What is database sharding? Explain the difference between range-based sharding and hash-based consistent hashing."},
                # Hard
                {"difficulty": "hard", "concept": "Distributed Consensus & CAP", "question": "Explain the CAP theorem and PACELC theorem. How does Raft consensus guarantee leader election and log replication safety across network partitions?"},
                {"difficulty": "hard", "concept": "Eventual Consistency & Sagas", "question": "How do you maintain distributed transaction consistency across microservices using the Saga pattern (Choreography vs Orchestration)?"}
            ],
            "devops": [
                # Easy
                {"difficulty": "easy", "concept": "Docker Fundamentals", "question": "What is the difference between a Docker image and a Docker container? How does Docker utilize Linux namespaces and cgroups?"},
                {"difficulty": "easy", "concept": "CI/CD Pipelines", "question": "Explain the core difference between Continuous Integration, Continuous Delivery, and Continuous Deployment."},
                # Medium
                {"difficulty": "medium", "concept": "Multi-Stage Docker Builds", "question": "Why are multi-stage Docker builds recommended for compiled or dependency-heavy applications? Provide an example of minimizing final image size."},
                {"difficulty": "medium", "concept": "Kubernetes Architecture", "question": "Explain the role of Pods, Deployments, and Services in Kubernetes. How does kube-proxy handle traffic routing across nodes?"},
                # Hard
                {"difficulty": "hard", "concept": "Zero-Downtime Deployments", "question": "Compare Blue-Green, Canary, and Rolling deployment strategies in Kubernetes. How do you handle schema migrations with zero downtime?"},
                {"difficulty": "hard", "concept": "Observability & Tracing", "question": "What are the 3 pillars of observability (Metrics, Logs, Traces)? How does distributed context propagation work in OpenTelemetry with W3C TraceContext headers?"}
            ]
        }

        # Return questions for topic, or default to python if unknown
        for key in libraries:
            if key in topic:
                return libraries[key]
        return libraries["python"]


# Singleton service instance
llm_service = LLMService()
