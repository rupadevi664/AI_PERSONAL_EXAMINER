# AI PERSONAL EXAMINER
> *“An AI examiner that remembers what I know.”*

An intelligent, LLM-powered technical examiner and interviewer that continuously remembers the user's previous answers, measures mastery across concepts, detects strengths and weaknesses, scales difficulty adaptively, and avoids repetitive or already-mastered questions.

---

## 1. Project Overview
Most interview preparation bots and LLM tutors suffer from "amnesia"—they treat every question as a standalone prompt. If you answer a question about Python lists with distinction, a traditional bot will happily ask you the exact same definition question five minutes later.

The **AI Personal Examiner** transforms technical assessment into a continuous, personalized learning journey. By coupling a relational memory engine with LLM intelligence, it maintains a persistent profile of what you know, challenges you on your weaknesses using novel scenarios, and elevates question difficulty as you improve.

---

## 2. Problem Statement
1. **Generic Questions**: Interview preparation tools repeatedly ask the same beginner questions (e.g., "What is a list?", "What is a dictionary?").
2. **Lack of Adaptive Progression**: Candidates who already master fundamentals are not challenged with intermediate or advanced production scenarios.
3. **No Memory of Weaknesses**: When a learner struggles with a topic (e.g., SQL JOINs, OOP inheritance), typical tools fail to diagnose the root deficiency or retest it effectively.
4. **Repetitive Question Loops**: Without application-level deduplication, LLMs frequently hallucinate or regenerate nearly identical phrasing.

---

## 3. The Solution
The AI Personal Examiner solves these problems by:
1. **Maintaining a Long-term Memory Ledger**: Every question, answer, score, feedback, covered point, and missing nuance is recorded in SQLite via SQLAlchemy.
2. **Context-Injected Question Generation**: Before asking any question, the memory engine injects your mastered concepts, weak concepts, average score, and recent question history into the LLM prompt.
3. **Dual-Tier Anti-Repetition Guard**: Both LLM-level negative constraints and application-level text similarity checks (Jaccard + Levenshtein) reject duplicates before they reach the user.
4. **Dynamic Difficulty Scaling**: Automatically transitions between Easy, Medium, and Hard based on your rolling performance window.
5. **Pedagogical Reflection**: Synthesizes an executive report (*"What My Examiner Learned About Me"*) with custom study breakdowns (e.g., 60% weak areas, 30% new frontiers, 10% revision).

---

## 4. The WOW Feature: Personalized Memory
The cornerstone of the application is **Personalized Memory**:
- If you answer *"What is a Python list?"* with a score of **9/10**, the examiner flags `Python Lists` as **MASTERED**.
- It will **never** ask you that basic definition question again.
- When it encounters `Python Lists` again, it escalates to an advanced problem:
  > *"How would you remove duplicate elements from a Python list without using `set()` while preserving order? Explain your approach and time complexity."*
- If you struggle with `SQL JOINs` (score < 5/10), the examiner flags it as a **WEAK AREA** and brings it back later using a completely different real-world scenario (e.g., customer order reconciliation).
- The dashboard proudly tracks **"Questions Avoided"**—quantifying exactly how many redundant questions you were spared from answering!

---

## 5. Key Features
- 🧠 **Persistent Learner Profiles**: Tracks progress across technical domains (Python, SQL, FastAPI, Django, DSA, JavaScript).
- 📈 **Adaptive Difficulty Engine**: 
  - Score 8–10: Promotes to next difficulty tier (`easy` -> `medium` -> `hard`).
  - Score 5–7: Maintains current difficulty.
  - Score 0–4: Demotes difficulty to reinforce fundamentals.
- 🛡️ **Application-Level Anti-Repetition**: Normalizes text and evaluates string/token similarity; rejects questions above 70% similarity.
- 🎯 **Deep Answer Evaluation**: Breaks down user responses into *Covered Points*, *Missing Nuances*, constructive *Feedback*, and numeric *Scores (0–10)*.
- 📊 **Learner Dashboard**: Interactive KPIs, topic competency bars, mastered concept chips, and a full chronological audit trail.
- 🔍 **"What My Examiner Learned About Me" Screen**: High-impact WOW view highlighting verified strengths, target weaknesses, cognitive observations, and upcoming exam strategy.
- 🔌 **Pluggable LLM Architecture**: Seamless support for Groq (Llama 3.3), Google Gemini 3.6, OpenAI, or an intelligent offline heuristic engine for zero-setup execution.

---

## 6. Architecture

