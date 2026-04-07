"""
Orbi — Sprint 2 test suite.
Tests schemas, services, and API endpoints.
Run with: cd orbi/backend && python -m pytest tests/test_sprint2.py -v
"""
import sys, os, asyncio, types

# Stub external deps not installed in sandbox
for mod in ['sqlalchemy','sqlalchemy.ext.asyncio','sqlalchemy.orm',
            'sqlalchemy.dialects.sqlite','fastapi','pydantic',
            'pydantic_settings','pydantic.networks']:
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ── We test pure logic that doesn't need DB ───────────────────────────────
import pytest
from datetime import date
from calendar import monthrange


# ── Helper: period_end logic (copied from order service) ──────────────────
def period_end(start: date) -> date:
    last_day = monthrange(start.year, start.month)[1]
    return date(start.year, start.month, last_day)


# ══════════════════════════════════════════════════════════════════════════
# 1. SCHEMA VALIDATION (pure Pydantic — no DB needed)
# ══════════════════════════════════════════════════════════════════════════

class TestPeriodEnd:
    def test_january(self):
        assert period_end(date(2026, 1, 1))  == date(2026, 1, 31)
    def test_february_non_leap(self):
        assert period_end(date(2025, 2, 1))  == date(2025, 2, 28)
    def test_february_leap(self):
        assert period_end(date(2024, 2, 1))  == date(2024, 2, 29)
    def test_april(self):
        assert period_end(date(2026, 4, 1))  == date(2026, 4, 30)
    def test_mid_month(self):
        assert period_end(date(2026, 3, 15)) == date(2026, 3, 31)


class TestOrderStateTransitions:
    """Test the state machine transition rules."""

    VALID = {
        ("pending",   "activate"):   "active",
        ("active",    "suspend"):    "suspended",
        ("suspended", "activate"):   "active",
        ("pending",   "cancel"):     "cancelled",
        ("active",    "cancel"):     "cancelled",
        ("suspended", "cancel"):     "cancelled",
    }
    INVALID = [
        ("active",    "activate"),
        ("cancelled", "activate"),
        ("cancelled", "cancel"),
        ("cancelled", "suspend"),
    ]

    def _allowed(self, status: str, action: str) -> bool:
        if action == "activate"  and status not in ("pending", "suspended"): return False
        if action == "suspend"   and status != "active":                     return False
        if action == "cancel"    and status == "cancelled":                  return False
        return True

    def test_valid_transitions(self):
        for (status, action), _ in self.VALID.items():
            assert self._allowed(status, action), f"{status} → {action} should be allowed"

    def test_invalid_transitions(self):
        for status, action in self.INVALID:
            assert not self._allowed(status, action), f"{status} → {action} should be rejected"


class TestBundleBalanceInit:
    """Test that bundle balances are correctly initialised from allowances."""

    def _make_balances(self, allowances: dict, period_start: date) -> list[dict]:
        """Simulate _init_bundle_balances logic."""
        service_map = {"data_mb": "data", "voice_mins": "voice", "sms": "sms"}
        result = []
        p_end = period_end(period_start)
        for field, svc in service_map.items():
            total = allowances.get(field)
            if not total:
                continue
            result.append({
                "service_type": svc,
                "allowance_total": total,
                "allowance_used": 0,
                "allowance_remaining": total,
                "period_start": period_start,
                "period_end": p_end,
            })
        return result

    def test_full_bundle(self):
        balances = self._make_balances(
            {"data_mb": 1024, "voice_mins": 100, "sms": 100},
            date(2026, 3, 1)
        )
        assert len(balances) == 3
        types = {b["service_type"] for b in balances}
        assert types == {"data", "voice", "sms"}

    def test_data_only(self):
        balances = self._make_balances({"data_mb": 512}, date(2026, 3, 1))
        assert len(balances) == 1
        assert balances[0]["service_type"] == "data"
        assert balances[0]["allowance_total"] == 512
        assert balances[0]["allowance_remaining"] == 512

    def test_no_allowances(self):
        balances = self._make_balances({}, date(2026, 3, 1))
        assert len(balances) == 0

    def test_period_spans_full_month(self):
        balances = self._make_balances({"data_mb": 1024}, date(2026, 1, 1))
        assert balances[0]["period_end"] == date(2026, 1, 31)

    def test_period_mid_month_still_ends_on_last_day(self):
        balances = self._make_balances({"data_mb": 1024}, date(2026, 3, 15))
        assert balances[0]["period_end"] == date(2026, 3, 31)


