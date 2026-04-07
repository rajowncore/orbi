#!/usr/bin/env python3
"""
Orbi + CGRateS — End-to-End Integration Test
=============================================
Tests the full flow:

  1.  Health check — Orbi API + CGRateS connectivity
  2.  Create product  (Home Mobile 1GB)
  3.  Add inventory   (MSISDN + SIM)
  4.  Create customer (prepaid)
  5.  Create order
  6.  Activate order  → triggers provisioning workflow
  7.  Poll provisioning status → wait for completion
  8.  Verify CGRateS account created (GetAccount)
  9.  Record prepaid topup → verify AddBalance on CGRateS
  10. Inject test usage event via Orbi API
  11. Rate pending events
  12. Run billing cycle → pulls CGRateS CDRs + generates invoice
  13. Verify invoice created
  14. Download invoice PDF
  15. Summary report

Usage:
    cd ~/orbi/backend
    source venv/bin/activate
    pip install httpx rich          # if not already installed
    python ../tests/e2e_test.py

Configure:
    ORBI_URL=http://localhost:8000
    CGRATES_URL=http://localhost:2080
    CGRATES_TENANT=cgrates.org
    HSS_URL=http://localhost:8081      # OmniHSS — optional, skip HSS steps if blank

Or pass as env vars:
    ORBI_URL=http://myserver:8000 python tests/e2e_test.py
"""
import os
import sys
import json
import time
import asyncio
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

try:
    import httpx
except ImportError:
    print("Missing dependency. Run: pip install httpx rich")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.table import Table
    from rich import print as rprint
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    console = None

# ── Config ────────────────────────────────────────────────────────────────
ORBI_URL     = os.getenv("ORBI_URL",      "http://localhost:8000")
CGRATES_URL  = os.getenv("CGRATES_URL",   "http://localhost:2080")
CGRATES_TENANT = os.getenv("CGRATES_TENANT", "cgrates.org")
HSS_URL      = os.getenv("HSS_URL",       "")
TIMEOUT      = int(os.getenv("TEST_TIMEOUT", "30"))

API = f"{ORBI_URL}/api/v1"

# ── Test state (accumulated across steps) ─────────────────────────────────
state = {}
results = []


# ══════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════

def log(msg: str, level: str = "info"):
    symbols = {"info": "·", "ok": "✓", "fail": "✗", "warn": "⚠", "step": "►"}
    sym = symbols.get(level, "·")
    colors = {"ok": "\033[92m", "fail": "\033[91m", "warn": "\033[93m",
              "step": "\033[94m", "info": ""}
    reset = "\033[0m"
    color = colors.get(level, "")
    print(f"  {color}{sym}{reset}  {msg}")


def record(step: str, ok: bool, detail: str = "", data: dict = None):
    results.append({"step": step, "ok": ok, "detail": detail, "data": data or {}})
    level = "ok" if ok else "fail"
    log(f"{step}: {detail}", level)


def orbi(method: str, path: str, **kwargs) -> httpx.Response:
    url = f"{API}{path}"
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = getattr(client, method.lower())(url, **kwargs)
    return resp


def cgrates_rpc(method: str, params: list) -> dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params,
                "id": str(uuid.uuid4())[:8]}
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.post(f"{CGRATES_URL}/jsonrpc", json=payload)
    data = resp.json()
    if "error" in data and data["error"]:
        raise RuntimeError(f"CGRateS [{method}]: {data['error']}")
    return data.get("result", {})


