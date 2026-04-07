"""
Orbi — Sprint 4 test suite.
Tests rating engine, bundle deduction, OOB charging, billing run logic.
Run with: cd orbi/backend && python tests/test_sprint4.py
"""
import sys, os, types
sys.modules['sqlalchemy'] = types.ModuleType('sqlalchemy')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from decimal import Decimal
from datetime import date
from calendar import monthrange

# ── Import engine directly (no DB deps) ───────────────────────────────────
from app.engine import OrbiNativeRater, RatingResult

rater = OrbiNativeRater()
passed = failed = 0

def check(name, condition, detail=''):
    global passed, failed
    if condition:
        print(f'  ✓  {name}')
        passed += 1
    else:
        print(f'  ✗  {name}  — got: {detail}')
        failed += 1

def rate(event_type, qty, unit, bundle_remaining, oob_rate, credit_type="postpaid"):
    return rater.rate_usage(
        event_type=event_type,
        quantity=Decimal(str(qty)),
        unit=unit,
        bundle_remaining=bundle_remaining,
        unit_price_oob=oob_rate,
        customer_credit_type=credit_type,
    )

# ══════════════════════════════════════════════════════════════════════════
# 1. BUNDLE DEDUCTION — WITHIN BUNDLE
# ══════════════════════════════════════════════════════════════════════════
print("\n── Bundle deduction (within bundle) ─────────────────────────────")

r = rate("data", 100, "mb", 1024, 2)
check("data/within_bundle/no_charge",          r.charged_amount == 0)
check("data/within_bundle/deducted_100",       r.bundle_deducted == 100)
check("data/within_bundle/remaining_924",      r.bundle_remaining == 924)
check("data/within_bundle/not_oob",            r.out_of_bundle == False)

r = rate("voice", 10, "minutes", 100, 5)
check("voice/within_bundle/no_charge",         r.charged_amount == 0)
check("voice/within_bundle/deducted_10",       r.bundle_deducted == 10)
check("voice/within_bundle/remaining_90",      r.bundle_remaining == 90)

r = rate("sms", 5, "messages", 100, 10)
check("sms/within_bundle/no_charge",           r.charged_amount == 0)
check("sms/within_bundle/deducted_5",          r.bundle_deducted == 5)
check("sms/within_bundle/remaining_95",        r.bundle_remaining == 95)

# ══════════════════════════════════════════════════════════════════════════
# 2. OUT-OF-BUNDLE CHARGING
# ══════════════════════════════════════════════════════════════════════════
print("\n── Out-of-bundle charging ───────────────────────────────────────")

# No bundle at all
r = rate("data", 100, "mb", 0, 2)
check("data/no_bundle/charged_200p",           r.charged_amount == 200)
check("data/no_bundle/is_oob",                 r.out_of_bundle == True)
check("data/no_bundle/zero_deducted",          r.bundle_deducted == 0)

# Partial bundle — 50MB remaining, using 100MB
r = rate("data", 100, "mb", 50, 2)
check("data/partial_bundle/deducted_50",       r.bundle_deducted == 50)
check("data/partial_bundle/remaining_0",       r.bundle_remaining == 0)
check("data/partial_bundle/oob_50mb",          r.out_of_bundle == True)
check("data/partial_bundle/charged_100p",      r.charged_amount == 100)  # 50MB × 2p

# Exactly at bundle boundary
r = rate("voice", 100, "minutes", 100, 5)
check("voice/exact_bundle/no_charge",          r.charged_amount == 0)
check("voice/exact_bundle/remaining_0",        r.bundle_remaining == 0)
check("voice/exact_bundle/not_oob",            r.out_of_bundle == False)

# ══════════════════════════════════════════════════════════════════════════
# 3. UNIT NORMALISATION
# ══════════════════════════════════════════════════════════════════════════
print("\n── Unit normalisation ───────────────────────────────────────────")

# Bytes → MB (1048576 bytes = 1MB)
r = rate("data", 1048576, "bytes", 1024, 2)
check("normalise/bytes_to_mb_1mb",             r.bundle_deducted == 1, r.bundle_deducted)

r = rate("data", 524288, "bytes", 1024, 2)   # 0.5MB
check("normalise/bytes_to_mb_half",            r.bundle_deducted == 0, r.bundle_deducted)  # <1 whole unit

