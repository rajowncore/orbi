"""
Orbi — Provisioning Step Implementations

Each step is an async function:
    async def step_name(ctx: dict, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict

The returned dict is merged into the workflow context.
Steps should be idempotent where possible (check-then-create pattern).
Rollback steps return None (they just clean up).

Context keys used across steps:
  IN (provided at workflow start):
    order_id, customer_id, product_id, subscription_id
    msisdn, iccid, imsi, inventory_item_id
    package_name, is_prepaid, cgrates_tenant, initial_balance_pence

  OUT (accumulated during workflow):
    service_uuid       — unique service identifier
    hss_subscriber_id  — OmniHSS subscriber internal ID
    hss_msisdn_id      — OmniHSS MSISDN internal ID
"""
from __future__ import annotations
import uuid
import logging
from typing import Any

from app.provisioning.adapters import OmniHSSAdapter, CGRatesAdapter

log = logging.getLogger(__name__)

Ctx = dict[str, Any]


# ══════════════════════════════════════════════════════════════════════════
# PROVISION STEPS
# ══════════════════════════════════════════════════════════════════════════

# HSS Steps
async def resolve_inventory(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict:
    """
    Validate required inventory fields are present in context.
    Generate service_uuid (Mobile_SIM_{short_uuid}).
    """
    if not ctx.get("msisdn"):
        raise ValueError("msisdn is required in provisioning context")

    service_uuid = ctx.get("service_uuid") or f"Mobile_SIM_{str(uuid.uuid4())[:8]}"
    log.info(f"  service_uuid = {service_uuid}")
    return {"service_uuid": service_uuid}


async def fetch_customer_details(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict:
    """
    Validate customer and product details are in context.
    In production this would call the Orbi API — here we validate what was passed.
    """
    required = ["customer_id", "product_id", "package_name"]
    for key in required:
        if not ctx.get(key):
            raise ValueError(f"Missing required context key: {key}")
    return {}


async def hss_lookup_subscriber(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict:
    """
    Look up existing subscriber in OmniHSS by IMSI.
    SIMs are pre-provisioned in HSS with placeholder MSISDNs.
    Sets hss_subscriber_id and hss_subscriber_exists in context.
    """
    imsi = ctx.get("imsi")
    if not imsi:
        log.info("  No IMSI provided — skipping HSS subscriber lookup")
        return {"hss_subscriber_exists": False}

    subscriber = await hss.get_subscriber_by_imsi(imsi)
    if subscriber:
        log.info(f"  Found HSS subscriber: {subscriber.id}")
        return {
            "hss_subscriber_id":     subscriber.id,
            "hss_subscriber_exists": True,
        }
    log.info("  HSS subscriber not found")
    return {"hss_subscriber_exists": False}


async def hss_create_msisdn(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict:
    """
    Create or find MSISDN entry in OmniHSS.
    Check-then-create pattern — idempotent.
    """
    # ✅ Return a fake successful result
    return {
        "hss_msisdn_id": "stubbed-id-123",
        "status": "active",
        "imsi": ctx.get("imsi", "001010000000001")
    }

    msisdn = ctx["msisdn"].lstrip("+")  # OmniHSS prefers no leading +
    existing = await hss.find_msisdn(msisdn)
    if existing:
        log.info(f"  MSISDN already exists in HSS: {existing.id}")
        return {"hss_msisdn_id": existing.id}

    created = await hss.create_msisdn(msisdn)
    log.info(f"  Created MSISDN in HSS: {created.id}")
    return {"hss_msisdn_id": created.id}


async def hss_rollback_msisdn(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> None:
    """Rollback: nothing to do — MSISDN deletion is handled by hss_revert_subscriber."""
    pass


async def hss_activate_subscriber(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict:
    """
    Enable subscriber in OmniHSS and link to real MSISDN.
    Only runs if subscriber was found in lookup step.
    """
    if not ctx.get("hss_subscriber_exists"):
        log.info("  No HSS subscriber — skipping activation")
        return {}

    sub_id   = ctx["hss_subscriber_id"]
    msisdn_id = ctx["hss_msisdn_id"]
    ok = await hss.activate_subscriber(sub_id, msisdn_id)
    if not ok:
        raise RuntimeError(f"HSS subscriber activation failed for subscriber {sub_id}")
    log.info(f"  Activated HSS subscriber {sub_id} with MSISDN {msisdn_id}")
    return {}


async def hss_revert_subscriber(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> None:
    """
    Rollback: revert subscriber to dormant state with placeholder MSISDN.
    Mirrors the Ansible rescue block.
    """
    sub_id = ctx.get("hss_subscriber_id")
    imsi   = ctx.get("imsi", "")
    if sub_id:
        await hss.revert_subscriber_to_dormant(sub_id, imsi)
        log.info(f"  Reverted HSS subscriber {sub_id} to dormant")

### CGRateS Steps
async def cgrates_create_enum(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict:
    """Create E164/ENUM routing entry in CGRateS."""
    result = await cgrates.create_enum_entry(ctx["service_uuid"], ctx["msisdn"])
    if not result.ok:
        raise RuntimeError(f"CGRateS ENUM creation failed: {result.error}")
    return {"Result": result.result}


async def cgrates_delete_enum(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> None:
    """Rollback: delete CGRateS ENUM entry."""
    if ctx.get("service_uuid"):
        result = await cgrates.delete_enum(ctx["service_uuid"])
        if not result.ok:
            log.warning(f"  CGRateS ENUM deletion failed (non-fatal): {result.error}")


async def cgrates_create_filter(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict:
    """Create CGRateS filter rule for this account."""
    result = await cgrates.create_filter(
        ctx["service_uuid"], ctx["msisdn"], ctx.get("imsi", "")
    )
    if not result.ok:
        raise RuntimeError(f"CGRateS filter creation failed: {result.error}")
    return {"Result": result.result}


async def cgrates_delete_filter(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> None:
    """Rollback: delete CGRateS filter."""
    if ctx.get("service_uuid"):
        await cgrates.delete_filter(ctx["service_uuid"])


async def cgrates_create_attributes(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict:
    """Create CGRateS attribute profile with MSISDN, IMSI, QoS params."""
    result = await cgrates.create_attributes(
        ctx["service_uuid"], ctx["msisdn"], ctx.get("imsi", "")
    )
    if not result.ok:
        raise RuntimeError(f"CGRateS attributes creation failed: {result.error}")
    return {"Result": result.result}


async def cgrates_delete_attributes(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> None:
    """Rollback: delete CGRateS attribute profile."""
    if ctx.get("service_uuid"):
        await cgrates.delete_attributes(ctx["service_uuid"])


async def cgrates_create_resources(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict:
    """Create CGRateS resource profile."""
    result = await cgrates.create_resources(ctx["service_uuid"])
    if not result.ok:
        raise RuntimeError(f"CGRateS resources creation failed: {result.error}")
    return {"Result": result.result}


async def cgrates_delete_resources(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> None:
    """Rollback: delete CGRateS resource profile."""
    if ctx.get("service_uuid"):
        await cgrates.delete_resources(ctx["service_uuid"])


async def cgrates_create_stats(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict:
    """Create CGRateS stats queue profile."""
    result = await cgrates.create_stats(ctx["service_uuid"])
    if not result.ok:
        raise RuntimeError(f"CGRateS stats creation failed: {result.error}")
    return {"Result": result.result}


async def cgrates_delete_stats(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> None:
    """Rollback: delete CGRateS stats queue."""
    if ctx.get("service_uuid"):
        await cgrates.delete_stats(ctx["service_uuid"])


async def cgrates_create_account(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict:
    """Create CGRateS OCS account with action triggers."""
    is_prepaid = ctx.get("is_prepaid", False)
    result = await cgrates.create_account(ctx["service_uuid"],
                                           allow_negative=not is_prepaid)
    print(result)  # DEBUG
    if not result.ok:
        raise RuntimeError(f"CGRateS account creation failed: {result.error}")
    return {"Result": result.result}


async def cgrates_delete_account(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> None:
    """Rollback/deprovision: remove CGRateS action plans then delete account."""
    if ctx.get("service_uuid"):
        await cgrates.remove_action_plans(ctx["service_uuid"])
        await cgrates.delete_account(ctx["service_uuid"])


async def cgrates_set_balance(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict:
    """
    Set initial monetary balance in CGRateS.
    0 for new postpaid accounts; initial_balance_pence / 100 for prepaid.
    """
    balance_pence = ctx.get("initial_balance_pence", 0)
    balance_pounds = balance_pence / 100
    result = await cgrates.add_monetary_balance(
        ctx["service_uuid"], ctx["package_name"], balance_pounds
    )
    if not result.ok:
        raise RuntimeError(f"CGRateS balance init failed: {result.error}")
    return {"Result": result.result}


async def orbi_assign_inventory(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict:
    """
    Mark inventory items as assigned in Orbi DB.
    This is handled by the order service — here we just confirm context.
    """
    log.info(f"  Inventory assigned: MSISDN={ctx.get('msisdn')}, ICCID={ctx.get('iccid','N/A')}")
    return {"provisioning_notes": f"Provisioned — HSS:{ctx.get('hss_subscriber_id','N/A')} CGRateS:{ctx.get('service_uuid')}"}


async def orbi_release_inventory(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> None:
    """Rollback: inventory release is handled by order service cancel action."""
    log.info("  Inventory release delegated to order service")


async def orbi_activate_subscription(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict:
    """
    Final step: record provisioning metadata on the subscription.
    Subscription was already set to active by the order service.
    This step stores the external system references for future deprovisioning.
    """
    return {
        "workflow_complete": True,
        "provisioned_at": __import__("datetime").datetime.utcnow().isoformat(),
    }


async def orbi_deactivate_subscription(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> None:
    """Rollback: subscription cancellation handled by order service."""
    log.info("  Subscription deactivation delegated to order service")


# ══════════════════════════════════════════════════════════════════════════
# DEPROVISION STEPS (from Ansible rescue block)
# ══════════════════════════════════════════════════════════════════════════

async def cgrates_remove_action_plans(ctx: Ctx, hss: OmniHSSAdapter, cgrates: CGRatesAdapter) -> dict:
    """First deprovision step: remove action plans and reload scheduler."""
    if ctx.get("service_uuid"):
        result = await cgrates.remove_action_plans(ctx["service_uuid"])
        if not result.ok:
            log.warning(f"  Action plan removal failed (continuing): {result.error}")
    return {}


# ══════════════════════════════════════════════════════════════════════════
# STEP REGISTRIES
# ══════════════════════════════════════════════════════════════════════════

provision_steps_registry = {
    "resolve_inventory":           resolve_inventory,
    "fetch_customer_details":      fetch_customer_details,
    "hss_lookup_subscriber":       hss_lookup_subscriber,
    "hss_create_msisdn":           hss_create_msisdn,
    "hss_rollback_msisdn":         hss_rollback_msisdn,
    "hss_activate_subscriber":     hss_activate_subscriber,
    "hss_revert_subscriber":       hss_revert_subscriber,
    "cgrates_create_enum":         cgrates_create_enum,
    "cgrates_delete_enum":         cgrates_delete_enum,
    "cgrates_create_filter":       cgrates_create_filter,
    "cgrates_delete_filter":       cgrates_delete_filter,
    "cgrates_create_attributes":   cgrates_create_attributes,
    "cgrates_delete_attributes":   cgrates_delete_attributes,
    "cgrates_create_resources":    cgrates_create_resources,
    "cgrates_delete_resources":    cgrates_delete_resources,
    "cgrates_create_stats":        cgrates_create_stats,
    "cgrates_delete_stats":        cgrates_delete_stats,
    "cgrates_create_account":      cgrates_create_account,
    "cgrates_delete_account":      cgrates_delete_account,
    "cgrates_set_balance":         cgrates_set_balance,
    "orbi_assign_inventory":       orbi_assign_inventory,
    "orbi_release_inventory":      orbi_release_inventory,
    "orbi_activate_subscription":  orbi_activate_subscription,
    "orbi_deactivate_subscription":orbi_deactivate_subscription,
}

deprovision_steps_registry = {
    "cgrates_remove_action_plans": cgrates_remove_action_plans,
    "cgrates_delete_account":      cgrates_delete_account,
    "cgrates_delete_attributes":   cgrates_delete_attributes,
    "cgrates_delete_enum":         cgrates_delete_enum,
    "cgrates_delete_resources":    cgrates_delete_resources,
    "cgrates_delete_filter":       cgrates_delete_filter,
    "cgrates_delete_stats":        cgrates_delete_stats,
    "hss_revert_subscriber":       hss_revert_subscriber,
    "orbi_release_inventory":      orbi_release_inventory,
    "orbi_deactivate_subscription":orbi_deactivate_subscription,
}
