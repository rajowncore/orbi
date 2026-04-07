"""
Orbi — External System Adapters

Typed interfaces for OmniHSS and CGRateS.
Each adapter is independently testable and swappable.

Based on the API calls observed in play_sim_omnihss.yaml:
  - OmniHSS: REST API for subscriber/MSISDN management
  - CGRateS: JSON-RPC API for rating/charging configuration
"""
from __future__ import annotations
import uuid
import logging
from dataclasses import dataclass
from typing import Optional
import aiohttp

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# RESULT TYPES
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class HSSSubscriber:
    id: str
    imsi: str
    msisdn_ids: list[str]
    enabled: bool
    ims_enabled: bool


@dataclass
class HSSMsisdn:
    id: str
    msisdn: str


@dataclass
class CGRatesResult:
    ok: bool
    result: any
    error: str | None = None


# ══════════════════════════════════════════════════════════════════════════
# OMNIHSS ADAPTER
# ══════════════════════════════════════════════════════════════════════════

class OmniHSSAdapter:
    """
    Adapter for OmniHSS REST API.
    Mirrors the API calls in play_sim_omnihss.yaml.
    """

    def __init__(self, base_url: str, verify_ssl: bool = False):
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl

    async def get_subscriber_by_imsi(self, imsi: str) -> HSSSubscriber | None:
        """GET /subscriber/imsi/{imsi} — returns None if not found (404)."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/subscriber/imsi/{imsi}",
                ssl=self.verify_ssl,
            ) as resp:
                if resp.status == 404:
                    return None
                resp.raise_for_status()
                data = await resp.json()
                body = data.get("response", data)
                return HSSSubscriber(
                    id=str(body["id"]),
                    imsi=imsi,
                    msisdn_ids=[str(m) for m in body.get("msisdns", [])],
                    enabled=body.get("enabled", False),
                    ims_enabled=body.get("ims_enabled", False),
                )

    async def find_msisdn(self, msisdn: str) -> HSSMsisdn | None:
        """GET /msisdn/digits/{msisdn} — search for existing MSISDN."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/msisdn/digits/{msisdn}",
                ssl=self.verify_ssl,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                items = data.get("response", data)
                if isinstance(items, list):
                    for item in items:
                        if item.get("msisdn") == msisdn:
                            return HSSMsisdn(id=str(item["id"]), msisdn=msisdn)
                return None

    async def create_msisdn(self, msisdn: str) -> HSSMsisdn:
        """POST /msisdn — create a new MSISDN entry."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/msisdn",
                json={"msisdn": msisdn},
                ssl=self.verify_ssl,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                body = data.get("response", data)
                return HSSMsisdn(id=str(body["id"]), msisdn=msisdn)

    async def activate_subscriber(
        self, subscriber_id: str, msisdn_id: str
    ) -> bool:
        """PATCH /subscriber/{id} — enable subscriber and link MSISDN."""
        async with aiohttp.ClientSession() as session:
            async with session.patch(
                f"{self.base_url}/subscriber/{subscriber_id}",
                json={"enabled": True, "ims_enabled": True,
                      "msisdns": [int(msisdn_id)]},
                ssl=self.verify_ssl,
            ) as resp:
                return resp.status in (200, 204)

    async def revert_subscriber_to_dormant(
        self, subscriber_id: str, imsi_suffix: str
    ) -> bool:
        """
        PATCH subscriber back to dormant state with placeholder MSISDN.
        Creates a placeholder MSISDN first, then updates the subscriber.
        Mirrors the deprovision rescue block in the playbook.
        """
        placeholder = f"2472473{imsi_suffix[-4:]}{str(uuid.uuid4().int)[:4]}"
        try:
            placeholder_msisdn = await self.create_msisdn(placeholder)
            async with aiohttp.ClientSession() as session:
                async with session.patch(
                    f"{self.base_url}/subscriber/{subscriber_id}",
                    json={"enabled": True, "ims_enabled": False,
                          "msisdns": [int(placeholder_msisdn.id)]},
                    ssl=self.verify_ssl,
                ) as resp:
                    return resp.status in (200, 204)
        except Exception as e:
            log.warning(f"HSS revert failed (non-fatal during rollback): {e}")
            return False


# ══════════════════════════════════════════════════════════════════════════
# CGRATES ADAPTER
# ══════════════════════════════════════════════════════════════════════════

class CGRatesAdapter:
    """
    Adapter for CGRateS JSON-RPC API.
    All methods map directly to CGRateS API methods from the playbook.
    """

    def __init__(self, base_url: str, tenant: str, verify_ssl: bool = False):
        self.rpc_url = f"{base_url.rstrip('/')}/jsonrpc"
        self.tenant  = tenant
        self.verify_ssl = verify_ssl

    async def _call(self, method: str, params: list) -> CGRatesResult:
        payload = {"method": method, "params": params, "id": 1}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.rpc_url, json=payload, ssl=self.verify_ssl
                ) as resp:
                    data = await resp.json()
                    if data.get("result") == "OK" or data.get("result") is not None:
                        return CGRatesResult(ok=True, result=data.get("result"))
                    return CGRatesResult(ok=False, result=None,
                                        error=str(data.get("error", "Unknown error")))
        except Exception as e:
            return CGRatesResult(ok=False, result=None, error=str(e))

    async def create_enum_entry(self, service_uuid: str, phone_number: str) -> CGRatesResult:
        """APIerSv2.SetAttributeProfile — E164/ENUM routing entry."""
        return await self._call("APIerSv2.SetAttributeProfile", [{
            "Tenant": self.tenant,
            "ID": f"ATTR_E164_{service_uuid}",
            "Contexts": ["*sessions"],
            "FilterIDs": [f"*prefix:~*req.E164Address:{phone_number}"],
            "Attributes": [
                {"FilterIDs": [], "Path": "*req.NAPTRAddress",
                 "Type": "*constant",
                 "Value": f"!(^.*$)!sip:\\\\1@ims.{self.tenant}!"},
                {"FilterIDs": [], "Path": "*req.NAPTROrder",
                 "Type": "*constant", "Value": "42"},
                {"FilterIDs": [], "Path": "*req.NAPTRPreference",
                 "Type": "*constant", "Value": "42"},
            ],
            "Weight": 8,
        }])

    async def create_filter(self, service_uuid: str,
                             phone_number: str, imsi: str) -> CGRatesResult:
        """ApierV1.SetFilter — account filter rule."""
        return await self._call("ApierV1.SetFilter", [{
            "Tenant": self.tenant,
            "ID": f"FLTR_ACCOUNT_{service_uuid}",
            "Rules": [{
                "Type": "*string",
                "Element": "~*req.Account",
                "Values": [service_uuid, imsi, phone_number],
            }],
            "ActivationInterval": {},
        }])

    async def create_attributes(self, service_uuid: str,
                                 phone_number: str, imsi: str,
                                 max_bitrate_dl: int = 5242880,
                                 max_bitrate_ul: int = 5242880) -> CGRatesResult:
        """APIerSv2.SetAttributeProfile — subscriber attribute profile."""
        return await self._call("APIerSv2.SetAttributeProfile", [{
            "ID": f"ATTR_ACCOUNT_{service_uuid}",
            "Tenant": self.tenant,
            "Attributes": [
                {"Path": "*req.Account",     "Type": "*constant", "Value": service_uuid},
                {"Path": "*req.IMSI",        "Type": "*constant", "Value": imsi},
                {"Path": "*req.MSISDN",      "Type": "*constant", "Value": phone_number},
                {"Path": "*req.MaxBitrateDL","Type": "*constant", "Value": str(max_bitrate_dl)},
                {"Path": "*req.MaxBitrateUL","Type": "*constant", "Value": str(max_bitrate_ul)},
                {"Path": "*req.PcefPolicyName","Type":"*constant","Value": "Inactive"},
            ],
            "Contexts": ["*any"],
            "FilterIDs": [f"FLTR_ACCOUNT_{service_uuid}"],
        }])

    async def create_resources(self, service_uuid: str) -> CGRatesResult:
        """ApierV1.SetResourceProfile — resource limits."""
        return await self._call("ApierV1.SetResourceProfile", [{
            "ID": f"RESOURCE_Account_{service_uuid}",
            "Tenant": self.tenant,
            "FilterIDs": [f"FLTR_ACCOUNT_{service_uuid}"],
            "UsageTTL": -1, "Limit": 5, "Blocker": False,
            "Stored": True, "Weight": 10,
            "ThresholdIDs": ["*none"],
        }])

    async def create_stats(self, service_uuid: str) -> CGRatesResult:
        """ApierV1.SetStatQueueProfile — stats queue."""
        return await self._call("ApierV1.SetStatQueueProfile", [{
            "ID": f"STATS_Account_{service_uuid}",
            "Tenant": self.tenant,
            "FilterIDs": [f"FLTR_ACCOUNT_{service_uuid}",
                          "*string:~*opts.*subsys:*sessions"],
            "QueueLength": 50, "TTL": -1, "MinItems": 0,
            "Metrics": [{"FilterIDs": [], "MetricID": "*sum#1"},
                        {"FilterIDs": [], "MetricID": "*sum#~*req.Usage"}],
            "Stored": False, "Blocker": False, "Weight": 0,
        }])

    async def create_account(self, service_uuid: str,
                              allow_negative: bool = False) -> CGRatesResult:
        """ApierV2.SetAccount — create OCS account with action triggers."""
        return await self._call("ApierV2.SetAccount", [{
            "Tenant": self.tenant,
            "Account": service_uuid,
            "ActionPlanIds": [],
            "ActionPlansOverwrite": True,
            "ActionTriggerIDs": [
                #"ActionTrigger_BalanceExpired",
                #"ActionTrigger_500MB_Remaining",
                #"ActionTrigger_0MB_Remaining",
            ],
            "ActionTriggersOverwrite": True,
            "ExtraOptions": {
                "AllowNegative": allow_negative,
                "Disabled": False,
            },
            "ReloadScheduler": True,
        }])

    async def add_monetary_balance(self, service_uuid: str,
                                    package_name: str,
                                    amount: float = 0) -> CGRatesResult:
        """ApierV1.AddBalance — initialise monetary balance."""
        return await self._call("ApierV1.AddBalance", [{
            "Tenant": self.tenant,
            "Account": service_uuid,
            "BalanceType": "*monetary",
            "Categories": "*any",
            "cdrlog": False,  # Set to True if you want this balance change to appear in CDRs (not needed for initial balance)
            "ActionExtraData": {
                "Subject": package_name,
                "Destination": package_name,
            },
            "Balance": {
                "ID": "PAYG Balance",
                "Value": amount,
                "ExpiryTime": "+4320h",
                "Weight": 1,
                "DestinationIDs": "",
                "Blocker": True,
            },
        }])

    # ── Deprovision methods ────────────────────────────────────────────────

    async def remove_action_plans(self, service_uuid: str) -> CGRatesResult:
        """Remove action plans and reload scheduler — first deprovision step."""
        return await self._call("ApierV2.SetAccount", [{
            "Tenant": self.tenant,
            "Account": service_uuid,
            "ActionPlanIds": [],
            "ActionPlansOverwrite": True,
            "ExtraOptions": {"AllowNegative": False, "Disabled": False},
            "ReloadScheduler": True,
        }])

    async def delete_account(self, service_uuid: str) -> CGRatesResult:
        return await self._call("ApierV1.RemoveAccount", [{
            "Tenant": self.tenant, "Account": service_uuid, "ReloadScheduler": True,
        }])

    async def delete_attributes(self, service_uuid: str) -> CGRatesResult:
        return await self._call("APIerSv1.RemoveAttributeProfile", [{
            "TPid": "cgrates.org", "Tenant": self.tenant,
            "ID": f"ATTR_ACCOUNT_{service_uuid}",
        }])

    async def delete_enum(self, service_uuid: str) -> CGRatesResult:
        return await self._call("APIerSv1.RemoveAttributeProfile", [{
            "TPid": "cgrates.org", "Tenant": self.tenant,
            "ID": f"ATTR_E164_{service_uuid}",
        }])

    async def delete_resources(self, service_uuid: str) -> CGRatesResult:
        return await self._call("APIerSv1.RemoveResourceProfile", [{
            "Tenant": self.tenant, "ID": f"RESOURCE_Account_{service_uuid}",
        }])

    async def delete_filter(self, service_uuid: str) -> CGRatesResult:
        return await self._call("APIerSv1.RemoveFilter", [{
            "Tenant": self.tenant, "ID": f"FLTR_ACCOUNT_{service_uuid}",
        }])

    async def delete_stats(self, service_uuid: str) -> CGRatesResult:
        return await self._call("ApierV1.RemoveStatQueueProfile", [{
            "Tenant": self.tenant, "ID": f"STATS_Account_{service_uuid}",
        }])

    async def get_attributes(self, service_uuid: str) -> CGRatesResult:
        """Fetch attribute profile — used during deprovision to recover MSISDN/IMSI."""
        return await self._call("APIerSv1.GetAttributeProfile", [{
            "Tenant": self.tenant, "ID": f"ATTR_ACCOUNT_{service_uuid}",
        }])