```
+-------------------------------------------------------------+
|               Frontend (Vanilla HTML5 / CSS3 / JS)          |
|  - index.html (Start Exam & Profile)                        |
|  - exam.html (Interactive Question, Live Evaluation, Next)  |
|  - dashboard.html (Progress, Mastered Topics, Avoided Qs)   |
|  - result.html (WOW Screen: Examiner Insights & Strategy)   |
+------------------------------+------------------------------+
                               | REST API (Fetch)
                               v
+-------------------------------------------------------------+
|                      FastAPI Backend                        |
|  - routes/exam.py: /exam/start, /exam/question, /exam/answer|
|  - routes/progress.py: /history, /progress, /analysis       |
+--------------+-------------------------------+--------------+
               |                               |
               v                               v
+-------------------------------+  +--------------------------+
|  Services Layer               |  |  Database Layer (SQLite) |
|  - memory.py (Context Engine) |  |  SQLAlchemy 2.0 ORM      |
|  - examiner.py (Rules & Logic)|  |  - User                  |
|  - llm_service.py (LLM / API) |  |  - Question              |
|  - Anti-repetition Similarity |  |  - Answer                |
|  - Adaptive Difficulty Engine |  |  - UserProgress          |
+-------------------------------+  +--------------------------+
```

---

## 7. Tech Stack
- **Backend**: Python 3.10+, FastAPI, SQLAlchemy 2.0, SQLite, Pydantic v2, Uvicorn
- **AI / LLM Integration**: Groq API (`llama-3.3-70b-versatile`), Google GenAI (`gemini-3.6-flash`), or OpenAI (`gpt-4o-mini`), plus offline fallback
- **Frontend**: Semantic HTML5, Vanilla CSS3 (Custom Glassmorphic Dark Design System), Vanilla JavaScript (ES6 Fetch API)
- **Environment**: `python-dotenv` for configuration

---

## 8. Folder Structure

```
AI-Personal-Examiner/
│
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI app entry point & static routes
│   ├── database.py               # SQLite engine, sessionmaker & get_db
│   ├── models.py                 # SQLAlchemy ORM models (User, Question, Answer, UserProgress)
│   ├── schemas.py                # Pydantic request & response schemas
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── exam.py               # /exam/start, /exam/question, /exam/answer
│   │   └── progress.py           # /exam/history, /exam/progress, /exam/analysis
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── memory.py             # Retrieves learner context, mastered & weak concepts
│   │   ├── examiner.py           # Anti-repetition, difficulty scaling & orchestration
│   │   └── llm_service.py        # Groq/Gemini/OpenAI callers & smart offline engine
│   │
│   └── prompts/
│       ├── __init__.py
│       └── examiner_prompt.py    # System prompts for question gen, evaluation & analysis
│
├── frontend/
│   ├── index.html                # Home page (Start Exam & Profile)
│   ├── exam.html                 # Live exam room with evaluation feedback
│   ├── dashboard.html            # Metrics, topic progress bars & history
│   ├── result.html               # BIG WOW SCREEN ("What My Examiner Learned About Me")
│   ├── style.css                 # Dark mode glassmorphic UI design system
│   └── script.js                 # Session management & client-side API logic
│
├── tests/
│   ├── __init__.py
│   └── test_examiner.py          # Unit & integration tests
│
├── .env.example                  # Environment variable blueprint
├── .gitignore                    # Secrets, DB, and pycache exclusions
├── requirements.txt              # Production dependencies
└── README.md                     # Documentation & Interview Guide
```

---

## 9. Database Design

The SQLite database (`examiner.db`) contains 4 interconnected tables:

### `users`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer (PK) | Unique user identifier |
| `name` | String(100) | Learner name (indexed) |
| `created_at` | DateTime | Timestamp of profile registration |

### `questions`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer (PK) | Unique question identifier |
| `user_id` | Integer (FK) | References `users.id` |
| `topic` | String(100) | Technical topic (e.g. Python, SQL) |
| `question_text`| Text | The question presented to learner |
| `difficulty` | String(50) | `easy`, `medium`, or `hard` |
| `concept` | String(150) | The concept tested (e.g. List Deduplication) |
| `created_at` | DateTime | Timestamp of creation |

### `answers`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer (PK) | Unique answer identifier |
| `question_id`| Integer (FK) | References `questions.id` |
| `user_id` | Integer (FK) | References `users.id` |
| `answer_text`| Text | Submitted learner solution |
| `score` | Float | Score evaluated by LLM (0.0 – 10.0) |
| `feedback` | Text | Constructive advice from examiner |
| `correct_points`| Text (JSON) | Array of concepts covered |
| `missing_points`| Text (JSON) | Array of missing nuances |
| `created_at` | DateTime | Timestamp of submission |

