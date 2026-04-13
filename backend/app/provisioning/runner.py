"""
Orbi — Provisioning Workflow Runner

Executes provisioning workflows step by step.
Persists state after every step — survives process restarts.
On any step failure, automatically runs rollback in reverse order.
"""
from __future__ import annotations
import uuid
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.provisioning import (
    WorkflowStatus, StepStatus, WorkflowType,
    PROVISION_STEPS, DEPROVISION_STEPS, StepDef,
)
from app.provisioning.models import ProvisioningWorkflow, ProvisioningStep
from app.provisioning.adapters import OmniHSSAdapter, CGRatesAdapter
from app.provisioning.steps import (
    provision_steps_registry,
    deprovision_steps_registry,
)

from sqlalchemy.orm import selectinload

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# WORKFLOW RUNNER
# ══════════════════════════════════════════════════════════════════════════

class WorkflowRunner:
    """
    Executes a provisioning workflow.

    Context dict is the shared state passed between all steps.
    Each step reads from context and writes its outputs back to it.
    Context is persisted to DB after every step.
    """

    def __init__(self, hss: OmniHSSAdapter, cgrates: CGRatesAdapter):
        self.hss     = hss
        self.cgrates = cgrates

    async def run_provision(
        self,
        db: AsyncSession,
        order_id: str,
        context: dict,
    ) -> ProvisioningWorkflow:
        """Start or resume a provision workflow for an order."""
        workflow = await self._get_or_create_workflow(
            db, order_id, WorkflowType.PROVISION, context
        )
        return await self._execute(db, workflow, PROVISION_STEPS,
                                   provision_steps_registry)

    async def run_deprovision(
        self,
        db: AsyncSession,
        order_id: str,
        context: dict,
    ) -> ProvisioningWorkflow:
        """Start a deprovision workflow for an order."""
        workflow = await self._get_or_create_workflow(
            db, order_id, WorkflowType.DEPROVISION, context
        )
        return await self._execute(db, workflow, DEPROVISION_STEPS,
                                   deprovision_steps_registry)

    # ── Internal ──────────────────────────────────────────────────────────

    async def _get_or_create_workflow(
        self,
        db: AsyncSession,
        order_id: str,
        wf_type: WorkflowType,
        context: dict,
    ) -> ProvisioningWorkflow:
        # Check for existing resumable workflow
        r = await db.execute(
            select(ProvisioningWorkflow).options(selectinload(ProvisioningWorkflow.steps)).where(
                ProvisioningWorkflow.order_id      == order_id,
                ProvisioningWorkflow.workflow_type == wf_type,
                ProvisioningWorkflow.status.in_([
                    WorkflowStatus.PENDING,
                    WorkflowStatus.RUNNING,
                    WorkflowStatus.FAILED,
                ]),
            )
        )

        existing = r.scalars().first()
        #existing = r.scalar_one_or_none()

        if existing:
            log.info(f"Resuming workflow {existing.id} for order {order_id}")
            existing.context.update(context)
            existing.status = WorkflowStatus.RUNNING
            await db.flush()
            return existing

        workflow = ProvisioningWorkflow(
            id=str(uuid.uuid4()),
            order_id=order_id,
            workflow_type=wf_type,
            status=WorkflowStatus.RUNNING,
            context=context,
        )
        db.add(workflow)
        await db.flush()
        log.info(f"Created workflow {workflow.id} for order {order_id}")
        return workflow

    async def _execute(
        self,
        db: AsyncSession,
        workflow: ProvisioningWorkflow,
        step_defs: list[StepDef],
        registry: dict,
    ) -> ProvisioningWorkflow:
        """Execute steps sequentially. Roll back on any failure."""

        await db.refresh(workflow, ["steps"])

        # Find which steps already completed (for resume)
        completed_steps = {
            s.step_name for s in workflow.steps
            if s.status == StepStatus.COMPLETED
        }

        completed_in_order = []  # track for rollback

        for i, step_def in enumerate(step_defs):
            if step_def.name in completed_steps:
                log.info(f"  Skipping already-completed step: {step_def.name}")
                completed_in_order.append(step_def)
                continue

            # Create step record
            step = ProvisioningStep(
                id=str(uuid.uuid4()),
                workflow_id=workflow.id,
                step_index=i,
                step_name=step_def.name,
                step_description=step_def.description,
                status=StepStatus.RUNNING,
                started_at=datetime.utcnow(),
            )
            db.add(step)
            await db.flush()

            log.info(f"  Running step [{i+1}/{len(step_defs)}]: {step_def.name}")

            # Execute step
            fn = registry.get(step_def.name)
            if not fn:
                step.status = StepStatus.FAILED
                step.error_message = f"No implementation registered for step: {step_def.name}"
                step.completed_at = datetime.utcnow()
                await db.flush()
                await self._rollback(db, workflow, completed_in_order,
                                     registry, step_def.name, step.error_message)
                return workflow

            try:
                result = await fn(workflow.context, self.hss, self.cgrates)
                # Step fn returns a dict of values to merge into context
                if isinstance(result, dict):
                    workflow.context = {**workflow.context, **result}
                    await db.flush()

                step.status       = StepStatus.COMPLETED
                step.result       = result
                step.completed_at = datetime.utcnow()
                await db.flush()
                completed_in_order.append(step_def)
                log.info(f"  ✓ {step_def.name}")

            except Exception as e:
                err = str(e)
                log.error(f"  ✗ Step {step_def.name} failed: {err}")
                step.status        = StepStatus.FAILED
                step.error_message = err
                step.completed_at  = datetime.utcnow()
                await db.flush()

                await self._rollback(db, workflow, completed_in_order,
                                     registry, step_def.name, err)
                return workflow

        # All steps done
        workflow.status       = WorkflowStatus.COMPLETED
        workflow.completed_at = datetime.utcnow()
        await db.flush()
        log.info(f"Workflow {workflow.id} completed successfully")
        return workflow

    async def _rollback(
        self,
        db: AsyncSession,
        workflow: ProvisioningWorkflow,
        completed_steps: list[StepDef],
        registry: dict,
        failed_step: str,
        error: str,
    ) -> None:
        """
        Roll back completed steps in reverse order.
        Mirrors the Ansible rescue block.
        Each step that has a rollback_name gets it called.
        Rollback failures are logged but never raise — we try everything.
        """
        workflow.status        = WorkflowStatus.ROLLING_BACK
        workflow.error_step    = failed_step
        workflow.error_message = error
        await db.flush()

        log.warning(f"Rolling back workflow {workflow.id} — failed at {failed_step}")

        # Reverse order
        for step_def in reversed(completed_steps):
            if not step_def.rollback_name:
                continue

            rollback_fn = registry.get(step_def.rollback_name)
            if not rollback_fn:
                log.warning(f"  No rollback fn for {step_def.rollback_name} — skipping")
                continue

            # Record rollback step
            rb_step = ProvisioningStep(
                id=str(uuid.uuid4()),
                workflow_id=workflow.id,
                step_index=9000,  # rollback steps get high index
                step_name=step_def.rollback_name,
                step_description=f"ROLLBACK: {step_def.description}",
                status=StepStatus.RUNNING,
                started_at=datetime.utcnow(),
            )
            db.add(rb_step)
            await db.flush()

            try:
                await rollback_fn(workflow.context, self.hss, self.cgrates)
                rb_step.status       = StepStatus.ROLLED_BACK
                rb_step.completed_at = datetime.utcnow()
                await db.flush()
                log.info(f"  ↩ {step_def.rollback_name}")
            except Exception as e:
                rb_step.status        = StepStatus.FAILED
                rb_step.error_message = str(e)
                rb_step.completed_at  = datetime.utcnow()
                await db.flush()
                log.error(f"  ✗ Rollback {step_def.rollback_name} failed: {e} (continuing)")

        workflow.status = WorkflowStatus.ROLLED_BACK
        await db.flush()
        log.warning(f"Workflow {workflow.id} rolled back")
