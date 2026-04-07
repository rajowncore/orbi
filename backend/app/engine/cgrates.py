"""
Orbi — CGRateS OCS Adapter

Integrates CGRateS as Orbi's Online Charging System when OCS_MODE=cgrates.

What CGRateS owns in this mode:
  - Real-time balance deduction (via Gy/Diameter from PGW/IMS)
  - CDR rating (applies rate tables, bundle deduction, OOB charging)
  - Account balance state (monetary buckets, data/voice/SMS bundles)

What Orbi owns in this mode:
  - Customer management, products, orders, subscriptions
  - Provisioning (creates CGRateS accounts via SetAccount/SetBalance)
  - Topup flow (receives payment, calls AddBalance on CGRateS)
  - Invoicing (pulls rated CDRs from CGRateS, generates invoices)
  - UI / CM (the frontend never talks to CGRateS directly)

Two primary integration flows:

  PREPAID topup:
    Customer pays → Orbi records payment → Orbi calls AddBalance on CGRateS
    CGRateS balance increases → customer can make calls / use data

  POSTPAID billing run:
    Orbi calls GetCDRs for the billing period → CGRateS returns rated CDRs
    Orbi aggregates by customer → creates ChargeRecords → generates invoices

Note: CDR rating itself happens autonomously inside CGRateS as CDRs arrive
from the network via SFTP/Diameter. Orbi does NOT need to forward CDRs.
"""
from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
import aiohttp

from app.engine import IChargingEngine, RatingResult

log = logging.getLogger(__name__)


# ── CGRateS response types ────────────────────────────────────────────────

@dataclass
class CGRatesCDR:
    """A rated CDR returned by CGRateS ApierV2.GetCDRs."""
    cgrid:        str
    origin_id:    str
    origin_host:  str
    account:      str           # service_uuid
    subject:      str           # msisdn
    destination:  str
    tor:          str           # *data | *voice | *sms
    usage:        float         # in CGRateS native units
    cost:         float         # in CGRateS monetary units
    cost_details: dict
    setup_time:   Optional[datetime] = None
    answer_time:  Optional[datetime] = None
    tenant:       str = "cgrates.org"

    @property
    def cost_pence(self) -> int:
        """Convert CGRateS cost to Orbi integer pence."""
        return int(
            (Decimal(str(self.cost)) * Decimal("100"))
            .to_integral_value(ROUND_HALF_UP)
        )

    @property
    def event_type(self) -> str:
        return {"*data": "data", "*voice": "voice", "*sms": "sms"}.get(self.tor, "custom")


@dataclass
class CGRatesBalance:
    """Account balance state from CGRateS ApierV2.GetAccount."""
    account:         str
    monetary_pence:  int          # total monetary balance in pence
    data_bytes:      int = 0      # data bundle remaining (bytes)
    voice_ns:        int = 0      # voice bundle remaining (nanoseconds)
    sms_count:       int = 0      # SMS bundle remaining
    disabled:        bool = False
    raw:             dict = field(default_factory=dict)

    @property
    def data_mb(self) -> int:
        return self.data_bytes // 1_048_576

    @property
    def voice_mins(self) -> int:
        return self.voice_ns // 60_000_000_000


@dataclass
class AddBalanceResult:
    ok:      bool
    account: str
    message: str
    error:   Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════
# JSON-RPC CLIENT
# ══════════════════════════════════════════════════════════════════════════