### `user_progress`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer (PK) | Unique record identifier |
| `user_id` | Integer (FK) | References `users.id` |
| `topic` | String(100) | Domain (e.g. Python) |
| `questions_attempted`| Integer | Total answered |
| `average_score`| Float | Cumulative score average |
| `strength` | Text (JSON) | Array of concepts scored >= 7.0 |
| `weakness` | Text (JSON) | Array of concepts scored < 6.0 |
| `mastered_concepts`| Text (JSON) | Array of concepts scored >= 8.0 |
| `questions_avoided`| Integer | Count of avoided redundant questions |
| `current_difficulty`| String(50) | Dynamically updated difficulty level |
| `updated_at` | DateTime | Timestamp of last activity |

---

## 10. API Endpoints

### 1. `POST /exam/start`
Starts or resumes an exam session.
- **Request**:
  ```json
  {
    "name": "Rupa",
    "topic": "Python",
    "difficulty": "easy"
  }
  ```
- **Response**:
  ```json
  {
    "user_id": 1,
    "exam_id": 1,
    "name": "Rupa",
    "topic": "Python",
    "current_difficulty": "easy",
    "message": "Welcome back, Rupa! Examiner memory loaded."
  }
  ```

### 2. `POST /exam/question`
Generates the next personalized question using memory and anti-repetition rules.
- **Request**:
  ```json
  {
    "user_id": 1,
    "topic": "Python",
    "difficulty": "easy"
  }
  ```
- **Response**:
  ```json
  {
    "id": 4,
    "user_id": 1,
    "topic": "Python",
    "question_text": "What is a Python list, and how does it differ from a tuple?",
    "difficulty": "easy",
    "concept": "Python Lists",
    "question_number": 1,
    "created_at": "2026-09-10T16:00:00"
  }
  ```

### 3. `POST /exam/answer`
Evaluates the student's solution, updates memory, and computes next difficulty.
- **Request**:
  ```json
  {
    "user_id": 1,
    "question_id": 4,
    "answer_text": "A list is a mutable dynamic array allowing item reassignment, whereas a tuple is immutable. Both support indexing."
  }
  ```
- **Response**:
  ```json
  {
    "answer_id": 4,
    "question_id": 4,
    "score": 9.0,
    "correct_points": ["Identified mutability and element ordering", "Provided detailed explanation"],
    "missing_points": ["Could mention memory overhead difference"],
    "feedback": "Strong demonstration of Python Lists! Your technical grasp is clear.",
    "recommended_difficulty": "medium",
    "concept_mastered": true,
    "is_weak_area": false
  }
  ```

### 4. `GET /exam/history/{user_id}`
Returns all past questions, answers, scores, and feedback for the user.

### 5. `GET /exam/progress/{user_id}`
Returns topic-wise progress summaries, average scores, and mastered concepts.

### 6. `GET /exam/analysis/{user_id}`
Generates the comprehensive pedagogical analysis for *"What My Examiner Learned About Me"*.

---

## 11. Environment Setup

Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```

Configure your preferred LLM provider in `.env`:
```env
LLM_PROVIDER=auto

# Choose one or more:
GROQ_API_KEY=gsk_your_groq_key_here
GEMINI_API_KEY=your_gemini_key_here
OPENAI_API_KEY=sk_your_openai_key_here

DATABASE_URL=sqlite:///./examiner.db
```

> **Note**: If you do not have an API key right now, leave them blank! The system automatically detects missing keys and activates its built-in smart offline heuristic engine, allowing 100% of features to work immediately.

---

## 12. Installation

Install all required packages:
```powershell
pip install -r requirements.txt
```

---

## 13. Running the Project

1. **Start the FastAPI server**:
   ```powershell
   uvicorn app.main:app --reload --port 8000
   ```

2. **Open your browser**:
   - Web App UI: `http://localhost:8000/`
   - Live Exam: `http://localhost:8000/exam`
   - Dashboard: `http://localhost:8000/dashboard`
   - Learner Analysis (WOW Screen): `http://localhost:8000/result`
   - Interactive API Docs: `http://localhost:8000/docs`

3. **Run Automated Tests**:
   ```powershell
   python -m unittest discover -s tests -p "test_*.py" -v
   ```

---

## 14. How LLM Integration Works
1. `services/llm_service.py` defines a modular interface with `generate_question()`, `evaluate_answer()`, and `generate_learning_analysis()`.
2. When an API key is present (Groq, Gemini, or OpenAI), it requests structured JSON output by setting system prompts and enforcing response formats.
3. The raw output is cleaned with regex to strip any markdown backticks, then validated using Pydantic models (`LLMQuestionOutput`, `LLMEvaluationOutput`, `LLMAnalysisOutput`).
4. If the provider fails or returns invalid formatting, the service falls back gracefully without crashing.

---

