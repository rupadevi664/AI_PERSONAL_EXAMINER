import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import AnswerHistoryItem, TopicProgressSummary, PersonalizedAnalysisResponse, ExportReportResponse
from app.services import memory, examiner

router = APIRouter(prefix="/exam", tags=["Progress & Analytics"])


@router.get("/history/{user_id}", response_model=List[AnswerHistoryItem])
def get_user_history_endpoint(user_id: int, db: Session = Depends(get_db)):
    """
    Returns complete chronological history of questions, user answers, scores, and feedback.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    raw_history = memory.get_user_history(user_id, db)
    history_items = []
    for h in raw_history:
        history_items.append(AnswerHistoryItem(
            id=h["answer_id"],
            question_id=h["question_id"],
            question_text=h["question_text"],
            topic=h["topic"],
            difficulty=h["difficulty"],
            concept=h["concept"],
            answer_text=h["answer_text"],
            score=h["score"],
            feedback=h["feedback"],
            correct_points=h["correct_points"],
            missing_points=h["missing_points"],
            created_at=h["created_at"]
        ))
    return history_items


@router.get("/progress/{user_id}", response_model=List[TopicProgressSummary])
def get_user_progress_endpoint(user_id: int, db: Session = Depends(get_db)):
    """
    Returns topic-by-topic analytics, scores, current difficulty, and strengths/weaknesses.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    analysis = examiner.build_personalized_analysis(user_id, db)
    return analysis.topic_breakdown


@router.get("/analysis/{user_id}", response_model=PersonalizedAnalysisResponse)
def get_personalized_analysis_endpoint(user_id: int, db: Session = Depends(get_db)):
    """
    Returns the comprehensive AI Personalized Examiner Report:
    'WHAT MY EXAMINER LEARNED ABOUT ME'
    Includes cognitive observations, mastered concepts, weaknesses, and custom study strategy.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        return examiner.build_personalized_analysis(user_id, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis computation failed: {str(e)}")


def _generate_markdown_report(user: User, analysis: PersonalizedAnalysisResponse, history: List[dict]) -> str:
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        f"# AI Personal Examiner - Pedagogical Report",
        f"> *“An AI examiner that remembers what I know.”*",
        f"",
        f"- **Learner Name**: {user.name}",
        f"- **Report Generated**: {now_str}",
        f"- **Overall Average Score**: {analysis.overall_average_score} / 10.0",
        f"- **Questions Attempted**: {analysis.total_questions}",
        f"- **Current Difficulty**: {analysis.current_difficulty.upper()}",
        f"- **Redundant Questions Avoided**: {analysis.questions_avoided}",
        f"",
        f"---",
        f"",
        f"## 1. AI Examiner Observation",
        f"> {analysis.ai_observation}",
        f"",
        f"---",
        f"",
        f"## 2. Mastery & Weakness Matrix",
        f"",
        f"### Mastered Concepts (Score >= 8.0/10)",
    ]

    if analysis.mastered_concepts:
        for m in analysis.mastered_concepts:
            lines.append(f"- **✓ {m}** (Skipped at basic levels; tested with advanced scenarios)")
    else:
        lines.append("- *No concepts formally mastered yet (requires >= 8.0/10 average).*")

    lines.extend([
        f"",
        f"### Target Weaknesses (Score < 6.0/10)",
    ])

    if analysis.weaknesses:
        for w in analysis.weaknesses:
            lines.append(f"- **⚠ {w}** (Flagged for reinforcement with novel real-world problems)")
    else:
        lines.append("- *No critical weaknesses detected.*")

    strat = analysis.next_exam_strategy or {}
    lines.extend([
        f"",
        f"---",
        f"",
        f"## 3. Next Exam Strategy Distribution",
        f"- **{strat.get('weak_focus_percent', 60)}% Target Weak Areas**: Deep dives into problem domains.",
        f"- **{strat.get('new_concepts_percent', 30)}% New Conceptual Frontiers**: Expanding knowledge boundary.",
        f"- **{strat.get('revision_percent', 10)}% Mastered Concepts Revision**: High-level architecture retention.",
        f"",
        f"**Pedagogical Guidance**:",
        f"{strat.get('insights', 'Practice consistent explanations with code syntax and time complexity.')}",
        f"",
        f"---",
        f"",
        f"## 4. Topic Competency Breakdown",
        f"",
        f"| Topic | Questions Attempted | Average Score | Difficulty Tier | Avoided Redundancies |",
        f"| :--- | :---: | :---: | :---: | :---: |",
    ])

    for tb in analysis.topic_breakdown:
        lines.append(f"| {tb.topic} | {tb.questions_attempted} | {tb.average_score}/10 | {tb.current_difficulty.upper()} | {tb.questions_avoided} |")

    lines.extend([
        f"",
        f"---",
        f"",
        f"## 5. Chronological Question & Answer Audit Trail",
        f"",
    ])

    if not history:
        lines.append("*No questions recorded in this session.*")
    else:
        for idx, h in enumerate(history, 1):
            score_badge = f"{h['score']}/10"
            lines.extend([
                f"### Question #{idx}: {h['concept']} ({h['difficulty'].upper()} - {h['topic']})",
                f"- **Question**: {h['question_text']}",
                f"- **Learner Answer**: *\"{h['answer_text']}\"*",
                f"- **Score**: `{score_badge}`",
                f"- **Examiner Feedback**: {h['feedback']}",
                f"- **Points Covered**: {', '.join(h['correct_points']) if h['correct_points'] else 'None'}",
                f"- **Missing Nuances**: {', '.join(h['missing_points']) if h['missing_points'] else 'None'}",
                f"",
            ])

    lines.extend([
        f"---",
        f"*Report generated automatically by AI Personal Examiner Engine.*"
    ])

    return "\n".join(lines)


@router.get("/export/{user_id}", response_model=ExportReportResponse)
def export_report_endpoint(user_id: int, db: Session = Depends(get_db)):
    """
    Generates structured Markdown report for the learner.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    analysis = examiner.build_personalized_analysis(user_id, db)
    raw_history = memory.get_user_history(user_id, db, limit=100)
    md_content = _generate_markdown_report(user, analysis, raw_history)

    return ExportReportResponse(
        user_id=user.id,
        user_name=user.name,
        markdown=md_content,
        generated_at=datetime.datetime.now(datetime.timezone.utc)
    )


@router.get("/export/{user_id}/download")
def download_report_endpoint(user_id: int, db: Session = Depends(get_db)):
    """
    Returns the report directly as a downloadable Markdown file (.md).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    analysis = examiner.build_personalized_analysis(user_id, db)
    raw_history = memory.get_user_history(user_id, db, limit=100)
    md_content = _generate_markdown_report(user, analysis, raw_history)

    filename = f"examiner_report_{user.name.lower().replace(' ', '_')}.md"
    return Response(
        content=md_content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

