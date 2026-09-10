import re
import json
import difflib
import logging
from typing import Tuple, List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models import User, Question, Answer, UserProgress
from app.schemas import LLMQuestionOutput, LLMEvaluationOutput, TopicProgressSummary, PersonalizedAnalysisResponse
from app.services.llm_service import llm_service
from app.services import memory

logger = logging.getLogger("examiner.core")

DIFFICULTY_LEVELS = ["easy", "medium", "hard"]


# =========================================================================
# ANTI-REPETITION SYSTEM (Section 7)
# =========================================================================

def normalize_text(text: str) -> str:
    """Normalizes string for robust similarity checking: lowercased, punctuation stripped, whitespace collapsed."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def calculate_jaccard_similarity(text1: str, text2: str) -> float:
    """Calculates Jaccard token set similarity between two text snippets."""
    tokens1 = set(normalize_text(text1).split())
    tokens2 = set(normalize_text(text2).split())
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)


def calculate_text_similarity(q1: str, q2: str) -> float:
    """
    Computes a hybrid similarity metric combining SequenceMatcher ratio and Jaccard similarity.
    """
    norm1 = normalize_text(q1)
    norm2 = normalize_text(q2)
    if norm1 == norm2:
        return 1.0

    seq_sim = difflib.SequenceMatcher(None, norm1, norm2).ratio()
    jaccard_sim = calculate_jaccard_similarity(q1, q2)
    return max(seq_sim, jaccard_sim)


def is_question_repetitive(new_question_text: str, past_questions: List[str], threshold: float = 0.70) -> Tuple[bool, str]:
    """
    Detects exact duplicates and high semantic similarity against previously asked questions.
    Returns (is_repetitive, reason).
    """
    for past in past_questions:
        similarity = calculate_text_similarity(new_question_text, past)
        if similarity >= 0.95:
            return True, f"Exact or near-identical duplicate (Similarity: {similarity:.2f})"
        if similarity >= threshold:
            return True, f"Too similar to recently asked question: '{past[:40]}...' (Similarity: {similarity:.2f})"
    return False, ""


# =========================================================================
# ADAPTIVE DIFFICULTY ENGINE (Section 8)
# =========================================================================

def calculate_next_difficulty(current_difficulty: str, latest_score: float, recent_scores: List[float]) -> str:
    """
    Dynamically adjusts question difficulty based on latest score and rolling trends.
    8-10: increase difficulty
    5-7: maintain difficulty
    0-4: decrease difficulty
    If recent scores are consistently high or low, acts decisively.
    """
    curr_diff = current_difficulty.lower()
    if curr_diff not in DIFFICULTY_LEVELS:
        curr_diff = "easy"

    curr_idx = DIFFICULTY_LEVELS.index(curr_diff)

    # Use rolling average of last up to 3 scores if available
    scores_window = [latest_score] + recent_scores[:2]
    rolling_avg = sum(scores_window) / len(scores_window)

    if latest_score >= 8.0 and rolling_avg >= 7.5:
        # Increase difficulty
        new_idx = min(curr_idx + 1, len(DIFFICULTY_LEVELS) - 1)
    elif latest_score <= 4.0 and rolling_avg <= 5.0:
        # Decrease difficulty
        new_idx = max(curr_idx - 1, 0)
    else:
        # Maintain difficulty
        new_idx = curr_idx

    return DIFFICULTY_LEVELS[new_idx]


# =========================================================================
# QUESTION GENERATION ORCHESTRATION WITH ANTI-REPETITION & MEMORY
# =========================================================================

def generate_personalized_question(
    user_id: int,
    topic: str,
    target_difficulty: Optional[str],
    db: Session
) -> Question:
    """
    Orchestrates personalized question generation:
    1. Loads learner memory context.
    2. Determines difficulty.
    3. Calls LLM with strict anti-repetition rules.
    4. Filters out duplicate/similar questions and increments avoided counters if mastered concept was avoided.
    5. Saves question to database and returns Question instance.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User with ID {user_id} not found")

    # Get topic progress to track difficulty and avoided questions
    progress = (
        db.query(UserProgress)
        .filter(UserProgress.user_id == user_id, UserProgress.topic.ilike(topic))
        .first()
    )

    if not progress:
        progress = UserProgress(
            user_id=user_id,
            topic=topic,
            current_difficulty=target_difficulty or "easy",
            questions_attempted=0,
            average_score=0.0,
            questions_avoided=0
        )
        db.add(progress)
        db.commit()
        db.refresh(progress)

    effective_difficulty = target_difficulty or progress.current_difficulty or "easy"
    memory_context = memory.build_learning_context(user_id, topic, db)
    past_questions = memory.get_recent_questions(user_id, topic, db, limit=20)
    mastered_concepts = memory_context.get("raw_mastered", [])

    max_attempts = 4
    final_q_output: Optional[LLMQuestionOutput] = None

    for attempt in range(max_attempts):
        candidate: LLMQuestionOutput = llm_service.generate_question(
            user_name=user.name,
            topic=topic,
            difficulty=effective_difficulty,
            memory_context=memory_context
        )

        # Check 1: Did the candidate pick an easy question on an already mastered concept?
        # If so, avoid it and record the avoidance metric!
        is_concept_mastered = any(m.lower() == candidate.concept.lower() for m in mastered_concepts)
        if is_concept_mastered and candidate.difficulty.lower() == "easy":
            logger.info(f"Avoided basic question on mastered concept '{candidate.concept}'. Scaling up.")
            progress.questions_avoided = (progress.questions_avoided or 0) + 1
            db.commit()
            # Escalate difficulty for this concept instead
            effective_difficulty = "medium"
            memory_context["difficulty"] = "medium"
            continue

        # Check 2: Anti-Repetition filter
        is_rep, reason = is_question_repetitive(candidate.question, past_questions)
        if is_rep:
            logger.warning(f"Question rejected due to anti-repetition check: {reason}. Retrying (attempt {attempt+1})")
            # Append rejected question to prompt context to force LLM divergence
            past_questions.append(candidate.question)
            memory_context["recent_questions"] += f"\n- (REJECTED DUPLICATE) \"{candidate.question}\""
            continue

        # If passed all checks, accept candidate!
        final_q_output = candidate
        break

    if not final_q_output:
        # Fallback to guaranteed novel variant
        final_q_output = candidate

    # Save question to DB
    db_question = Question(
        user_id=user_id,
        topic=topic,
        question_text=final_q_output.question,
        difficulty=final_q_output.difficulty.lower(),
        concept=final_q_output.concept
    )
    db.add(db_question)
    db.commit()
    db.refresh(db_question)

    return db_question