## 15. How Memory Works
`services/memory.py` is the data aggregation engine:
- `get_concept_scores()`: Groups past answers by concept and calculates the average score for each.
- `get_mastered_concepts()`: Identifies concepts with an average score >= 8.0.
- `get_weak_concepts()`: Identifies concepts with an average score < 6.0.
- `build_learning_context()`: Packages the learner's entire profile (strengths, weaknesses, mastered topics, recent question texts, and average score) into a structured dictionary that is injected into the LLM prompt.

---

## 16. How Anti-Repetition Works
Never relies solely on the LLM's memory:
1. **Normalization**: Both the generated candidate and recent questions are stripped of punctuation, lowercased, and whitespace-collapsed.
2. **Jaccard Token Similarity**: Measures token set overlap:
   $$\text{Jaccard}(A, B) = \frac{|A \cap B|}{|A \cup B|}$$
3. **SequenceMatcher Ratio**: Computes longest contiguous matching character sequences.
4. **Mastered Concept Guard**: If a generated question targets a mastered concept at an "easy" level, it is rejected, the `questions_avoided` counter increments, and difficulty escalates.
5. **Rejection & Retry**: If similarity exceeds 70%, the candidate is rejected and added as a negative constraint for regeneration.

---

## 17. How Adaptive Difficulty Works
Operates using a rolling window of recent scores:
- **Score 8.0 – 10.0** (and rolling avg >= 7.5): Promotes difficulty:
  - `Easy` $\rightarrow$ `Medium`
  - `Medium` $\rightarrow$ `Hard`
- **Score 5.0 – 7.9**: Maintains current difficulty.
- **Score 0.0 – 4.9** (and rolling avg <= 5.0): Demotes difficulty to solidify core concepts:
  - `Hard` $\rightarrow$ `Medium`
  - `Medium` $\rightarrow$ `Easy`

---

## 18. Example User Flow
1. **Rupa** opens `http://localhost:8000/`, enters her name, selects **Python**, and starts at **Easy**.
2. **Question 1**: *"What is a Python list, and how does it differ from a tuple?"*
3. **Submission**: Rupa explains mutability, indexing, and memory differences.
4. **Evaluation**: Score: **9/10**. Concept `Python Lists` is marked **Mastered**. Next difficulty: **Medium**.
5. **Question 2**: The examiner avoids asking basic list questions. Instead, it asks:
   *"How would you remove duplicate elements from a Python list without using set()? Explain time complexity."*
6. **Submission**: Rupa misses the time complexity explanation and receives **4.5/10**.
7. **Memory Update**: `Time Complexity` is logged as a **Target Weakness**.
8. **Question 3**: The examiner revisits time complexity, but using a fresh data structure scenario.
9. **Rupa finishes the exam**:
   - Screen displays: **"WHAT MY EXAMINER LEARNED ABOUT ME"**
   - **Strengths**: Lists, Tuples
   - **Weaknesses**: Time Complexity, Production Edge Cases
   - **AI Observation**: *"You understand core mechanics well, but need practice stating runtime Big-O complexity."*
   - **Next Strategy**: 60% Weak Areas, 30% New Concepts, 10% Revision.

---

## 19. Extended Capabilities & Roadmap
- ✅ **Voice Mode**: Real-time Speech-to-Text (STT dictation) and Text-to-Speech (TTS examiner voice) with audio wave animations.
- ✅ **Live Code Execution Sandbox**: Isolated subprocess runner (`/exam/run-code`) supporting Python 3 and JavaScript with timeout guards and live terminal console.
- 🔮 **Multi-user Authentication**: JWT-based authentication for team and classroom environments.
- 🔮 **Vector Semantic Search**: Integrate vector embeddings (ChromaDB) for high-dimensional semantic search across historical questions.

---

## 20. Final Interview Explanation
*Here is how you can explain this project during a technical interview:*

> **"In this project, the LLM acts as the examiner's cognitive brain, FastAPI powers the high-performance asynchronous REST backend, and SQLite stores the learner's complete chronological history.
>
> What makes this different from a standard chatbot is our custom Memory & Anti-Repetition engine. Before generating any question, the system queries the database to assemble the learner's mastered concepts, target weaknesses, and recently asked questions. It injects this memory context directly into the prompt.
>
> On top of that, we have an application-level similarity filter combining Jaccard and Levenshtein metrics to ensure the examiner never repeats questions. When the student scores above 8/10, that concept is marked mastered and the difficulty automatically scales up from Easy to Medium or Hard.
>
> When the candidate struggles, the examiner flags that concept as a weak area and revisits it later using real-world scenarios rather than the same theoretical question.
>
> Finally, the system synthesizes a deep pedagogical analysis—'What My Examiner Learned About Me'—providing candidates with actionable insights on their explanation habits and a tailored study strategy."**
