"""
Orbi — Charging Engine Abstraction Layer

OCS_MODE in config determines which engine is active:

  orbi-native  Orbi's built-in rater. Handles bundle deduction, OOB
               charging, and balance management entirely within Orbi's DB.
               No external dependencies. Default.

  cgrates      Delegates rating and balance management to CGRateS.
               Orbi handles invoicing by pulling rated CDRs from CGRateS.
               Topups call CGRateS AddBalance directly.

Switching: change OCS_MODE in .env, restart. Nothing else changes.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import logging

log = logging.getLogger(__name__)


# ── Result types ──────────────────────────────────────────────────────────

@dataclass
class RatingResult:
    charged_amount:  int    # cents — 0 if fully covered by bundle
    bundle_deducted: int    # natural units deducted from bundle
    bundle_remaining: int   # natural units remaining
    out_of_bundle:   bool
    description:     str
    service_type:    str


@dataclass
class DebitResult:
    success:        bool
    debited_amount: int
    new_balance:    int
    message:        str


# ── Interface ─────────────────────────────────────────────────────────────

class IChargingEngine(ABC):
    """
    Every OCS adapter must implement this interface.
    The rest of Orbi calls only these methods — never a concrete class.
    """
    @abstractmethod
    def rate_usage(self, event_type: str, quantity: Decimal, unit: str,
                   bundle_remaining: int, unit_price_oob: int,
                   customer_credit_type: str, **kwargs) -> RatingResult: ...

    @abstractmethod
    def check_balance(self, balance_cents: int, required_cents: int) -> bool: ...

    @abstractmethod
    def get_name(self) -> str: ...


# ── Orbi native rater ─────────────────────────────────────────────────────

class OrbiNativeRater(IChargingEngine):
    """
    Orbi's built-in rating engine. Used when OCS_MODE=orbi-native.
    Handles bundle deduction and OOB charging with pure Python arithmetic.
    """

    def get_name(self) -> str:
        return "orbi-native-v1"

    def check_balance(self, balance_cents: int, required_cents: int) -> bool:
        return balance_cents >= required_cents

    def rate_usage(self, event_type: str, quantity: Decimal, unit: str,
                   bundle_remaining: int, unit_price_oob: int,
                   customer_credit_type: str, **kwargs) -> RatingResult:
        qty = self._normalise(quantity, unit)
        svc = {"data": "data", "voice": "voice", "sms": "sms"}.get(event_type, "custom")
        lbl = {"data": "MB", "voice": "min", "sms": "SMS"}.get(event_type, "unit")

        if bundle_remaining <= 0:
            charged = int((qty * Decimal(unit_price_oob)).to_integral_value(ROUND_HALF_UP))
            return RatingResult(
                charged_amount=charged, bundle_deducted=0,
                bundle_remaining=0, out_of_bundle=True,
                description=f"{qty:.1f} {lbl} @ {unit_price_oob}p/unit (out-of-bundle)",
                service_type=svc,
            )

        deducted      = min(int(qty), bundle_remaining)
        oob_qty       = max(Decimal("0"), qty - Decimal(bundle_remaining))
        new_remaining = max(0, bundle_remaining - int(qty))
        charged       = 0
        oob           = False

        if oob_qty > 0:
            charged = int((oob_qty * Decimal(unit_price_oob)).to_integral_value(ROUND_HALF_UP))
            oob     = True
            desc    = f"{qty:.1f} {lbl} — {deducted} from bundle, {oob_qty:.1f} @ {unit_price_oob}p OOB"
        else:
            desc = f"{qty:.1f} {lbl} deducted from bundle"

        return RatingResult(
            charged_amount=charged, bundle_deducted=deducted,
            bundle_remaining=new_remaining, out_of_bundle=oob,
            description=desc, service_type=svc,
        )

    def _normalise(self, quantity: Decimal, unit: str) -> Decimal:
        u = unit.lower()
        if u == "bytes":
            return (quantity / Decimal("1048576")).quantize(Decimal("0.001"), ROUND_HALF_UP)
        if u == "seconds":
            return (quantity / Decimal("60")).quantize(Decimal("0.001"), ROUND_HALF_UP)
        return quantity


# ── Registry ──────────────────────────────────────────────────────────────

_ENGINES: dict[str, IChargingEngine] = {
    "orbi-native": OrbiNativeRater(),
}

def get_engine(name: str) -> IChargingEngine:
    if name not in _ENGINES:
        raise ValueError(f"Unknown engine: '{name}'. Available: {list(_ENGINES)}")
    return _ENGINES[name]

def register_engine(name: str, engine: IChargingEngine) -> None:
    _ENGINES[name] = engine
    log.info(f"Charging engine registered: {name} → {engine.get_name()}")

def get_active_engine() -> IChargingEngine:
    """
    Return the currently configured OCS engine based on OCS_MODE setting.
    Always reads from config — no caching — so .env changes take effect on restart.
    """
    from app.config import settings
    mode = settings.OCS_MODE

    if mode == "cgrates":
        if "cgrates" not in _ENGINES:
            raise RuntimeError(
                "OCS_MODE=cgrates but CGRateS engine not initialised. "
                "Check CGRATES_API_URL is set and app startup completed."
            )
        return _ENGINES["cgrates"]

    # Default: orbi-native
    return _ENGINES["orbi-native"]


def init_engine_from_config() -> IChargingEngine:
    """
    Read OCS_MODE from config and initialise the appropriate engine.
    Called once at app startup from main.py lifespan.
    """
    from app.config import settings

    if settings.OCS_MODE == "cgrates":
        if not settings.CGRATES_API_URL:
            raise RuntimeError(
                "OCS_MODE=cgrates requires CGRATES_API_URL to be set in .env"
            )
        from app.engine.cgrates import CGRatesChargingEngine
        engine = CGRatesChargingEngine(
            base_url=settings.CGRATES_API_URL,
            tenant=settings.CGRATES_TENANT,
            verify_ssl=settings.CGRATES_VERIFY_SSL,
            timeout=settings.CGRATES_TIMEOUT_SECONDS,
        )
        register_engine("cgrates", engine)
        log.info(f"OCS mode: cgrates @ {settings.CGRATES_API_URL} "
                 f"tenant={settings.CGRATES_TENANT}")
        return engine

    else:
        engine = _ENGINES["orbi-native"]
        log.info("OCS mode: orbi-native (built-in rater)")
        return engine