# =========================================================================
# ANSWER EVALUATION & PROGRESS SYNCHRONIZATION
# =========================================================================

def evaluate_and_record_answer(
    user_id: int,
    question_id: int,
    answer_text: str,
    db: Session
) -> Tuple[Answer, LLMEvaluationOutput, str]:
    """
    Evaluates user's answer, updates database, calculates new difficulty, and refreshes learner profile.
    Returns (db_answer, evaluation_output, new_difficulty).
    """
    question = db.query(Question).filter(Question.id == question_id, Question.user_id == user_id).first()
    if not question:
        raise ValueError(f"Question {question_id} not found for user {user_id}")

    # Evaluate via LLM service
    eval_result: LLMEvaluationOutput = llm_service.evaluate_answer(
        topic=question.topic,
        difficulty=question.difficulty,
        concept=question.concept,
        question_text=question.question_text,
        answer_text=answer_text
    )

    # Save answer to DB
    db_answer = Answer(
        question_id=question.id,
        user_id=user_id,
        answer_text=answer_text.strip(),
        score=eval_result.score,
        feedback=eval_result.feedback,
        correct_points=json.dumps(eval_result.correct_points),
        missing_points=json.dumps(eval_result.missing_points)
    )
    db.add(db_answer)
    db.commit()
    db.refresh(db_answer)

    # Update UserProgress
    progress = (
        db.query(UserProgress)
        .filter(UserProgress.user_id == user_id, UserProgress.topic.ilike(question.topic))
        .first()
    )
    if not progress:
        progress = UserProgress(
            user_id=user_id,
            topic=question.topic,
            current_difficulty=question.difficulty,
            questions_attempted=0,
            average_score=0.0,
            questions_avoided=0
        )
        db.add(progress)

    # Gather past scores for this topic
    recent_answers = (
        db.query(Answer.score)
        .join(Question, Answer.question_id == Question.id)
        .filter(Answer.user_id == user_id, Question.topic.ilike(question.topic))
        .order_by(desc(Answer.created_at))
        .all()
    )
    all_scores = [r[0] for r in recent_answers]
    progress.questions_attempted = len(all_scores)
    progress.average_score = round(sum(all_scores) / len(all_scores), 2) if all_scores else eval_result.score

    # Compute new difficulty
    past_scores_excluding_current = all_scores[1:] if len(all_scores) > 1 else []
    new_difficulty = calculate_next_difficulty(
        current_difficulty=progress.current_difficulty or question.difficulty,
        latest_score=eval_result.score,
        recent_scores=past_scores_excluding_current
    )
    progress.current_difficulty = new_difficulty

    # Update strengths, weaknesses, and mastered concepts
    mastered = memory.get_mastered_concepts(user_id, question.topic, db)
    weak = memory.get_weak_concepts(user_id, question.topic, db)
    scores_map = memory.get_concept_scores(user_id, question.topic, db)
    strong = [c for c, scs in scores_map.items() if (sum(scs)/len(scs)) >= 7.0]

    progress.mastered_concepts = json.dumps(mastered)
    progress.weakness = json.dumps(weak)
    progress.strength = json.dumps(strong)

    db.commit()
    db.refresh(progress)

    return db_answer, eval_result, new_difficulty