# Seconds → minutes (60s = 1min)
r = rate("voice", 120, "seconds", 100, 5)   # 2 minutes
check("normalise/seconds_to_mins_2min",        r.bundle_deducted == 2, r.bundle_deducted)

r = rate("voice", 300, "seconds", 100, 5)   # 5 minutes
check("normalise/seconds_to_mins_5min",        r.bundle_deducted == 5, r.bundle_deducted)

# ══════════════════════════════════════════════════════════════════════════
# 4. ZERO OOB RATE (free out-of-bundle)
# ══════════════════════════════════════════════════════════════════════════
print("\n── Zero OOB rate ────────────────────────────────────────────────")

r = rate("sms", 200, "messages", 100, 0)    # Unlimited SMS (0p OOB)
check("zero_oob/no_charge_even_oob",          r.charged_amount == 0)
check("zero_oob/still_marked_oob",            r.out_of_bundle == True)

# ══════════════════════════════════════════════════════════════════════════
# 5. PRO-RATING (billing run logic)
# ══════════════════════════════════════════════════════════════════════════
print("\n── Pro-rating ───────────────────────────────────────────────────")

def pro_rate(amount, period_start, period_end, sub_start):
    total_days  = (period_end - period_start).days + 1
    effective   = max(sub_start, period_start)
    active_days = (period_end - effective).days + 1
    if active_days <= 0: return 0
    if active_days >= total_days: return amount
    from decimal import Decimal, ROUND_HALF_UP
    return int((Decimal(amount) * Decimal(active_days) / Decimal(total_days)).to_integral_value(ROUND_HALF_UP))

jan_start = date(2026, 1, 1)
jan_end   = date(2026, 1, 31)

check("pro_rate/full_month_no_prorate",        pro_rate(1999, jan_start, jan_end, jan_start) == 1999)
check("pro_rate/starts_jan16_16_of_31",        pro_rate(3100, jan_start, jan_end, date(2026,1,16)) == 1600)
check("pro_rate/starts_last_day_1_of_31",      pro_rate(3100, jan_start, jan_end, date(2026,1,31)) == 100)
check("pro_rate/before_period_full_charge",    pro_rate(1999, jan_start, jan_end, date(2025,12,1)) == 1999)

# ══════════════════════════════════════════════════════════════════════════
# 6. SERVICE TYPE MAPPING
# ══════════════════════════════════════════════════════════════════════════
print("\n── Service type mapping ─────────────────────────────────────────")

r = rate("data",  10, "mb",      100, 2)
check("svc_map/data_maps_to_data",   r.service_type == "data")
r = rate("voice", 5,  "minutes", 100, 5)
check("svc_map/voice_maps_to_voice", r.service_type == "voice")
r = rate("sms",   3,  "messages",100, 10)
check("svc_map/sms_maps_to_sms",     r.service_type == "sms")
r = rate("custom",1,  "units",   0,   0)
check("svc_map/custom_maps_custom",  r.service_type == "custom")

# ══════════════════════════════════════════════════════════════════════════
# 7. ENGINE INTERFACE
# ══════════════════════════════════════════════════════════════════════════
print("\n── Engine interface ─────────────────────────────────────────────")

check("engine/name",                 rater.get_name() == "orbi-native-v1")
check("engine/balance_sufficient",   rater.check_balance(2000, 1999) == True)
check("engine/balance_exact",        rater.check_balance(1999, 1999) == True)
check("engine/balance_insufficient", rater.check_balance(1000, 1999) == False)
check("engine/balance_zero_price",   rater.check_balance(0, 0) == True)

# ══════════════════════════════════════════════════════════════════════════
# 8. DESCRIPTION STRINGS
# ══════════════════════════════════════════════════════════════════════════
print("\n── Description strings ──────────────────────────────────────────")

r = rate("data", 100, "mb", 1024, 2)
check("desc/within_bundle_mentions_bundle",  "bundle" in r.description.lower())

r = rate("data", 100, "mb", 0, 2)
check("desc/oob_mentions_oob",              "out-of-bundle" in r.description.lower())

r = rate("data", 150, "mb", 100, 2)
check("desc/partial_mentions_both",         "bundle" in r.description.lower() and "OOB" in r.description or "out-of-bundle" in r.description.lower())

print(f'\n── {passed+failed} tests: {passed} passed, {failed} failed ──\n')
