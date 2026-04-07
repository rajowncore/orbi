"""
Orbi — Provisioning Workflow DB Models

Two tables:
  ProvisioningWorkflow — one row per workflow instance
  ProvisioningStep     — one row per step execution (append-only log)
"""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Enum, ForeignKey, Integer
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.provisioning import WorkflowStatus, StepStatus, WorkflowType


def _uid() -> str:
    return str(uuid.uuid4())

def _now() -> datetime:
    return datetime.utcnow()


class ProvisioningWorkflow(Base):
    """
    One row per provisioning workflow instance.
    Tracks overall status and the shared context passed between steps.
    """
    __tablename__ = "provisioning_workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id"), nullable=False)
    subscription_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workflow_type: Mapped[WorkflowType] = mapped_column(Enum(WorkflowType), nullable=False)
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus), nullable=False, default=WorkflowStatus.PENDING
    )

    # Shared context — input params + outputs accumulated across steps
    # e.g. { "msisdn": "+447700...", "iccid": "894450...", "service_uuid": "Mobile_SIM_...",
    #         "hss_subscriber_id": "123", "hss_msisdn_id": "456", "cgrates_tenant": "cgrates.org" }
    context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Error info if failed
    error_message: Mapped[str | None] = mapped_column(Text)
    error_step: Mapped[str | None] = mapped_column(String(128))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationships
    steps: Mapped[list[ProvisioningStep]] = relationship(
        "ProvisioningStep", back_populates="workflow",
        order_by="ProvisioningStep.step_index"
    )

    def __repr__(self) -> str:
        return f"<Workflow {self.workflow_type.value} [{self.status.value}]>"


class ProvisioningStep(Base):
    """
    One row per step execution — append-only log.
    Steps are never updated, only inserted.
    Failed steps get a new row when retried.
    """
    __tablename__ = "provisioning_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("provisioning_workflows.id"), nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_name: Mapped[str] = mapped_column(String(128), nullable=False)
    step_description: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus), nullable=False, default=StepStatus.PENDING
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # What this step did — for audit and rollback
    result: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationship
    workflow: Mapped[ProvisioningWorkflow] = relationship(
        "ProvisioningWorkflow", back_populates="steps"
    )

    def __repr__(self) -> str:
        return f"<Step {self.step_name} [{self.status.value}]>"