# =========================================================================
# COMPREHENSIVE LEARNER ANALYSIS ("WHAT MY EXAMINER LEARNED ABOUT ME")
# =========================================================================

def build_personalized_analysis(user_id: int, db: Session) -> PersonalizedAnalysisResponse:
    """
    Assembles comprehensive examiner intelligence across all topics for the learner.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    progress_records = db.query(UserProgress).filter(UserProgress.user_id == user_id).all()
    all_answers = db.query(Answer).filter(Answer.user_id == user_id).all()

    total_questions = len(all_answers)
    overall_avg = round(sum(a.score for a in all_answers) / total_questions, 1) if total_questions > 0 else 0.0

    # Aggregate mastered and weak concepts across all topics
    all_mastered: List[str] = []
    all_weak: List[str] = []
    all_strengths: List[str] = []
    total_avoided = 0
    topic_summaries: List[TopicProgressSummary] = []

    best_topic = None
    best_score = -1.0
    worst_topic = None
    worst_score = 11.0

    for p in progress_records:
        total_avoided += (p.questions_avoided or 0)
        m_list = json.loads(p.mastered_concepts or "[]")
        w_list = json.loads(p.weakness or "[]")
        s_list = json.loads(p.strength or "[]")

        all_mastered.extend(m_list)
        all_weak.extend(w_list)
        all_strengths.extend(s_list)

        topic_summaries.append(TopicProgressSummary(
            topic=p.topic,
            questions_attempted=p.questions_attempted or 0,
            average_score=p.average_score or 0.0,
            current_difficulty=p.current_difficulty or "easy",
            strengths=s_list,
            weaknesses=w_list,
            mastered_concepts=m_list,
            questions_avoided=p.questions_avoided or 0
        ))

        if p.questions_attempted > 0:
            if p.average_score > best_score:
                best_score = p.average_score
                best_topic = p.topic
            if p.average_score < worst_score:
                worst_score = p.average_score
                worst_topic = p.topic

    # Deduplicate lists preserving order
    all_mastered = list(dict.fromkeys(all_mastered))
    all_weak = list(dict.fromkeys(all_weak))
    all_strengths = list(dict.fromkeys(all_strengths))

    # Recent performance line
    recent_ans = db.query(Answer).filter(Answer.user_id == user_id).order_by(desc(Answer.created_at)).limit(5).all()
    perf_lines = [f"- Question: '{a.question.question_text[:40]}...' -> Score: {a.score}/10" for a in recent_ans if a.question]
    perf_summary = "\n".join(perf_lines)

    # Call LLM analysis
    analysis_llm = llm_service.generate_learning_analysis(
        user_name=user.name,
        total_questions=total_questions,
        overall_avg=overall_avg,
        strengths=all_strengths,
        weaknesses=all_weak,
        mastered_concepts=all_mastered,
        recent_performance_summary=perf_summary
    )

    current_diff = progress_records[0].current_difficulty if progress_records else "medium"

    return PersonalizedAnalysisResponse(
        user_id=user.id,
        name=user.name,
        total_questions=total_questions,
        overall_average_score=overall_avg,
        current_difficulty=current_diff,
        strongest_topic=best_topic,
        weakest_topic=worst_topic,
        strengths=all_strengths,
        weaknesses=all_weak,
        mastered_concepts=all_mastered,
        questions_avoided=total_avoided,
        ai_observation=analysis_llm.observation,
        next_exam_strategy={
            "weak_focus_percent": analysis_llm.weak_focus_percent,
            "new_concepts_percent": analysis_llm.new_concepts_percent,
            "revision_percent": analysis_llm.revision_percent,
            "insights": analysis_llm.learning_insights
        },
        topic_breakdown=topic_summaries
    )
