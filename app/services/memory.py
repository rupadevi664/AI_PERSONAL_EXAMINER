import json
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models import User, Question, Answer, UserProgress


def get_user_history(user_id: int, db: Session, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves chronological answers and associated questions for a user."""
    answers = (
        db.query(Answer)
        .filter(Answer.user_id == user_id)
        .order_by(desc(Answer.created_at))
        .limit(limit)
        .all()
    )
    history = []
    for ans in answers:
        q = ans.question
        history.append({
            "answer_id": ans.id,
            "question_id": q.id if q else None,
            "question_text": q.question_text if q else "",
            "topic": q.topic if q else "",
            "difficulty": q.difficulty if q else "",
            "concept": q.concept if q else "General",
            "answer_text": ans.answer_text,
            "score": ans.score,
            "feedback": ans.feedback,
            "correct_points": json.loads(ans.correct_points or "[]"),
            "missing_points": json.loads(ans.missing_points or "[]"),
            "created_at": ans.created_at.isoformat() if ans.created_at else ""
        })
    return history


def get_topic_history(user_id: int, topic: str, db: Session, limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieves past attempts strictly within a given technical topic."""
    answers = (
        db.query(Answer)
        .join(Question, Answer.question_id == Question.id)
        .filter(Answer.user_id == user_id, Question.topic.ilike(topic))
        .order_by(desc(Answer.created_at))
        .limit(limit)
        .all()
    )
    results = []
    for ans in answers:
        q = ans.question
        results.append({
            "question_text": q.question_text,
            "concept": q.concept,
            "difficulty": q.difficulty,
            "score": ans.score,
            "feedback": ans.feedback,
            "created_at": ans.created_at
        })
    return results


def get_concept_scores(user_id: int, topic: Optional[str], db: Session) -> Dict[str, List[float]]:
    """Gathers all scores per concept to calculate concept-level mastery or weakness."""
    query = (
        db.query(Question.concept, Answer.score)
        .join(Answer, Question.id == Answer.question_id)
        .filter(Answer.user_id == user_id)
    )
    if topic:
        query = query.filter(Question.topic.ilike(topic))
    
    rows = query.all()
    concept_scores: Dict[str, List[float]] = {}
    for concept, score in rows:
        c_clean = (concept or "General").strip().title()
        if c_clean not in concept_scores:
            concept_scores[c_clean] = []
        concept_scores[c_clean].append(score)
    return concept_scores


def get_mastered_concepts(user_id: int, topic: Optional[str], db: Session) -> List[str]:
    """
    Returns concepts where user's average score is >= 8.0 with at least 1 attempt.
    """
    scores_map = get_concept_scores(user_id, topic, db)
    mastered = []
    for concept, scores in scores_map.items():
        avg = sum(scores) / len(scores)
        if avg >= 8.0:
            mastered.append(concept)
    return mastered


def get_weak_concepts(user_id: int, topic: Optional[str], db: Session) -> List[str]:
    """
    Returns concepts where user's average score is < 6.0.
    """
    scores_map = get_concept_scores(user_id, topic, db)
    weak = []
    for concept, scores in scores_map.items():
        avg = sum(scores) / len(scores)
        if avg < 6.0:
            weak.append(concept)
    return weak


def get_strong_topics(user_id: int, db: Session) -> List[str]:
    """Returns topics where user average score is >= 7.5."""
    progress_records = db.query(UserProgress).filter(UserProgress.user_id == user_id).all()
    strong = [p.topic for p in progress_records if p.average_score >= 7.5]
    return strong


def get_weak_topics(user_id: int, db: Session) -> List[str]:
    """Returns topics where user average score is < 6.0 and questions attempted > 0."""
    progress_records = db.query(UserProgress).filter(UserProgress.user_id == user_id).all()
    weak = [p.topic for p in progress_records if p.average_score < 6.0 and p.questions_attempted > 0]
    return weak


def get_recent_questions(user_id: int, topic: Optional[str], db: Session, limit: int = 10) -> List[str]:
    """Fetches the text of recently asked questions for the user to prevent repetition."""
    query = db.query(Question.question_text).filter(Question.user_id == user_id)
    if topic:
        query = query.filter(Question.topic.ilike(topic))
    recent = query.order_by(desc(Question.created_at)).limit(limit).all()
    return [r[0] for r in recent]


def build_learning_context(user_id: int, topic: str, db: Session) -> Dict[str, Any]:
    """
    Builds the personalized memory context for the LLM examiner before question generation.
    Returns:
    - user_name
    - topic
    - mastered_concepts
    - weak_concepts
    - strengths
    - avg_score
    - recent_questions
    - performance_summary
    """
    user = db.query(User).filter(User.id == user_id).first()
    user_name = user.name if user else "Student"

    # Progress record for topic
    progress = (
        db.query(UserProgress)
        .filter(UserProgress.user_id == user_id, UserProgress.topic.ilike(topic))
        .first()
    )

    avg_score = round(progress.average_score, 1) if progress else 0.0
    current_difficulty = progress.current_difficulty if progress else "easy"

    concept_scores = get_concept_scores(user_id, topic, db)
    mastered = get_mastered_concepts(user_id, topic, db)
    weak = get_weak_concepts(user_id, topic, db)

    # Concept breakdown for prompt
    perf_lines = []
    for concept, scores in concept_scores.items():
        c_avg = round(sum(scores) / len(scores), 1)
        perf_lines.append(f"- {concept}: {c_avg}/10 ({len(scores)} attempts)")

    performance_summary = "\n".join(perf_lines) if perf_lines else "No prior questions answered in this topic."
    recent_qs = get_recent_questions(user_id, topic, db, limit=8)
    formatted_recent_qs = "\n".join(f"- \"{q}\"" for q in recent_qs) if recent_qs else "None (first question)"

    strengths = [c for c, scores in concept_scores.items() if (sum(scores) / len(scores)) >= 7.0]

    return {
        "user_name": user_name,
        "topic": topic,
        "difficulty": current_difficulty,
        "avg_score": avg_score,
        "mastered_concepts": ", ".join(mastered) if mastered else "None yet",
        "weak_concepts": ", ".join(weak) if weak else "None identified yet",
        "strengths": ", ".join(strengths) if strengths else "Assessing baseline",
        "recent_questions": formatted_recent_qs,
        "performance_summary": performance_summary,
        "raw_mastered": mastered,
        "raw_weak": weak,
        "raw_recent": recent_qs
    }