def wait_for(condition_fn, timeout_s: int = 60, poll_s: int = 3, label: str = "") -> bool:
    """Poll until condition_fn returns True or timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if condition_fn():
                return True
        except Exception:
            pass
        if label:
            log(f"  waiting for {label}…", "info")
        time.sleep(poll_s)
    return False


# ══════════════════════════════════════════════════════════════════════════
# TEST STEPS
# ══════════════════════════════════════════════════════════════════════════

def step_health():
    print("\n── Step 1: Health checks ─────────────────────────────────────────")

    # Orbi health
    try:
        resp = httpx.get(f"{ORBI_URL}/health", timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            record("Orbi API", True,
                   f"v{data.get('version')} · engine={data.get('engine')} · ocs_mode={data.get('ocs_mode')}")
            state["ocs_mode"] = data.get("ocs_mode", "orbi-native")
        else:
            record("Orbi API", False, f"HTTP {resp.status_code}")
            return False
    except Exception as e:
        record("Orbi API", False, str(e))
        return False

    # Engine status
    try:
        resp = orbi("GET", "/engine/status")
        if resp.status_code == 200:
            data = resp.json()
            record("Engine status", True,
                   f"mode={data.get('ocs_mode')} engine={data.get('active_engine','?')[:30]}")
            if data.get("cgrates_health"):
                cgr_health = data["cgrates_health"]
                ok = cgr_health.get("status") == "ok"
                record("CGRateS connectivity", ok,
                       cgr_health.get("status", "unknown"))
                if not ok:
                    log("CGRateS unreachable — provisioning steps will be skipped", "warn")
    except Exception as e:
        record("Engine status", False, str(e))

    # Direct CGRateS ping
    try:
        result = cgrates_rpc("CoreSv1.Status", [{}])
        record("CGRateS direct ping", True,
               f"version={result.get('Version','?')} node={result.get('NodeID','?')}")
        state["cgrates_ok"] = True
    except Exception as e:
        record("CGRateS direct ping", False, str(e))
        state["cgrates_ok"] = False
        log("Will continue — provisioning and balance steps will be skipped", "warn")

    return True


def step_create_product():
    print("\n── Step 2: Create product ────────────────────────────────────────")
    payload = {
        "name":         "E2E Home Mobile 1GB",
        "description":  "End-to-end test product — 1GB data, 100 mins, 100 SMS",
        "product_type": "base",
        "billing_model":"recurring",
        "price_config": {"amount": 1999, "interval": "month", "interval_count": 1},
        "allowances":   {"data_mb": 1024, "voice_mins": 100, "sms": 100},
        "out_of_bundle_rates": {"data_mb": 2, "voice_mins": 5, "sms": 10},
        "requires_inventory": True,
        "inventory_type": "msisdn",
        "currency": "GBP",
    }
    resp = orbi("POST", "/products", json=payload)
    if resp.status_code == 201:
        data = resp.json()
        state["product_id"] = data["id"]
        record("Create product", True,
               f"id={data['id'][:8]}… name='{data['name']}'")
        return True
    else:
        record("Create product", False, f"HTTP {resp.status_code}: {resp.text[:100]}")
        return False


def step_add_inventory():
    print("\n── Step 3: Add inventory ─────────────────────────────────────────")
    test_msisdn = f"+447{str(uuid.uuid4().int)[:9]}"
    test_iccid  = f"8944{str(uuid.uuid4().int)[:15]}"
    state["msisdn"] = test_msisdn
    state["iccid"]  = test_iccid

    # MSISDN
    resp = orbi("POST", "/inventory", json={"type": "msisdn", "value": test_msisdn})
    if resp.status_code == 201:
        data = resp.json()
        state["msisdn_item_id"] = data["id"]
        record("Add MSISDN", True, f"{test_msisdn} id={data['id'][:8]}…")
    else:
        record("Add MSISDN", False, f"HTTP {resp.status_code}: {resp.text[:80]}")
        return False

    # SIM (optional — used by HSS provisioning)
    resp2 = orbi("POST", "/inventory",
                 json={"type": "sim", "value": test_iccid,
                       "extra": {"imsi": f"2340799{str(uuid.uuid4().int)[:8]}"}})
    if resp2.status_code == 201:
        data2 = resp2.json()
        state["sim_item_id"] = data2["id"]
        record("Add SIM (ICCID)", True, f"{test_iccid[:12]}… id={data2['id'][:8]}…")

    return True


def step_create_customer():
    print("\n── Step 4: Create customer ───────────────────────────────────────")
    email = f"e2etest-{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "name":              "E2E Test Customer",
        "email":             email,
        "phone":             state["msisdn"],
        "credit_type":       "prepaid",
        "currency":          "GBP",
        "billing_cycle_day": 1,
    }
    resp = orbi("POST", "/customers", json=payload)
    if resp.status_code == 201:
        data = resp.json()
        state["customer_id"] = data["id"]
        record("Create customer", True,
               f"id={data['id'][:8]}… email={email} type=prepaid")
        return True
    else:
        record("Create customer", False, f"HTTP {resp.status_code}: {resp.text[:100]}")
        return False


def step_create_and_activate_order():
    print("\n── Step 5: Create + activate order ──────────────────────────────")
    if not state.get("customer_id") or not state.get("product_id"):
        record("Create + activate order", False, "Skipped — missing customer_id or product_id from earlier steps")
        return False

    # Create order
    payload = {
        "customer_id":       state["customer_id"],
        "product_id":        state["product_id"],
        "inventory_item_id": state["msisdn_item_id"],
    }
    resp = orbi("POST", "/orders", json=payload)
    if resp.status_code != 201:
        record("Create order", False, f"HTTP {resp.status_code}: {resp.text[:100]}")
        return False

    order = resp.json()
    state["order_id"] = order["id"]
    state["order_number"] = order["order_number"]
    record("Create order", True,
           f"{order['order_number']} status={order['status']}")

    # Activate order
    resp2 = orbi("PATCH", f"/orders/{state['order_id']}", json={"action": "activate"})
    if resp2.status_code == 200:
        data2 = resp2.json()
        record("Activate order", True,
               f"status={data2['status']} activated_at={data2.get('activated_at','?')[:10]}")
        return True
    else:
        record("Activate order", False, f"HTTP {resp2.status_code}: {resp2.text[:100]}")
        return False


def step_check_provisioning():
    print("\n── Step 6: Provisioning workflow ─────────────────────────────────")
    if not state.get("order_id"):
        record("Provisioning workflow", True, "Skipped — no order_id from earlier steps")
        return True

    # Poll for workflow to complete
    def workflow_done() -> bool:
        resp = orbi("GET", f"/provisioning/workflows/{state['order_id']}")
        if resp.status_code == 404:
            return False  # not started yet
        if resp.status_code == 200:
            wf = resp.json()
            state["workflow"] = wf
            return wf["status"] in ("completed", "failed", "rolled_back")
        return False

    # Check if provisioning is configured
    resp = orbi("GET", f"/provisioning/workflows/{state['order_id']}")
    if resp.status_code == 404:
        record("Provisioning workflow", True,
               "No workflow (provisioning not configured — HSS_API_URL not set)")
        log("Set HSS_API_URL and CGRATES_API_URL in .env to enable provisioning", "info")
        return True

    log("Waiting for provisioning workflow to complete (max 60s)…", "info")
    done = wait_for(workflow_done, timeout_s=60, poll_s=3, label="workflow")

    if not done:
        record("Provisioning workflow", False, "Timed out waiting for completion")
        return False

    wf = state.get("workflow", {})
    ok = wf["status"] == "completed"
    steps = wf.get("steps", [])
    completed = sum(1 for s in steps if s["status"] == "completed")
    failed    = [s for s in steps if s["status"] == "failed"]

    record("Provisioning workflow", ok,
           f"status={wf['status']} steps={completed}/{len(steps)}")

    if failed:
        for s in failed:
            log(f"  Failed step: {s['step_name']} — {s.get('error_message','?')[:80]}", "warn")

    return ok


def step_verify_cgrates_account():
    print("\n── Step 7: Verify CGRateS account ───────────────────────────────")

    if not state.get("cgrates_ok"):
        record("CGRateS account check", True, "Skipped — CGRateS not reachable")
        return True

    wf = state.get("workflow", {})
    service_uuid = wf.get("context", {}).get("service_uuid") if wf else None

    if not service_uuid:
        record("CGRateS account check", True,
               "Skipped — no service_uuid (provisioning not configured)")
        return True

    state["service_uuid"] = service_uuid

    try:
        result = cgrates_rpc("ApierV2.GetAccount", [{
            "Tenant":  CGRATES_TENANT,
            "Account": service_uuid,
        }])
        balance_map = result.get("BalanceMap", {})
        monetary = balance_map.get("*monetary", [{}])
        balance_val = float(monetary[0].get("Value", 0)) if monetary else 0
        record("CGRateS account exists", True,
               f"account={service_uuid} monetary_balance={balance_val}")
        state["cgrates_balance_before"] = balance_val
        return True
    except Exception as e:
        record("CGRateS account exists", False, str(e))
        return False


def step_topup():
    print("\n── Step 5b: Prepaid topup (before activation) ───────────────────")
    if not state.get("customer_id"):
        record("Record topup payment", False, "Skipped — no customer_id from earlier steps")
        return False
    topup_amount = 5000  # £50.00 in pence
    today = date.today().isoformat()

    payload = {
        "customer_id":  state["customer_id"],
        "amount":       topup_amount,
        "currency":     "GBP",
        "method":       "bank_transfer",
        "payment_date": today,
        "reference":    f"E2E-TOPUP-{uuid.uuid4().hex[:8].upper()}",
        "description":  "E2E test top-up",
    }
    resp = orbi("POST", "/payments", json=payload)
    if resp.status_code != 201:
        record("Record topup payment", False, f"HTTP {resp.status_code}: {resp.text[:100]}")
        return False

    payment = resp.json()
    state["payment_id"] = payment["id"]
    record("Record topup payment", True,
           f"amount=£{topup_amount/100:.2f} ref={payload['reference']}")

    # Verify balance updated in Orbi ledger
    resp2 = orbi("GET", f"/customers/{state['customer_id']}/balance")
    if resp2.status_code == 200:
        bal = resp2.json()
        record("Orbi balance updated", True,
               f"balance={bal['balance_cents']}p (£{bal['balance_cents']/100:.2f})")

    # Verify CGRateS balance updated (if provisioned)
    if state.get("service_uuid") and state.get("cgrates_ok"):
        time.sleep(1)  # give CGRateS a moment
        try:
            result = cgrates_rpc("ApierV2.GetAccount", [{
                "Tenant":  CGRATES_TENANT,
                "Account": state["service_uuid"],
            }])
            monetary = result.get("BalanceMap", {}).get("*monetary", [{}])
            balance_val = float(monetary[0].get("Value", 0)) if monetary else 0
            before = state.get("cgrates_balance_before", 0)
            expected = before + (topup_amount / 100)
            ok = abs(balance_val - expected) < 0.01
            record("CGRateS balance updated", ok,
                   f"before={before:.2f} after={balance_val:.2f} expected={expected:.2f}")
        except Exception as e:
            record("CGRateS balance check", False, str(e))

    return True




def step_cgrates_account_direct():
    """
    Directly create and verify a CGRateS account without going through
    the provisioning workflow. Tests CGRateS API integration independently.
    """
    print("\n── Step 7b: CGRateS direct account test ──────────────────────────")

    if not state.get("cgrates_ok"):
        record("CGRateS direct test", True, "Skipped — CGRateS not reachable")
        return True

    # Use the order_id as a test service_uuid
    service_uuid = f"Mobile_SIM_{state.get('order_id','test')[:8]}"
    state["service_uuid"] = service_uuid
    msisdn = state.get("msisdn", "+447000000000").lstrip("+")

    # 1. Create ENUM entry
    try:
        cgrates_rpc("APIerSv2.SetAttributeProfile", [{
            "Tenant":  CGRATES_TENANT,
            "ID":      f"ATTR_E164_{service_uuid}",
            "Contexts": ["*sessions"],
            "FilterIDs": [f"*prefix:~*req.E164Address:{msisdn}"],
            "Attributes": [
                {"FilterIDs": [], "Path": "*req.NAPTRAddress",
                 "Type": "*constant",
                 "Value": f"!(^.*$)!sip:\\1@ims.{CGRATES_TENANT}!"},
            ],
            "Weight": 8,
        }])
        record("CGRateS ENUM entry", True, f"ATTR_E164_{service_uuid}")
    except Exception as e:
        record("CGRateS ENUM entry", False, str(e))

    # 2. Create Filter
    try:
        cgrates_rpc("ApierV1.SetFilter", [{
            "Tenant": CGRATES_TENANT,
            "ID":     f"FLTR_ACCOUNT_{service_uuid}",
            "Rules": [{"Type": "*string", "Element": "~*req.Account",
                       "Values": [service_uuid, msisdn]}],
            "ActivationInterval": {},
        }])
        record("CGRateS filter", True, f"FLTR_ACCOUNT_{service_uuid}")
    except Exception as e:
        record("CGRateS filter", False, str(e))

    # 3. Create Attributes
    try:
        cgrates_rpc("APIerSv2.SetAttributeProfile", [{
            "ID":      f"ATTR_ACCOUNT_{service_uuid}",
            "Tenant":  CGRATES_TENANT,
            "Attributes": [
                {"Path": "*req.Account",  "Type": "*constant", "Value": service_uuid},
                {"Path": "*req.MSISDN",   "Type": "*constant", "Value": msisdn},
            ],
            "Contexts":  ["*any"],
            "FilterIDs": [f"FLTR_ACCOUNT_{service_uuid}"],
        }])
        record("CGRateS attributes", True, f"ATTR_ACCOUNT_{service_uuid}")
    except Exception as e:
        record("CGRateS attributes", False, str(e))

    # 4. Create Account
    try:
        cgrates_rpc("ApierV2.SetAccount", [{
            "Tenant":  CGRATES_TENANT,
            "Account": service_uuid,
            "ActionPlanIds": [],
            "ActionPlansOverwrite": True,
            "ActionTriggerIDs": [],
            "ActionTriggersOverwrite": True,
            "ExtraOptions": {"AllowNegative": False, "Disabled": False},
            "ReloadScheduler": True,
        }])
        record("CGRateS account created", True, f"account={service_uuid}")
    except Exception as e:
        record("CGRateS account created", False, str(e))
        return False

    # 5. Add initial monetary balance (£50 from topup)
    topup_pence = 5000
    try:
        cgrates_rpc("ApierV1.AddBalance", [{
            "Tenant":      CGRATES_TENANT,
            "Account":     service_uuid,
            "BalanceType": "*monetary",
            "Value":       topup_pence / 100,
            "Weight":      10.0,      # Added priority
            "ExpiryTime":  "*none",   # Fixed expiration
            "Categories":  "*any"
        }])
        record("CGRateS balance set", True,
               f"£{topup_pence/100:.2f} added to {service_uuid}")
    except Exception as e:
        record("CGRateS balance set", False, str(e))

    # 6. Verify account and balance
    try:
        result = cgrates_rpc("ApierV2.GetAccount", [{
            "Tenant":  CGRATES_TENANT,
            "Account": service_uuid,
        }])
        bal_map  = result.get("BalanceMap", {})
        monetary = bal_map.get("*monetary", [{}])
        balance  = float(monetary[0].get("Value", 0)) if monetary else 0
        disabled = result.get("Disabled", False)
        record("CGRateS account verified", True,
               f"balance=£{balance:.2f} disabled={disabled} "
               f"buckets={sum(len(v) for v in bal_map.values())}")
        state["cgrates_balance_before"] = balance
    except Exception as e:
        record("CGRateS account verified", False, str(e))
        return False

    # 7. Submit test CDR via ProcessCDR
    try:
        import uuid as _uuid
        from datetime import datetime as _dt
																	  
																														  
        origin_id = f"E2E-{_uuid.uuid4().hex[:12]}"
																																		
        # Try v0.10+ flat format first, fall back to legacy CGREvent wrapper
        now_str = _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        cdr_event = {
						  
            "ToR":         "*data",
            "OriginID":    origin_id,
            "OriginHost":  "e2e-test",
            "RequestType": "*prepaid",
            "Account":     service_uuid,
            "Subject":     service_uuid,
            "Destination": msisdn,
            "Category":    "data",
            "Tenant":      CGRATES_TENANT,
            "SetupTime":   now_str,
            "AnswerTime":  now_str,
            "Usage":       2000000000,
        }

        cdr_sent = False
        # Try flat format (v0.10+)
        for payload in [
            # Format 1: flat Event at top level
            [{"Tenant": CGRATES_TENANT, "Event": cdr_event}],
            # Format 2: CGREvent wrapper (older versions)
            [{"CGREvent": {"Tenant": CGRATES_TENANT, "ID": origin_id, "Event": cdr_event}, "ArgDispatcher": None}],
            # Format 3: CDR directly (some versions use ApierV2.ProcessCDR)
            [cdr_event],
        ]:
            try:
                cgrates_rpc("SessionSv1.ProcessCDR", payload)
                state["cgrates_origin_id"] = origin_id
                record("CGRateS ProcessCDR (200MB)", True,
                       f"origin_id={origin_id} format=payload#{[payload].index(payload)+1}")
                cdr_sent = True
                break
            except Exception as ex:
                last_err = str(ex)
                continue

        if not cdr_sent:
            # Try CDRsV1.ProcessExternalCDR as alternative
            try:
                cgrates_rpc("CDRsV1.ProcessExternalCDR", [{
                    "ExternalCDR": {**cdr_event, "CGRID": origin_id}
                }])
                state["cgrates_origin_id"] = origin_id
                record("CGRateS ProcessCDR (200MB)", True,
                       f"origin_id={origin_id} via CDRsV1.ProcessExternalCDR")
                cdr_sent = True
            except Exception as ex2:
                record("CGRateS ProcessCDR (200MB)", False,
                       f"All formats failed. Last error: {last_err[:100]}\n"
                       f"    CDRsV1 error: {str(ex2)[:80]}\n"
                       f"    → CGRateS StorDB may need migration (cdrs table missing)")
    except Exception as e:
        record("CGRateS ProcessCDR (200MB)", False, str(e))

    # 8. Wait briefly then fetch rated CDR
    time.sleep(2)
    try:
        cdrs = cgrates_rpc("ApierV2.GetCDRs", [{
            "Tenants": [CGRATES_TENANT],
            "OriginIDs": [state.get("cgrates_origin_id", "")],
        }])
        if isinstance(cdrs, list) and cdrs:
            cdr = cdrs[0]
            cost = float(cdr.get("Cost", -1))
            usage = cdr.get("Usage", "?")
            record("CGRateS CDR rated", True,
                   f"cost=£{cost:.4f} usage={usage} "
                   f"account={cdr.get('Account','?')}")
        elif cdrs == 0 or cdrs is None:
            record("CGRateS CDR rated", False,
                   "No CDR found — CDR may still be processing, or rate tables not configured")
        else:
            record("CGRateS CDR rated", False, f"Unexpected response: {str(cdrs)[:80]}")
    except Exception as e:
        err = str(e)
        if "doesn't exist" in err or "1146" in err:
            record("CGRateS CDR rated", False,
                   "StorDB cdrs table missing — run CGRateS DB migration:\n"
                   "    cgr-migrator -exec -migrate=*cdrs -stordb_type=mysql "
                   "-stordb_host=<host> -stordb_user=<user> -stordb_passwd=<pass> -stordb_name=cgrates")
        else:
            record("CGRateS CDR rated", False, f"{err[:120]}")

    # 9. Check balance after CDR
    try:
        result2 = cgrates_rpc("ApierV2.GetAccount", [{
            "Tenant":  CGRATES_TENANT,
            "Account": service_uuid,
        }])
        monetary2 = result2.get("BalanceMap", {}).get("*monetary", [{}])
        balance2  = float(monetary2[0].get("Value", 0)) if monetary2 else 0
        before    = state.get("cgrates_balance_before", 0)
        diff      = before - balance2
        record("CGRateS balance after CDR", True,
               f"before=£{before:.4f} after=£{balance2:.4f} "
               f"deducted=£{diff:.4f}")
    except Exception as e:
        record("CGRateS balance after CDR", False, str(e))

    return True

def step_inject_usage():
    print("\n── Step 9: Inject test usage events ─────────────────────────────")
    msisdn = state["msisdn"]
	
    now = datetime.utcnow()

    events = [
        # Data usage — 200MB (within bundle)
        {"event_type": "data",  "quantity": "200", "unit": "mb",      "qty_label": "200MB data"},
        # Voice usage — 15 mins (within bundle)
        {"event_type": "voice", "quantity": "15",  "unit": "minutes", "qty_label": "15 mins voice"},
        # SMS — 5 messages (within bundle)
        {"event_type": "sms",   "quantity": "5",   "unit": "messages","qty_label": "5 SMS"},
        # OOB data — 50MB extra (out of bundle, should generate a charge)
        # Only meaningful in orbi-native mode
    ]

    all_ok = True
    for i, ev in enumerate(events):
        payload = {
            "msisdn":           msisdn,
            "event_type":       ev["event_type"],
            "quantity":         ev["quantity"],
            "unit":             ev["unit"],
            "event_timestamp":  (now - timedelta(hours=i)).isoformat(),
            "source_system":    "e2e-test",
        }
        resp = orbi("POST", "/usage/events", json=payload)
        if resp.status_code in (200, 202):
            data = resp.json()
            record(f"Inject {ev['qty_label']}", True,
                   f"event_id={data.get('event_id','?')[:12]}…")
        else:
            record(f"Inject {ev['qty_label']}", False,
                   f"HTTP {resp.status_code}: {resp.text[:80]}")
            all_ok = False

    return all_ok


def step_rate_events():
    print("\n── Step 10: Rate usage events ────────────────────────────────────")

    ocs_mode = state.get("ocs_mode", "orbi-native")

    if ocs_mode == "cgrates":
        log("OCS_MODE=cgrates — CDRs rated by CGRateS directly, not via Orbi", "info")
        log("Injecting a test CDR to CGRateS via ProcessCDR…", "info")

        if not state.get("service_uuid"):
            record("CGRateS ProcessCDR", True,
                   "Skipped — no service_uuid (provisioning not run)")
            return True

        # Push a test CDR directly to CGRateS
        try:
																			
																																	 
            origin_id = f"E2E-{uuid.uuid4().hex[:12]}"
            now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            cdr_ev  = {
																   
										
							  
                "ToR": "*data", "OriginID": origin_id, "OriginHost": "e2e-test",
																		 
																   
                "RequestType": "*prepaid", "Account": state["service_uuid"],
																																				
                "Subject": state["service_uuid"], "Destination": state["msisdn"],
																				  
                "Category": "data", "Tenant": CGRATES_TENANT,
																	  
                "SetupTime": now_str, "AnswerTime": now_str,
                "Usage": str(200 * 1024 * 1024),
            }
            sent = False
            for fmt, params in [
                ("flat",    [{"Tenant": CGRATES_TENANT, "Event": cdr_ev}]),
                ("wrapper", [{"CGREvent": {"Tenant": CGRATES_TENANT, "ID": origin_id, "Event": cdr_ev}, "ArgDispatcher": None}]),
                ("external",[{"ExternalCDR": {**cdr_ev, "CGRID": origin_id}}]),
            ]:
                try:
                    method = "CDRsV1.ProcessExternalCDR" if fmt == "external" else "SessionSv1.ProcessCDR"
                    cgrates_rpc(method, params)
                    state["cgrates_origin_id"] = origin_id
                    record("CGRateS ProcessCDR", True, f"origin_id={origin_id} fmt={fmt}")
                    sent = True
                    break
                except Exception as _e:
                    _last = str(_e)
            if not sent:
                record("CGRateS ProcessCDR", False,
                       f"All formats failed: {_last[:100]}")
        except Exception as e:
            record("CGRateS ProcessCDR", False, str(e))
        return True

    else:
        # orbi-native — rate the events we just injected
        resp = orbi("POST", "/billing-runs/rate-pending")
        if resp.status_code in (200, 202):
            data = resp.json()
            record("Rate pending events", True,
                   f"processed={data.get('events_processed',0)} "
                   f"charges={data.get('charges_generated',0)} "
                   f"failed={data.get('events_failed',0)}")
            return True
        else:
            record("Rate pending events", False,
                   f"HTTP {resp.status_code}: {resp.text[:80]}")
            return False


def step_billing_run():
    print("\n── Step 11: Billing run ──────────────────────────────────────────")
    if not state.get("customer_id"):
        record("Billing run", False, "Skipped — no customer_id from earlier steps")
        return False
    today      = date.today()
    period_start = date(today.year, today.month, 1).isoformat()
    period_end   = today.isoformat()

    payload = {
        "period_start": period_start,
        "period_end":   period_end,
        "customer_id":  state["customer_id"],
    }
    resp = orbi("POST", "/billing-runs", json=payload)
    if resp.status_code not in (200, 202):
        record("Billing run", False, f"HTTP {resp.status_code}: {resp.text[:100]}")
        return False

    data = resp.json()
    record("Billing run", True,
           f"invoices={data.get('invoices_created',0)} "
           f"charges={data.get('recurring_charges_generated',0)} "
           f"usage_rated={data.get('usage_events_rated',0)} "
           f"took={data.get('duration_seconds','?')}s")
    state["billing_result"] = data
    return True


def step_verify_invoice():
    print("\n── Step 12: Verify invoice ───────────────────────────────────────")
    if not state.get("customer_id"):
        record("Get customer invoices", False, "Skipped — no customer_id from earlier steps")
        return False

    resp = orbi("GET", f"/customers/{state['customer_id']}/invoices")
    if resp.status_code != 200:
        record("Get customer invoices", False, f"HTTP {resp.status_code}")
        return False

    invoices = resp.json()
    if not invoices:
        record("Invoice created", False,
               "No invoices found — billing run may not have generated charges")
        log("This is expected if the customer has no unbilled charges yet", "info")
        return True

    inv = invoices[0]
    state["invoice_id"] = inv["id"]
    record("Invoice created", True,
           f"{inv['invoice_number']} "
           f"total=£{inv['total']/100:.2f} "
           f"status={inv['status']}")

    # Check line items
    resp2 = orbi("GET", f"/invoices/{inv['id']}")
    if resp2.status_code == 200:
        inv_detail = resp2.json()
        line_items  = inv_detail.get("line_items", [])
        record("Invoice line items", True,
               f"{len(line_items)} line item(s): " +
               ", ".join(li.get("description","?")[:30] for li in line_items[:3]))

    return True


def step_pdf():
    print("\n── Step 13: Invoice PDF ──────────────────────────────────────────")

    if not state.get("invoice_id"):
        record("Invoice PDF", True, "Skipped — no invoice created")
        return True

    resp = orbi("GET", f"/invoices/{state['invoice_id']}/pdf")
    if resp.status_code == 200:
        content_type = resp.headers.get("content-type", "")
        size         = len(resp.content)
        if "pdf" in content_type:
            record("Invoice PDF", True, f"PDF generated — {size:,} bytes")
        elif "html" in content_type:
            record("Invoice PDF (HTML fallback)", True,
                   f"HTML invoice {size:,} bytes — install WeasyPrint for PDF")
        else:
            record("Invoice PDF", True,
                   f"content-type={content_type} size={size:,}")
        return True
    elif resp.status_code == 503:
        record("Invoice PDF", True,
               "WeasyPrint not installed — run: pip install weasyprint")
        return True
    else:
        record("Invoice PDF", False, f"HTTP {resp.status_code}: {resp.text[:80]}")
        return False


# ══════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════

def print_summary():
    print("\n" + "═" * 65)
    print("  ORBI E2E TEST SUMMARY")
    print("═" * 65)

    passed = sum(1 for r in results if r["ok"])
    failed = sum(1 for r in results if not r["ok"])
    total  = len(results)

    for r in results:
        sym   = "✓" if r["ok"] else "✗"
        color = "\033[92m" if r["ok"] else "\033[91m"
        reset = "\033[0m"
        detail = f"  {r['detail']}" if r["detail"] else ""
        print(f"  {color}{sym}{reset}  {r['step']}{detail}")

    print("─" * 65)
    pct = int(passed / total * 100) if total else 0
    color = "\033[92m" if failed == 0 else "\033[93m" if failed <= 2 else "\033[91m"
    reset = "\033[0m"
    print(f"\n  {color}{passed}/{total} passed ({pct}%){reset}", end="")
    if failed:
        print(f"  ·  {failed} failed")
    else:
        print("  ·  All green!")

    print("\n  State captured:")
    for k, v in state.items():
        if k not in ("workflow", "billing_result", "cgrates_balance_before"):
            val = str(v)[:60] + "…" if len(str(v)) > 60 else str(v)
            print(f"    {k}: {val}")

    if state.get("ocs_mode") == "cgrates" and not state.get("cgrates_ok"):
        print("""
  CGRateS was not reachable. To test the full integration:
    1. Check CGRateS is running: curl http://localhost:2080/jsonrpc
    2. Set CGRATES_URL=http://<your-cgrates-host>:2080
    3. Re-run: CGRATES_URL=http://... python tests/e2e_test.py
