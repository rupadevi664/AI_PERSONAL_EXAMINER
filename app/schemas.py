import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# --- Exam Session Schemas ---
class ExamStartRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    topic: str = Field(..., min_length=1, max_length=100)
    difficulty: str = Field(default="easy", description="easy, medium, hard")


class ExamStartResponse(BaseModel):
    user_id: int
    exam_id: int
    name: str
    topic: str
    current_difficulty: str
    message: str


# --- Question Schemas ---
class QuestionGenerateRequest(BaseModel):
    user_id: int
    topic: str
    difficulty: Optional[str] = None


class QuestionResponse(BaseModel):
    id: int
    user_id: int
    topic: str
    question_text: str
    difficulty: str
    concept: str
    question_number: int
    created_at: datetime.datetime

    class Config:
        from_attributes = True


# --- Answer & Evaluation Schemas ---
class AnswerSubmitRequest(BaseModel):
    user_id: int
    question_id: int
    answer_text: str = Field(..., min_length=1)


class EvaluationResponse(BaseModel):
    answer_id: int
    question_id: int
    score: float
    correct_points: List[str]
    missing_points: List[str]
    feedback: str
    recommended_difficulty: str
    concept_mastered: bool
    is_weak_area: bool


# --- History & Progress Schemas ---
class AnswerHistoryItem(BaseModel):
    id: int
    question_id: int
    question_text: str
    topic: str
    difficulty: str
    concept: str
    answer_text: str
    score: float
    feedback: str
    correct_points: List[str]
    missing_points: List[str]
    created_at: datetime.datetime


class TopicProgressSummary(BaseModel):
    topic: str
    questions_attempted: int
    average_score: float
    current_difficulty: str
    strengths: List[str]
    weaknesses: List[str]
    mastered_concepts: List[str]
    questions_avoided: int


class PersonalizedAnalysisResponse(BaseModel):
    user_id: int
    name: str
    total_questions: int
    overall_average_score: float
    current_difficulty: str
    strongest_topic: Optional[str] = None
    weakest_topic: Optional[str] = None
    strengths: List[str]
    weaknesses: List[str]
    mastered_concepts: List[str]
    questions_avoided: int
    ai_observation: str
    next_exam_strategy: Dict[str, Any]
    topic_breakdown: List[TopicProgressSummary]


# --- Structured LLM Outputs ---
class LLMQuestionOutput(BaseModel):
    topic: str
    difficulty: str
    concept: str
    question: str


class LLMEvaluationOutput(BaseModel):
    score: float = Field(..., ge=0.0, le=10.0)
    correct_points: List[str] = Field(default_factory=list)
    missing_points: List[str] = Field(default_factory=list)
    feedback: str
    recommended_difficulty: str = "medium"


class LLMAnalysisOutput(BaseModel):
    observation: str
    weak_focus_percent: int = 60
    new_concepts_percent: int = 30
    revision_percent: int = 10
    learning_insights: str


# --- Reset & Export Schemas ---
class ResetProgressRequest(BaseModel):
    user_id: int
    topic: Optional[str] = None  # None resets all topics for user


class ResetProgressResponse(BaseModel):
    success: bool
    user_id: int
    topic: Optional[str]
    message: str


class ExportReportResponse(BaseModel):
    user_id: int
    user_name: str
    markdown: str
    generated_at: datetime.datetime


# --- Code Sandbox Execution Schemas ---
class CodeRunRequest(BaseModel):
    code: str = Field(..., min_length=1, description="Code snippet to execute")
    language: str = Field(default="python", description="python or javascript")
    timeout_seconds: Optional[float] = Field(default=4.0, ge=0.5, le=10.0)


class CodeRunResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: float
    error: Optional[str] = None
    language: str