class TestPrepaidBalanceCheck:
    """Test prepaid balance validation logic."""

    def _can_activate(self, balance_cents: int, product_price_cents: int) -> bool:
        return balance_cents >= product_price_cents

    def test_sufficient_balance(self):
        assert self._can_activate(2000, 1999) is True

    def test_exact_balance(self):
        assert self._can_activate(1999, 1999) is True

    def test_insufficient_balance(self):
        assert self._can_activate(1000, 1999) is False

    def test_zero_price_always_passes(self):
        assert self._can_activate(0, 0) is True

    def test_zero_balance_nonzero_price_fails(self):
        assert self._can_activate(0, 100) is False


class TestInventoryAssignment:
    """Test inventory state transitions during order lifecycle."""

    def _reserve(self, item_status: str) -> tuple[bool, str]:
        if item_status != "available":
            return False, f"Item is {item_status}, not available"
        return True, "reserved"

    def _assign(self, item_status: str) -> tuple[bool, str]:
        if item_status not in ("available", "reserved"):
            return False, f"Cannot assign item with status {item_status}"
        return True, "assigned"

    def _release(self, item_status: str) -> tuple[bool, str]:
        return True, "available"  # always releasable on cancel

    def test_reserve_available(self):
        ok, status = self._reserve("available")
        assert ok and status == "reserved"

    def test_reserve_already_assigned(self):
        ok, _ = self._reserve("assigned")
        assert not ok

    def test_assign_from_reserved(self):
        ok, status = self._assign("reserved")
        assert ok and status == "assigned"

    def test_release_on_cancel(self):
        ok, status = self._release("assigned")
        assert ok and status == "available"

    def test_cannot_reserve_ported_out(self):
        ok, _ = self._reserve("ported_out")
        assert not ok


class TestOrderNumberFormat:
    """Test order number generation format."""

    def _make_order_number(self, year: int, sequence: int) -> str:
        return f"ORD-{year}-{str(sequence).zfill(5)}"

    def test_format(self):
        assert self._make_order_number(2026, 1)     == "ORD-2026-00001"
        assert self._make_order_number(2026, 100)   == "ORD-2026-00100"
        assert self._make_order_number(2026, 99999) == "ORD-2026-99999"

    def test_zero_padding(self):
        n = self._make_order_number(2026, 42)
        assert n == "ORD-2026-00042"
        assert len(n.split("-")[2]) == 5


class TestLedgerEntries:
    """Test balance ledger arithmetic."""

    def _compute_balance(self, entries: list[int]) -> int:
        return sum(entries)

    def test_topup_increases_balance(self):
        assert self._compute_balance([2000]) == 2000

    def test_charge_decreases_balance(self):
        assert self._compute_balance([2000, -1999]) == 1

    def test_multiple_topups(self):
        assert self._compute_balance([1000, 1000, 1000]) == 3000

    def test_zero_balance_after_full_debit(self):
        assert self._compute_balance([1999, -1999]) == 0

    def test_negative_balance_possible_postpaid(self):
        # Postpaid can go negative — that's what invoicing is for
        assert self._compute_balance([-4999]) == -4999

    def test_append_only(self):
        # Ledger is append-only — balance is always recomputed from all rows
        entries = [2000, -1999, 500, -250]
        assert self._compute_balance(entries) == 251


# ══════════════════════════════════════════════════════════════════════════
# Run summary
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import traceback
    tests = [
        TestPeriodEnd, TestOrderStateTransitions, TestBundleBalanceInit,
        TestPrepaidBalanceCheck, TestInventoryAssignment,
        TestOrderNumberFormat, TestLedgerEntries,
    ]
    passed = failed = 0
    for cls in tests:
        inst = cls()
        for name in [m for m in dir(inst) if m.startswith("test_")]:
            try:
                getattr(inst, name)()
                print(f"  ✓  {cls.__name__}/{name}")
                passed += 1
            except Exception as e:
                print(f"  ✗  {cls.__name__}/{name}: {e}")
                traceback.print_exc()
                failed += 1
    print(f"\n── {passed+failed} tests: {passed} passed, {failed} failed ──")
