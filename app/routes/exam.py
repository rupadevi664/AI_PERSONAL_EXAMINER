from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Question, Answer, UserProgress
from app.schemas import (
    ExamStartRequest,
    ExamStartResponse,
    QuestionGenerateRequest,
    QuestionResponse,
    AnswerSubmitRequest,
    EvaluationResponse,
    ResetProgressRequest,
    ResetProgressResponse,
    CodeRunRequest,
    CodeRunResponse
)
from app.services import examiner
from app.services.code_runner import execute_code_sandbox

router = APIRouter(prefix="/exam", tags=["Exam"])


@router.post("/start", response_model=ExamStartResponse, status_code=status.HTTP_201_CREATED)
def start_exam(payload: ExamStartRequest, db: Session = Depends(get_db)):
    """
    Initializes or retrieves a user by name, sets up topic progress tracking,
    and starts the examination session.
    """
    cleaned_name = payload.name.strip()
    cleaned_topic = payload.topic.strip()
    valid_diffs = ["easy", "medium", "hard"]
    cleaned_diff = payload.difficulty.lower().strip() if payload.difficulty.lower().strip() in valid_diffs else "easy"

    if not cleaned_name:
        raise HTTPException(status_code=400, detail="User name cannot be empty")
    if not cleaned_topic:
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    # Retrieve existing user or create a new user profile
    user = db.query(User).filter(User.name.ilike(cleaned_name)).first()
    if not user:
        user = User(name=cleaned_name)
        db.add(user)
        db.commit()
        db.refresh(user)

    # Initialize or fetch topic progress record
    progress = (
        db.query(UserProgress)
        .filter(UserProgress.user_id == user.id, UserProgress.topic.ilike(cleaned_topic))
        .first()
    )
    if not progress:
        progress = UserProgress(
            user_id=user.id,
            topic=cleaned_topic,
            current_difficulty=cleaned_diff,
            questions_attempted=0,
            average_score=0.0,
            questions_avoided=0
        )
        db.add(progress)
        db.commit()
        db.refresh(progress)

    return ExamStartResponse(
        user_id=user.id,
        exam_id=progress.id,
        name=user.name,
        topic=progress.topic,
        current_difficulty=progress.current_difficulty,
        message=f"Welcome back, {user.name}! Examiner memory loaded for topic '{cleaned_topic}'."
    )


@router.post("/question", response_model=QuestionResponse)
def generate_question(payload: QuestionGenerateRequest, db: Session = Depends(get_db)):
    """
    Generates the next personalized question using historical memory,
    anti-repetition safeguards, and adaptive difficulty.
    """
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        db_question = examiner.generate_personalized_question(
            user_id=payload.user_id,
            topic=payload.topic,
            target_difficulty=payload.difficulty,
            db=db
        )
        # Compute question number for this user in this topic
        count = (
            db.query(Question)
            .filter(Question.user_id == payload.user_id, Question.topic.ilike(payload.topic))
            .count()
        )
        return QuestionResponse(
            id=db_question.id,
            user_id=db_question.user_id,
            topic=db_question.topic,
            question_text=db_question.question_text,
            difficulty=db_question.difficulty,
            concept=db_question.concept,
            question_number=count,
            created_at=db_question.created_at
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Question generation failed: {str(e)}")


@router.post("/answer", response_model=EvaluationResponse)
def submit_answer(payload: AnswerSubmitRequest, db: Session = Depends(get_db)):
    """
    Evaluates learner's answer, scores technical depth, detects missing nuances,
    updates memory profile, and computes next difficulty.
    """
    if not payload.answer_text or not payload.answer_text.strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty")

    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    question = db.query(Question).filter(Question.id == payload.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    try:
        db_ans, eval_out, new_diff = examiner.evaluate_and_record_answer(
            user_id=payload.user_id,
            question_id=payload.question_id,
            answer_text=payload.answer_text,
            db=db
        )
        return EvaluationResponse(
            answer_id=db_ans.id,
            question_id=question.id,
            score=eval_out.score,
            correct_points=eval_out.correct_points,
            missing_points=eval_out.missing_points,
            feedback=eval_out.feedback,
            recommended_difficulty=new_diff,
            concept_mastered=(eval_out.score >= 8.0),
            is_weak_area=(eval_out.score < 5.0)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Answer evaluation failed: {str(e)}")


@router.post("/reset", response_model=ResetProgressResponse)
def reset_progress(payload: ResetProgressRequest, db: Session = Depends(get_db)):
    """
    Resets progress and question history for a user, optionally scoped to a single topic.
    """
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.topic and payload.topic.strip().lower() != "all":
        cleaned_topic = payload.topic.strip()
        # Delete questions (and cascade answers) for this topic
        topic_questions = db.query(Question).filter(
            Question.user_id == user.id,
            Question.topic.ilike(cleaned_topic)
        ).all()
        for q in topic_questions:
            db.delete(q)

        # Delete UserProgress record for topic
        db.query(UserProgress).filter(
            UserProgress.user_id == user.id,
            UserProgress.topic.ilike(cleaned_topic)
        ).delete()
        db.commit()

        return ResetProgressResponse(
            success=True,
            user_id=user.id,
            topic=cleaned_topic,
            message=f"Reset memory and progress for topic '{cleaned_topic}'."
        )
    else:
        # Reset all progress and questions for user
        db.query(Question).filter(Question.user_id == user.id).delete()
        db.query(UserProgress).filter(UserProgress.user_id == user.id).delete()
        db.commit()

        return ResetProgressResponse(
            success=True,
            user_id=user.id,
            topic=None,
            message="Reset all memory, scores, and history for user."
        )


@router.post("/run-code", response_model=CodeRunResponse)
def run_code_endpoint(payload: CodeRunRequest):
    """
    Executes a code snippet inside an isolated sandbox subprocess with strict timeouts.
    Enables learners to test and verify solutions before submitting for evaluation.
    """
    res = execute_code_sandbox(
        code=payload.code,
        language=payload.language,
        timeout=payload.timeout_seconds or 4.0
    )
    return CodeRunResponse(**res)


