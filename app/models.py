import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now)

    # Relationships
    questions = relationship("Question", back_populates="user", cascade="all, delete-orphan")
    answers = relationship("Answer", back_populates="user", cascade="all, delete-orphan")
    progress_records = relationship("UserProgress", back_populates="user", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    topic = Column(String(100), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    difficulty = Column(String(50), nullable=False, default="easy")
    concept = Column(String(150), nullable=False, default="general")
    created_at = Column(DateTime, default=utc_now)

    # Relationships
    user = relationship("User", back_populates="questions")
    answers = relationship("Answer", back_populates="question", cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    answer_text = Column(Text, nullable=False)
    score = Column(Float, nullable=False)  # 0 to 10
    feedback = Column(Text, nullable=False)
    correct_points = Column(Text, default="[]")  # JSON encoded list of strings
    missing_points = Column(Text, default="[]")  # JSON encoded list of strings
    created_at = Column(DateTime, default=utc_now)

    # Relationships
    user = relationship("User", back_populates="answers")
    question = relationship("Question", back_populates="answers")


class UserProgress(Base):
    __tablename__ = "user_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    topic = Column(String(100), nullable=False, index=True)
    questions_attempted = Column(Integer, default=0)
    average_score = Column(Float, default=0.0)
    strength = Column(Text, default="[]")           # JSON encoded list of strong concepts
    weakness = Column(Text, default="[]")           # JSON encoded list of weak concepts
    mastered_concepts = Column(Text, default="[]")  # JSON encoded list of mastered concepts
    questions_avoided = Column(Integer, default=0)  # Counter for questions avoided due to mastery
    current_difficulty = Column(String(50), default="easy")
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    user = relationship("User", back_populates="progress_records")
