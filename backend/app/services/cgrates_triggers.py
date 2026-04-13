"""
Orbi — CGRateS Action Trigger Configuration

Configures CGRateS to POST to Orbi when balance thresholds are crossed.
Fully idempotent — safe to call on every startup across all Gunicorn workers.

Fixes:
  - EXISTS error on SetActions: skip gracefully if already created
  - MANDATORY_IE_MISSING [GroupID]: ActionTriggers require a GroupID
"""
from __future__ import annotations
import logging
import uuid

log = logging.getLogger(__name__)


async def setup_cgrates_action_triggers(
    cgrates_url: str,
    tenant: str,
    orbi_webhook_url: str,
) -> dict:
    """
    Create CGRateS Actions and ActionTriggers for balance notifications.
    Idempotent — EXISTS errors are silently skipped.

    ActionTriggers created (all in group "OrbiAlerts"):
      ActionTrigger_BalanceExpired   — monetary balance ExpiryTime reached
      ActionTrigger_500MB_Remaining  — data drops below 524288000 bytes (500MB)
      ActionTrigger_0MB_Remaining    — data hits 0
    """
    import aiohttp

    rpc_url = f"{cgrates_url.rstrip('/')}/jsonrpc"
    results = {}

    async def call(method: str, params: list) -> any:
        payload = {
            "jsonrpc": "2.0",
            "method":  method,
            "params":  params,
            "id":      str(uuid.uuid4())[:8],
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(rpc_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                err = data.get("error")
                if err:
                    raise RuntimeError(str(err))
                return data.get("result")

    async def call_idempotent(method: str, params: list, name: str) -> str:
        """Call CGRateS API, treating EXISTS as success."""
        try:
            await call(method, params)
            log.info(f"CGRateS: created {name}")
            return "created"
        except RuntimeError as e:
            if "EXISTS" in str(e):
                log.debug(f"CGRateS: {name} already exists — skipping")
                return "exists"
            log.warning(f"CGRateS: failed to create {name}: {e}")
            return f"error: {e}"

    # ── Actions: HTTP POST to Orbi ─────────────────────────────────────
    action_map = {
        "ACT_NOTIFY_BALANCE_EXPIRED":  "ActionTrigger_BalanceExpired",
        "ACT_NOTIFY_500MB_REMAINING":  "ActionTrigger_500MB_Remaining",
        "ACT_NOTIFY_0MB_REMAINING":    "ActionTrigger_0MB_Remaining",
    }

    for action_id, event_name in action_map.items():
        webhook = (
            f"{orbi_webhook_url}"
            f"?Account=%7E*req.Account%7D"  # CGRateS template: ~*req.Account
            f"&Tenant={tenant}"
            f"&Event={event_name}"
        )
        results[action_id] = await call_idempotent(
            "ApierV2.SetActions",
            [{
                "ActionsId": action_id,
                "Tenant":    tenant,
                "Actions": [{
                    "Identifier":      "*http_post",
                    "ExtraParameters": f"{orbi_webhook_url}",
                    "Weight":          10,
                }],
            }],
            action_id,
        )

    # ── ActionTriggers ────────────────────────────────────────────────
    # GroupID is required — all Orbi triggers belong to "OrbiAlerts" group
    # ThresholdType options: *min_balance, *max_balance, *balance_expired
    # BalanceType: *monetary, *data, *voice, *sms

    triggers = [
        {
            "name": "ActionTrigger_BalanceExpired",
            "params": {
                "Tenant":           tenant,
                "ID":               "ActionTrigger_BalanceExpired",
                "GroupID":          "OrbiAlerts",           # ← required field
                "ThresholdType":    "*balance_expired",
                "BalanceType":      "*monetary",
                "ActionsID":        "ACT_NOTIFY_BALANCE_EXPIRED",
                "Weight":           10,
                "Recurrent":        False,
                "Executed":         False,
            }
        },
        {
            "name": "ActionTrigger_500MB_Remaining",
            "params": {
                "Tenant":           tenant,
                "ID":               "ActionTrigger_500MB_Remaining",
                "GroupID":          "OrbiAlerts",
                "ThresholdType":    "*min_balance",
                "ThresholdValue":   524288000,              # 500MB in bytes
                "BalanceType":      "*data",
                "ActionsID":        "ACT_NOTIFY_500MB_REMAINING",
                "Weight":           10,
                "Recurrent":        False,
                "Executed":         False,
            }
        },
        {
            "name": "ActionTrigger_0MB_Remaining",
            "params": {
                "Tenant":           tenant,
                "ID":               "ActionTrigger_0MB_Remaining",
                "GroupID":          "OrbiAlerts",
                "ThresholdType":    "*min_balance",
                "ThresholdValue":   0,
                "BalanceType":      "*data",
                "ActionsID":        "ACT_NOTIFY_0MB_REMAINING",
                "Weight":           10,
                "Recurrent":        False,
                "Executed":         False,
            }
        },
    ]

    for t in triggers:
        results[t["name"]] = await call_idempotent(
            "ApierV2.SetActionTrigger",
            [t["params"]],
            t["name"],
        )

    log.info(f"CGRateS trigger setup: {results}")
    return results
