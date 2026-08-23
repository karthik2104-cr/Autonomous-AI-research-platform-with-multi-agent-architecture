import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


class ResearchRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    RESEARCHING = "RESEARCHING"
    ANALYZING = "ANALYZING"
    VERIFYING = "VERIFYING"
    GENERATING = "GENERATING"
    DONE = "DONE"
    FAILED = "FAILED"


class PlanStepStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    FAILED = "FAILED"


class ToolHint(str, enum.Enum):
    WEB_SEARCH = "web_search"
    VECTOR_RETRIEVE = "vector_retrieve"
    DB_QUERY = "db_query"


class SourceType(str, enum.Enum):
    WEB = "web"
    DOCUMENT = "document"
    DATABASE = "database"


def _enum_type(enum_cls, name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        values_callable=lambda items: [item.value for item in items],
    )


class ResearchRun(Base):
    __tablename__ = "research_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ResearchRunStatus] = mapped_column(
        _enum_type(ResearchRunStatus, "research_run_status"),
        nullable=False,
        default=ResearchRunStatus.PENDING,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Analysis-stage meta (contradictions + gaps) kept on the run so VERIFYING /
    # GENERATING can read it without waiting for a Report row.
    analysis_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    plan_steps: Mapped[list["PlanStep"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
        order_by="PlanStep.order_index",
    )
    claims: Mapped[list["Claim"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    report: Mapped["Report | None"] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
        uselist=False,
    )
    llm_calls: Mapped[list["LLMCallLog"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )


class PlanStep(Base):
    __tablename__ = "plan_steps"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sub_question: Mapped[str] = mapped_column(Text, nullable=False)
    tool_hint: Mapped[ToolHint | None] = mapped_column(
        _enum_type(ToolHint, "tool_hint"),
        nullable=True,
    )
    status: Mapped[PlanStepStatus] = mapped_column(
        _enum_type(PlanStepStatus, "plan_step_status"),
        nullable=False,
        default=PlanStepStatus.PENDING,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    research_run: Mapped[ResearchRun] = relationship(back_populates="plan_steps")
    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="plan_step",
        cascade="all, delete-orphan",
    )


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_step_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("plan_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[SourceType] = mapped_column(
        _enum_type(SourceType, "source_type"),
        nullable=False,
    )
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    plan_step: Mapped[PlanStep] = relationship(back_populates="evidence")
    citations: Mapped[list["Citation"]] = relationship(back_populates="evidence")


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    research_run: Mapped[ResearchRun] = relationship(back_populates="claims")
    citations: Mapped[list["Citation"]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
    )
    verification_result: Mapped["VerificationResult | None"] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    claim: Mapped[Claim] = relationship(back_populates="citations")
    evidence: Mapped[Evidence] = relationship(back_populates="citations")


class VerificationResult(Base):
    __tablename__ = "verification_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    is_supported: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    claim: Mapped[Claim] = relationship(back_populates="verification_result")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    content_pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    research_run: Mapped[ResearchRun] = relationship(back_populates="report")


class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    research_run: Mapped[ResearchRun] = relationship(back_populates="llm_calls")