class CGRatesClient:
    """
    Async JSON-RPC client for CGRateS.
    Covers only the APIs Orbi actually needs.
    """

    def __init__(self, base_url: str, tenant: str,
                 verify_ssl: bool = False, timeout: int = 10):
        self.rpc_url = f"{base_url.rstrip('/')}/jsonrpc"
        self.tenant  = tenant
        self.verify_ssl = verify_ssl
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def _call(self, method: str, params: list) -> dict | list:
        payload = {
            "jsonrpc": "2.0",
            "method":  method,
            "params":  params,
            "id":      str(uuid.uuid4())[:8],
        }
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as sess:
                async with sess.post(
                    self.rpc_url, json=payload, ssl=self.verify_ssl
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    if "error" in data and data["error"]:
                        raise RuntimeError(f"CGRateS RPC error [{method}]: {data['error']}")
                    return data.get("result", {})
        except aiohttp.ClientError as e:
            raise RuntimeError(f"CGRateS connection error [{method}]: {e}") from e

    # ── CDR retrieval ──────────────────────────────────────────────────────

    async def get_cdrs(
        self,
        period_start: datetime,
        period_end:   datetime,
        accounts:     list[str] | None = None,
    ) -> list[CGRatesCDR]:
        """
        ApierV2.GetCDRs — pull rated CDRs for a billing period.
        Returns all CDRs between period_start and period_end.
        Optionally filtered by account (service_uuid) list.
        """
        params: dict = {
            "Tenants":    [self.tenant],
            "AnswerTimeStart": period_start.isoformat() + "Z",
            "AnswerTimeEnd":   period_end.isoformat() + "Z",
            "OrderByField":   "AnswerTime",
        }
        if accounts:
            params["Accounts"] = accounts

        result = await self._call("ApierV2.GetCDRs", [params])
        if not result or not isinstance(result, list):
            return []

        cdrs = []
        for r in result:
            try:
                cdrs.append(CGRatesCDR(
                    cgrid=r.get("CGRID", ""),
                    origin_id=r.get("OriginID", ""),
                    origin_host=r.get("OriginHost", ""),
                    account=r.get("Account", ""),
                    subject=r.get("Subject", ""),
                    destination=r.get("Destination", ""),
                    tor=r.get("ToR", "*generic"),
                    usage=float(r.get("Usage", 0) or 0),
                    cost=float(r.get("Cost", 0) or 0),
                    cost_details=r.get("CostDetails", {}),
                    tenant=r.get("Tenant", self.tenant),
                ))
            except Exception as e:
                log.warning(f"Skipping malformed CDR {r.get('CGRID','?')}: {e}")

        log.info(f"CGRateS GetCDRs: {len(cdrs)} CDRs for period "
                 f"{period_start.date()} → {period_end.date()}")
        return cdrs

    # ── Balance management ─────────────────────────────────────────────────

    async def add_balance(
        self,
        account:      str,
        amount_pence: int,
        package_name: str = "",
        balance_id:   str = "PAYG Balance",
        expiry_hours: int = 4320,       # 6 months default
    ) -> AddBalanceResult:
        """
        ApierV1.AddBalance — top up a CGRateS account with monetary credit.
        Called by Orbi when a customer makes a payment / prepaid topup.
        amount_pence is converted to CGRateS monetary units (÷100).
        """
        amount = float(Decimal(str(amount_pence)) / Decimal("100"))
        try:
            await self._call("ApierV1.AddBalance", [{
                "Tenant":  self.tenant,
                "Account": account,
                "BalanceType": "*monetary",
                "Categories": "*any",
                "cdrlog": True,
                "ActionExtraData": {
                    "Subject":     package_name or account,
                    "Destination": package_name or account,
                },
                "Balance": {
                    "ID":          balance_id,
                    "Value":       amount,
                    "ExpiryTime":  f"+{expiry_hours}h",
                    "Weight":      1,
                    "DestinationIDs": "",
                    "Blocker":     True,
                },
            }])
            return AddBalanceResult(ok=True, account=account,
                                    message=f"Added {amount_pence}p to {account}")
        except Exception as e:
            return AddBalanceResult(ok=False, account=account,
                                    message="Balance top-up failed", error=str(e))

    async def get_account(self, account: str) -> CGRatesBalance:
        """
        ApierV2.GetAccount — fetch current balance state.
        Used to sync Orbi's UI with the real CGRateS balance.
        """
        try:
            result = await self._call("ApierV2.GetAccount", [{
                "Tenant":  self.tenant,
                "Account": account,
            }])
            return _parse_account(account, result)
        except Exception as e:
            log.warning(f"CGRateS GetAccount failed for {account}: {e}")
            return CGRatesBalance(account=account, monetary_pence=0)

    async def ping(self) -> bool:
        """CoreSv1.Status — connectivity check."""
        try:
            await self._call("CoreSv1.Status", [{}])
            return True
        except Exception:
            return False


def _parse_account(account: str, data: dict) -> CGRatesBalance:
    """Parse CGRateS GetAccount response into CGRatesBalance."""
    if not data or not isinstance(data, dict):
        return CGRatesBalance(account=account, monetary_pence=0)

    balance_map = data.get("BalanceMap", {})
    monetary_pence = 0
    data_bytes     = 0
    voice_ns       = 0
    sms_count      = 0

    for btype, buckets in balance_map.items():
        for bucket in (buckets or []):
            val = float(bucket.get("Value", 0) or 0)
            if btype == "*monetary":
                monetary_pence += int(Decimal(str(val)) * 100)
            elif btype == "*data":
                data_bytes += int(val)
            elif btype == "*voice":
                voice_ns += int(val)
            elif btype == "*sms":
                sms_count += int(val)

    return CGRatesBalance(
        account=account,
        monetary_pence=monetary_pence,
        data_bytes=data_bytes,
        voice_ns=voice_ns,
        sms_count=sms_count,
        disabled=data.get("Disabled", False),
        raw=data,
    )


# ══════════════════════════════════════════════════════════════════════════
# CGRATES ICHARGING ENGINE ADAPTER
# ══════════════════════════════════════════════════════════════════════════

class CGRatesChargingEngine(IChargingEngine):
    """
    IChargingEngine implementation for CGRateS mode (OCS_MODE=cgrates).

    In this mode:
    - rate_usage() is NOT called for normal CDR processing.
      CGRateS rates CDRs autonomously as they arrive from the network.
      Orbi pulls rated CDRs at billing time via get_cdrs_for_billing().

    - rate_usage() IS called only when Orbi is the CDR source
      (e.g. manually submitted usage events via REST API).
      In this case Orbi forwards them to CGRateS via ProcessCDR.

    - check_balance() queries CGRateS for the real-time balance.

    For the normal MVNO flow: use get_cdrs_for_billing() and topup_balance()
    directly — do not route through rate_usage().
    """

    def __init__(self, base_url: str, tenant: str,
                 verify_ssl: bool = False, timeout: int = 10):
        self.client = CGRatesClient(base_url, tenant, verify_ssl, timeout)
        self.tenant = tenant

    def get_name(self) -> str:
        return f"cgrates@{self.client.rpc_url}"

    def check_balance(self, balance_cents: int, required_cents: int) -> bool:
        """
        Synchronous balance check using Orbi's cached ledger value.
        For real-time accuracy, use get_account_balance() (async).
        """
        return balance_cents >= required_cents

    def rate_usage(
        self,
        event_type: str,
        quantity: Decimal,
        unit: str,
        bundle_remaining: int,
        unit_price_oob: int,
        customer_credit_type: str,
        **kwargs,
    ) -> RatingResult:
        """
        Called only when Orbi is the CDR source (manual API usage events).
        For network CDRs, CGRateS rates them directly — use get_cdrs_for_billing().
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                log.warning(
                    "CGRateS rate_usage called from async context — "
                    "use rate_usage_async() or get_cdrs_for_billing() instead"
                )
                return _native_rate(event_type, quantity, unit,
                                    bundle_remaining, unit_price_oob,
                                    customer_credit_type, prefix="[cgrates-fallback]")
            return loop.run_until_complete(
                self.rate_usage_async(event_type, quantity, unit,
                                      bundle_remaining, unit_price_oob,
                                      customer_credit_type, **kwargs)
            )
        except Exception as e:
            log.error(f"CGRateS rate_usage failed: {e}")
            return _native_rate(event_type, quantity, unit,
                                bundle_remaining, unit_price_oob,
                                customer_credit_type, prefix="[cgrates-error-fallback]")

    async def rate_usage_async(
        self,
        event_type: str,
        quantity: Decimal,
        unit: str,
        bundle_remaining: int,
        unit_price_oob: int,
        customer_credit_type: str,
        account: str = "",
        origin_id: str = "",
        **kwargs,
    ) -> RatingResult:
        """
        Async path for manually submitted usage events.
        Submits a CDR to CGRateS and returns the rated result.
        Not used in the normal MVNO flow.
        """
        if not account:
            log.warning("CGRateS rate_usage_async: no account — using native rater")
            return _native_rate(event_type, quantity, unit,
                                bundle_remaining, unit_price_oob, customer_credit_type)

        from app.engine.cgrates_utils import build_cgr_event, submit_process_cdr
        try:
            result = await submit_process_cdr(
                self.client, event_type, quantity, unit,
                account, origin_id or str(uuid.uuid4()),
                customer_credit_type, self.tenant,
            )
            return result
        except Exception as e:
            log.error(f"CGRateS ProcessCDR failed for {account}: {e}")
            return _native_rate(event_type, quantity, unit,
                                bundle_remaining, unit_price_oob,
                                customer_credit_type, prefix="[cgrates-error-fallback]")

    # ── Primary integration methods ────────────────────────────────────────

    async def get_cdrs_for_billing(
        self,
        period_start: datetime,
        period_end:   datetime,
        accounts:     list[str] | None = None,
    ) -> list[CGRatesCDR]:
        """
        Pull rated CDRs from CGRateS for a billing period.
        This is the primary method called during Orbi billing runs.
        """
        return await self.client.get_cdrs(period_start, period_end, accounts)

    async def topup_balance(
        self,
        account:      str,
        amount_pence: int,
        package_name: str = "",
    ) -> AddBalanceResult:
        """
        Top up a CGRateS account balance.
        Called by Orbi when a customer makes a prepaid payment.
        """
        result = await self.client.add_balance(account, amount_pence, package_name)
        if result.ok:
            log.info(f"CGRateS topup: {amount_pence}p → {account}")
        else:
            log.error(f"CGRateS topup failed for {account}: {result.error}")
        return result

    async def get_account_balance(self, account: str) -> CGRatesBalance:
        """Fetch real-time balance from CGRateS for UI display."""
        return await self.client.get_account(account)

    async def health_check(self) -> dict:
        ok = await self.client.ping()
        return {
            "status": "ok" if ok else "unreachable",
            "engine": self.get_name(),
        }


# ── Native rater fallback ─────────────────────────────────────────────────

def _native_rate(
    event_type: str,
    quantity: Decimal,
    unit: str,
    bundle_remaining: int,
    unit_price_oob: int,
    customer_credit_type: str,
    prefix: str = "",
) -> RatingResult:
    """Run the Orbi native rater. Used when CGRateS is unavailable."""
    from app.engine import OrbiNativeRater
    result = OrbiNativeRater().rate_usage(
        event_type, quantity, unit,
        bundle_remaining, unit_price_oob, customer_credit_type
    )
    if prefix:
        result.description = f"{prefix} {result.description}"
    return result
