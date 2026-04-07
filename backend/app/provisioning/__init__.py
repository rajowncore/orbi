"""
Orbi — Provisioning Workflow Engine

Translates the Ansible play_sim_omnihss playbook into a persistent,
resumable Python workflow with full rollback on failure.

Key design decisions:
- Each workflow step is a Python coroutine registered by name
- Workflow state is persisted to DB after every step — survives restarts
- Steps declare their rollback counterpart — rollback runs in reverse order
- All external calls (HSS, CGRateS) go through typed adapter interfaces
- The workflow engine itself has zero knowledge of HSS or CGRateS internals
"""
from __future__ import annotations
from enum import Enum as PyEnum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Awaitable


# ── Enums ─────────────────────────────────────────────────────────────────

class WorkflowStatus(str, PyEnum):
    PENDING    = "pending"
    RUNNING    = "running"
    COMPLETED  = "completed"
    FAILED     = "failed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK  = "rolled_back"


class StepStatus(str, PyEnum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    SKIPPED   = "skipped"
    ROLLED_BACK = "rolled_back"


class WorkflowType(str, PyEnum):
    PROVISION   = "provision_sim"
    DEPROVISION = "deprovision_sim"
    SUSPEND     = "suspend_sim"
    RESUME      = "resume_sim"


# ── Step definition ────────────────────────────────────────────────────────

@dataclass
class StepDef:
    """Defines a workflow step and its optional rollback."""
    name: str
    description: str
    rollback_name: str | None = None   # name of the step that undoes this one


# ── Provision workflow steps (mirrors the Ansible playbook) ───────────────

PROVISION_STEPS: list[StepDef] = [
    StepDef("resolve_inventory",
            "Resolve MSISDN and SIM card from Orbi inventory",
            rollback_name=None),  # No rollback needed — read-only

    StepDef("fetch_customer_details",
            "Fetch customer and product details",
            rollback_name=None),  # Read-only

    StepDef("hss_lookup_subscriber",
            "Look up subscriber in OmniHSS by IMSI",
            rollback_name=None),  # Read-only

    StepDef("hss_create_msisdn",
            "Create or find MSISDN entry in OmniHSS",
            rollback_name="hss_rollback_msisdn"),

    StepDef("hss_activate_subscriber",
            "Enable subscriber and link MSISDN in OmniHSS",
            rollback_name="hss_revert_subscriber"),

    StepDef("cgrates_create_enum",
            "Create E164/ENUM routing entry in CGRateS",
            rollback_name="cgrates_delete_enum"),

    StepDef("cgrates_create_filter",
            "Create account filter rule in CGRateS",
            rollback_name="cgrates_delete_filter"),

    StepDef("cgrates_create_attributes",
            "Create attribute profile (MSISDN, IMSI, QoS) in CGRateS",
            rollback_name="cgrates_delete_attributes"),

    StepDef("cgrates_create_resources",
            "Create resource profile in CGRateS",
            rollback_name="cgrates_delete_resources"),

    StepDef("cgrates_create_stats",
            "Create stats queue profile in CGRateS",
            rollback_name="cgrates_delete_stats"),

    StepDef("cgrates_create_account",
            "Create subscriber account in CGRateS with action triggers",
            rollback_name="cgrates_delete_account"),

    StepDef("cgrates_set_balance",
            "Initialise monetary balance in CGRateS",
            rollback_name=None),  # Account deletion handles this

    StepDef("orbi_assign_inventory",
            "Assign SIM and MSISDN to subscription in Orbi",
            rollback_name="orbi_release_inventory"),

    StepDef("orbi_activate_subscription",
            "Set subscription active and record provisioning metadata",
            rollback_name="orbi_deactivate_subscription"),
]

DEPROVISION_STEPS: list[StepDef] = [
    StepDef("cgrates_remove_action_plans",
            "Remove action plans from CGRateS account"),
    StepDef("cgrates_delete_account",
            "Delete CGRateS account"),
    StepDef("cgrates_delete_attributes",
            "Delete CGRateS attribute profile"),
    StepDef("cgrates_delete_enum",
            "Delete CGRateS ENUM/E164 entry"),
    StepDef("cgrates_delete_resources",
            "Delete CGRateS resource profile"),
    StepDef("cgrates_delete_filter",
            "Delete CGRateS filter rule"),
    StepDef("cgrates_delete_stats",
            "Delete CGRateS stats queue"),
    StepDef("hss_revert_subscriber",
            "Revert HSS subscriber to dormant state with placeholder MSISDN"),
    StepDef("orbi_release_inventory",
            "Release MSISDN back to available pool"),
    StepDef("orbi_deactivate_subscription",
            "Cancel subscription in Orbi"),
]