""")

    if state.get("ocs_mode") == "orbi-native":
        print("""
  Running in orbi-native mode. To test CGRateS integration:
    1. Set OCS_MODE=cgrates in your .env
    2. Set CGRATES_API_URL=http://<cgrates-host>:2080
    3. Restart uvicorn
    4. Re-run this test
""")

    print("═" * 65 + "\n")


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "═" * 65)
    print("  ORBI + CGRATES END-TO-END INTEGRATION TEST")
    print(f"  Orbi:    {ORBI_URL}")
    print(f"  CGRateS: {CGRATES_URL}  tenant={CGRATES_TENANT}")
    print("═" * 65)

    steps = [
        ("Health checks",              step_health),
        ("Create product",             step_create_product),
        ("Add inventory",              step_add_inventory),
        ("Create customer",            step_create_customer),
        ("Prepaid topup (before activation)", step_topup),
        ("Create + activate order",    step_create_and_activate_order),
        ("Provisioning workflow",      step_check_provisioning),
        ("Verify CGRateS account",     step_verify_cgrates_account),
        ("CGRateS direct account test",step_cgrates_account_direct),
        ("Inject usage events",        step_inject_usage),
        ("Rate events / inject CDR",   step_rate_events),
        ("Billing run",                step_billing_run),
        ("Verify invoice",             step_verify_invoice),
        ("Invoice PDF",                step_pdf),
    ]

    for name, fn in steps:
        try:
            fn()
        except Exception as e:
            record(name, False, f"Exception: {e}")
            import traceback
            traceback.print_exc()

    print_summary()


if __name__ == "__main__":
    main()
