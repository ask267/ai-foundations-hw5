"""Campus Customs MCP — shared tools for every agent in Homework 5.

All tools read from the working copy data/campus_customs_new.db (never the
original data/campus_customs.db). Values come straight from the database;
nothing is invented. Set CAMPUS_CUSTOMS_DB to point at another copy (tests).

Read tools:   get_shop_date, list_tickets, get_ticket, check_stock,
              get_pricing, quote_discount, get_rent_due, get_invoice,
              list_vendors, get_cash_balance, list_payments,
              list_payment_requests
Agent writes: update_ticket, adjust_inventory,
              prepare_payment, prepare_purchase   (prepare only - no cash moves)
Human-only:   approve_payment_request, reject_payment_request
              (called by the backend's approve route after a person clicks
              Approve; no agent role is given these tools)

Agents never move money. They file a pending row in payment_requests; cash,
payments and invoices change only when a human approves that request.
Every write checks the database first (amounts must match the bill, cash
can't go negative, stock can't go negative, no double payments) and runs in a
single transaction.

Run (stdio):  python server.py
"""

from __future__ import annotations

import calendar
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from fastmcp import FastMCP

HERE = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("CAMPUS_CUSTOMS_DB", HERE.parent / "data" / "campus_customs_new.db"))

TICKET_STATUSES = ("open", "in_progress", "waiting", "resolved", "escalated")
MAX_ROWS = 50  # cap on rows any list tool returns
OWNER_DISCOUNT_PCT = 15.0  # discounts above this need the human owner
RENT_PAY_WINDOW_DAYS = 10  # rent can't be paid earlier than this before next_due

mcp = FastMCP("campus-customs")


# Pending money requests prepared by agents and decided by a human. Created on
# first use, so a freshly reset copy of the original database works too.
PAYMENT_REQUESTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS payment_requests (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,              -- invoice | rent | purchase
    ref_id INTEGER,                  -- invoices.id / leases.id (NULL for purchase)
    vendor_id INTEGER,               -- purchase only
    sku TEXT, size TEXT, qty INTEGER,-- purchase only
    amount REAL NOT NULL,
    account TEXT NOT NULL,
    ticket_id INTEGER,
    reason TEXT NOT NULL,
    resolves_ticket INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,            -- pending | approved | rejected
    prepared_by TEXT NOT NULL,
    prepared_at TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT,
    decision_note TEXT,
    payment_id INTEGER
)
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """One connection per tool call: commits on success, rolls back on error, always closes."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute(PAYMENT_REQUESTS_SCHEMA)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    return row["date_today"] if row else None


def _days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _add_month(iso: str) -> str:
    d = date.fromisoformat(iso)
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day).isoformat()


def _add_days(iso: str, days: int) -> str:
    return date.fromordinal(date.fromisoformat(iso).toordinal() + days).isoformat()


# --------------------------------------------------------------------- read


@mcp.tool
def get_shop_date() -> dict:
    """The shop's official 'today' and desk notes. All due dates, overdue
    checks and ETAs are measured from this date, not the real clock.
    Reads: desk."""
    with _connect() as conn:
        row = conn.execute("SELECT date_today, notes FROM desk LIMIT 1").fetchone()
    if row is None:
        return {"found": False, "error": "desk table is empty"}
    return {"found": True, "date_today": row["date_today"], "notes": row["notes"]}


@mcp.tool
def list_tickets(status: str = "open") -> dict:
    """List tickets with the given status ('open', 'in_progress', 'waiting',
    'resolved', 'escalated', or 'all'), oldest first. Reads: tickets."""
    with _connect() as conn:
        if status == "all":
            rows = conn.execute(
                "SELECT * FROM tickets ORDER BY created_at LIMIT ?", (MAX_ROWS,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE status = ? ORDER BY created_at LIMIT ?",
                (status, MAX_ROWS),
            ).fetchall()
    return {"status_filter": status, "count": len(rows), "tickets": [dict(r) for r in rows]}


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """One ticket plus the rows it links to: inventory + pricing (sku/size),
    lease (lease_id), and invoice + vendor (invoice_id).
    Reads: tickets, inventory, pricing, leases, invoices, vendors."""
    with _connect() as conn:
        t = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"found": False, "ticket_id": ticket_id, "error": "Ticket not found"}
        linked: dict = {}
        if t["sku"]:
            inv = conn.execute(
                "SELECT size, qty, location FROM inventory WHERE sku = ? ORDER BY size",
                (t["sku"],),
            ).fetchall()
            linked["inventory"] = [dict(r) for r in inv]
            price = conn.execute(
                "SELECT list_price FROM pricing WHERE sku = ?", (t["sku"],)
            ).fetchone()
            linked["list_price"] = price["list_price"] if price else None
        if t["lease_id"] is not None:
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (t["lease_id"],)).fetchone()
            linked["lease"] = dict(lease) if lease else None
        if t["invoice_id"] is not None:
            inv = conn.execute(
                "SELECT i.*, v.name AS vendor_name, v.lead_days AS vendor_lead_days "
                "FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
                (t["invoice_id"],),
            ).fetchone()
            linked["invoice"] = dict(inv) if inv else None
    return {"found": True, "ticket": dict(t), "linked": linked}


@mcp.tool
def check_stock(sku: str, size: str, qty_needed: int = 1) -> dict:
    """Check on-hand stock for one SKU and size, and whether an order of
    qty_needed can be filled. Also lists every other size of the same SKU so
    the agent can offer a swap. Reads: inventory."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ?",
            (sku,),
        ).fetchall()
    if not rows:
        return {"found": False, "sku": sku, "error": "SKU not in inventory"}

    match = next((r for r in rows if r["size"] == size), None)
    if match is None:
        return {
            "found": False,
            "sku": sku,
            "size": size,
            "error": "Size not stocked for this SKU",
            "sizes_available": [dict(r) for r in rows],
        }

    on_hand = match["qty"]
    return {
        "found": True,
        "sku": sku,
        "name": match["name"],
        "size": size,
        "location": match["location"],
        "qty_on_hand": on_hand,
        "qty_needed": qty_needed,
        "can_fill": on_hand >= qty_needed,
        "shortfall": max(qty_needed - on_hand, 0),
        "other_sizes": [
            {"size": r["size"], "qty": r["qty"]} for r in rows if r["size"] != size
        ],
    }


@mcp.tool
def get_pricing(sku: str, qty: int = 1) -> dict:
    """Return unit cost and list price for a SKU, with totals for qty units
    at list price and at cost (the break-even floor). Use before quoting or
    approving any discount. INTERNAL: unit cost is never shared with
    customers. Reads: pricing."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?",
            (sku,),
        ).fetchone()
    if row is None:
        return {"found": False, "sku": sku, "error": "SKU not in pricing"}

    unit_cost, list_price = row["unit_cost"], row["list_price"]
    return {
        "found": True,
        "sku": sku,
        "qty": qty,
        "unit_cost": unit_cost,
        "list_price": list_price,
        "unit_margin": round(list_price - unit_cost, 2),
        "total_at_list": round(list_price * qty, 2),
        "total_at_cost": round(unit_cost * qty, 2),
        "max_discount_pct_before_loss": round((list_price - unit_cost) / list_price * 100, 1),
    }


@mcp.tool
def quote_discount(sku: str, qty: int, discount_pct: float) -> dict:
    """Price a proposed discount without changing anything: discounted unit
    price, order total, margin left, whether it sells below cost, whether it
    needs the human owner's approval (over 15%), and whether stock covers qty.
    Reads: pricing, inventory."""
    if qty <= 0 or not 0 <= discount_pct < 100:
        return {"ok": False, "error": "qty must be > 0 and discount_pct between 0 and 100"}
    with _connect() as conn:
        p = conn.execute(
            "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()
        stock = conn.execute(
            "SELECT COALESCE(SUM(qty), 0) AS total FROM inventory WHERE sku = ?", (sku,)
        ).fetchone()["total"]
    if p is None:
        return {"ok": False, "sku": sku, "error": "SKU not in pricing"}
    unit_price = round(p["list_price"] * (1 - discount_pct / 100), 2)
    return {
        "ok": True,
        "sku": sku,
        "qty": qty,
        "discount_pct": discount_pct,
        "list_price": p["list_price"],
        "unit_cost": p["unit_cost"],
        "discounted_unit_price": unit_price,
        "order_total": round(unit_price * qty, 2),
        "order_margin": round((unit_price - p["unit_cost"]) * qty, 2),
        "below_cost": unit_price < p["unit_cost"],
        "needs_owner_approval": discount_pct > OWNER_DISCOUNT_PCT,
        "total_stock_all_sizes": stock,
    }


@mcp.tool
def get_rent_due(lease_id: int) -> dict:
    """Look up a lease's rent amount, landlord, and next due date, plus the
    shop's 'today' date and checking balance, so a rent notice can be
    verified before anything is paid. Reads: leases, desk, cash_accounts."""
    with _connect() as conn:
        lease = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes "
            "FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
        today = _today(conn)
        accounts = conn.execute(
            "SELECT name, balance, date FROM cash_accounts"
        ).fetchall()
    if lease is None:
        return {"found": False, "lease_id": lease_id, "error": "Lease not found"}

    return {
        "found": True,
        "lease": dict(lease),
        "desk_date_today": today,
        "days_until_due": _days_between(today, lease["next_due"]) if today else None,
        "cash_accounts": [dict(a) for a in accounts],
    }


@mcp.tool
def get_invoice(invoice_id: int) -> dict:
    """One vendor invoice with its vendor (name, specialty, lead_days), days
    overdue versus the shop date, and the restock ETA if it were paid today
    (shop date + vendor lead_days). Reads: invoices, vendors, desk."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT i.id, i.amount, i.due_date, i.status, i.description, "
            "v.id AS vendor_id, v.name AS vendor_name, v.specialty, v.lead_days "
            "FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
            (invoice_id,),
        ).fetchone()
        today = _today(conn)
    if row is None:
        return {"found": False, "invoice_id": invoice_id, "error": "Invoice not found"}
    overdue = _days_between(row["due_date"], today) if today else None
    return {
        "found": True,
        "invoice": dict(row),
        "desk_date_today": today,
        "days_overdue": max(overdue, 0) if overdue is not None else None,
        "eta_if_paid_today": _add_days(today, row["lead_days"]) if today else None,
    }


@mcp.tool
def list_vendors() -> dict:
    """All vendors with specialty and lead time in days. Reads: vendors."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM vendors ORDER BY id LIMIT ?", (MAX_ROWS,)).fetchall()
    return {"count": len(rows), "vendors": [dict(r) for r in rows]}


@mcp.tool
def get_cash_balance() -> dict:
    """Every cash account balance plus the total owed on open invoices and
    the shop date, so a payment can be checked against available cash.
    Reads: cash_accounts, invoices, desk."""
    with _connect() as conn:
        accounts = conn.execute("SELECT name, balance, date FROM cash_accounts").fetchall()
        owed = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS n "
            "FROM invoices WHERE status = 'open'"
        ).fetchone()
        today = _today(conn)
    return {
        "desk_date_today": today,
        "accounts": [dict(a) for a in accounts],
        "open_invoices_count": owed["n"],
        "open_invoices_total": owed["total"],
    }


@mcp.tool
def list_payments(limit: int = 20) -> dict:
    """Most recent payments already made (newest first), to avoid paying the
    same bill twice. Reads: payments."""
    limit = max(1, min(limit, MAX_ROWS))
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM payments ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"count": len(rows), "payments": [dict(r) for r in rows]}


# -------------------------------------------------------------------- write


@mcp.tool
def update_ticket(ticket_id: int, status: str, note: str, author: str = "agent") -> dict:
    """Set a ticket's status ('open', 'in_progress', 'waiting', 'resolved',
    'escalated') and append a dated note signed by author. Earlier notes are
    kept. Writes: tickets."""
    if status not in TICKET_STATUSES:
        return {"ok": False, "error": f"status must be one of {TICKET_STATUSES}"}
    note = " ".join(note.split())[:500]
    if not note:
        return {"ok": False, "error": "note is required"}
    with _connect() as conn:
        t = conn.execute("SELECT status, notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"ok": False, "ticket_id": ticket_id, "error": "Ticket not found"}
        line = f"[{_today(conn)} {author}] {note}"
        notes = f"{t['notes']}\n{line}" if t["notes"] else line
        conn.execute(
            "UPDATE tickets SET status = ?, notes = ? WHERE id = ?", (status, notes, ticket_id)
        )
    return {
        "ok": True,
        "ticket_id": ticket_id,
        "old_status": t["status"],
        "new_status": status,
        "note_added": line,
    }


def _check_bill(conn: sqlite3.Connection, kind: str, ref_id: int, amount: float) -> str | None:
    """Why an invoice/rent payment can't be made right now (None = it can)."""
    today = _today(conn)
    if kind == "invoice":
        bill = conn.execute("SELECT amount, status FROM invoices WHERE id = ?", (ref_id,)).fetchone()
        if bill is None:
            return f"Invoice {ref_id} not found"
        if bill["status"] != "open":
            return f"Invoice {ref_id} is '{bill['status']}', not open"
        expected = bill["amount"]
    elif kind == "rent":
        lease = conn.execute(
            "SELECT monthly_rent, next_due FROM leases WHERE id = ?", (ref_id,)
        ).fetchone()
        if lease is None:
            return f"Lease {ref_id} not found"
        days_left = _days_between(today, lease["next_due"])
        if days_left > RENT_PAY_WINDOW_DAYS:
            return (
                f"Rent for lease {ref_id} isn't due until {lease['next_due']} ({days_left} days); "
                f"it may be paid at most {RENT_PAY_WINDOW_DAYS} days early"
            )
        expected = lease["monthly_rent"]
    else:
        return "kind must be 'invoice' or 'rent'"
    if round(amount, 2) != round(expected, 2):
        return f"Amount {amount:.2f} does not match the bill ({expected:.2f})"
    dup = conn.execute(
        "SELECT id FROM payments WHERE kind = ? AND ref_id = ? AND paid_at = ?", (kind, ref_id, today)
    ).fetchone()
    if dup is not None:
        return f"Already paid today (payment {dup['id']})"
    return None


def _check_cash(conn: sqlite3.Connection, account: str, amount: float, exclude_request: int | None = None) -> str | None:
    acct = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
    if acct is None:
        return f"Cash account '{account}' not found"
    pending = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM payment_requests "
        "WHERE status = 'pending' AND account = ? AND id != ?",
        (account, exclude_request or -1),
    ).fetchone()["total"]
    if acct["balance"] < amount + pending:
        return (
            f"Insufficient funds: {account} has {acct['balance']:.2f}, other pending requests "
            f"total {pending:.2f}, this needs {amount:.2f}"
        )
    return None


def _insert_request(conn: sqlite3.Connection, **row) -> dict:
    row.setdefault("account", "checking")
    row.update(status="pending", prepared_at=_stamp())
    cols = ", ".join(row)
    cur = conn.execute(
        f"INSERT INTO payment_requests ({cols}) VALUES ({', '.join('?' for _ in row)})",
        tuple(row.values()),
    )
    req = conn.execute("SELECT * FROM payment_requests WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(req)


@mcp.tool
def prepare_payment(
    kind: str,
    ref_id: int,
    amount: float,
    ticket_id: int,
    reason: str,
    resolves_ticket: bool = False,
    account: str = "checking",
    prepared_by: str = "agent",
) -> dict:
    """Prepare (do NOT make) a payment of a vendor invoice (kind='invoice',
    ref_id=invoices.id) or rent (kind='rent', ref_id=leases.id). Files a
    PENDING request that a human must approve before any cash moves. The
    amount must equal the bill exactly, the invoice must be open, rent may be
    at most 10 days early, and cash must cover it plus other pending requests.
    Set resolves_ticket=True if approving this payment finishes the ticket.
    Writes: payment_requests."""
    reason = " ".join(reason.split())[:300]
    if not reason:
        return {"ok": False, "error": "reason is required"}
    with _connect() as conn:
        problem = _check_bill(conn, kind, ref_id, amount)
        if problem is None:
            dup = conn.execute(
                "SELECT id FROM payment_requests WHERE kind = ? AND ref_id = ? AND status = 'pending'",
                (kind, ref_id),
            ).fetchone()
            if dup is not None:
                problem = f"A pending request already exists for {kind} {ref_id} (request {dup['id']})"
        if problem is None:
            problem = _check_cash(conn, account, amount)
        if problem:
            return {"ok": False, "error": problem}
        req = _insert_request(
            conn, kind=kind, ref_id=ref_id, amount=amount, account=account, ticket_id=ticket_id,
            reason=reason, resolves_ticket=int(resolves_ticket), prepared_by=prepared_by[:50],
        )
    return {"ok": True, "status": "pending_human_approval", "request": req}


@mcp.tool
def prepare_purchase(
    vendor_id: int,
    sku: str,
    size: str,
    qty: int,
    ticket_id: int,
    reason: str,
    resolves_ticket: bool = False,
    account: str = "checking",
    prepared_by: str = "agent",
) -> dict:
    """Prepare (do NOT make) a restock purchase order from a vendor. The
    amount is computed from the database: qty x pricing.unit_cost. Files a
    PENDING request a human must approve; on approval the shop pays and the
    stock is expected after the vendor's lead_days. Writes: payment_requests."""
    reason = " ".join(reason.split())[:300]
    if qty <= 0 or not reason:
        return {"ok": False, "error": "qty must be > 0 and reason is required"}
    with _connect() as conn:
        vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        item = conn.execute(
            "SELECT i.name, p.unit_cost FROM inventory i JOIN pricing p ON p.sku = i.sku "
            "WHERE i.sku = ? AND i.size = ?",
            (sku, size),
        ).fetchone()
        if vendor is None:
            return {"ok": False, "error": f"Vendor {vendor_id} not found"}
        if item is None:
            return {"ok": False, "error": f"{sku} size {size} not in inventory/pricing"}
        amount = round(item["unit_cost"] * qty, 2)
        problem = _check_cash(conn, account, amount)
        if problem:
            return {"ok": False, "error": problem}
        req = _insert_request(
            conn, kind="purchase", vendor_id=vendor_id, sku=sku, size=size, qty=qty,
            amount=amount, account=account, ticket_id=ticket_id, reason=reason,
            resolves_ticket=int(resolves_ticket), prepared_by=prepared_by[:50],
        )
        today = _today(conn)
    return {
        "ok": True,
        "status": "pending_human_approval",
        "request": req,
        "vendor": dict(vendor),
        "unit_cost": item["unit_cost"],
        "eta_if_approved_today": _add_days(today, vendor["lead_days"]) if today else None,
    }


@mcp.tool
def list_payment_requests(status: str = "pending") -> dict:
    """Payment/purchase requests by status ('pending', 'approved', 'rejected',
    or 'all'), newest first. Reads: payment_requests."""
    with _connect() as conn:
        if status == "all":
            rows = conn.execute(
                "SELECT * FROM payment_requests ORDER BY id DESC LIMIT ?", (MAX_ROWS,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM payment_requests WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, MAX_ROWS),
            ).fetchall()
    return {"status_filter": status, "count": len(rows), "requests": [dict(r) for r in rows]}


def _ticket_note(conn: sqlite3.Connection, ticket_id: int | None, text: str, status: str | None = None) -> None:
    if ticket_id is None:
        return
    t = conn.execute("SELECT notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if t is None:
        return
    line = f"[{_today(conn)} owner] {text}"
    notes = f"{t['notes']}\n{line}" if t["notes"] else line
    if status:
        conn.execute("UPDATE tickets SET notes = ?, status = ? WHERE id = ?", (notes, status, ticket_id))
    else:
        conn.execute("UPDATE tickets SET notes = ? WHERE id = ?", (notes, ticket_id))


@mcp.tool
def approve_payment_request(request_id: int, approved_by: str) -> dict:
    """HUMAN ONLY - the backend calls this after a person clicks Approve.
    Re-checks the request against the database, then in one transaction:
    inserts the payments row, lowers the cash balance, and marks the invoice
    paid / moves the lease's next_due a month / records the purchase invoice.
    Adds a note to the linked ticket (and resolves it if the request said so).
    Writes: payment_requests, payments, cash_accounts, invoices / leases, tickets."""
    approved_by = " ".join(approved_by.split())[:60]
    if not approved_by:
        return {"ok": False, "error": "approved_by is required"}
    with _connect() as conn:
        req = conn.execute("SELECT * FROM payment_requests WHERE id = ?", (request_id,)).fetchone()
        if req is None:
            return {"ok": False, "error": f"Request {request_id} not found"}
        if req["status"] != "pending":
            return {"ok": False, "error": f"Request {request_id} is already {req['status']}"}
        kind, amount, account = req["kind"], req["amount"], req["account"]
        today = _today(conn)

        problem = None if kind == "purchase" else _check_bill(conn, kind, req["ref_id"], amount)
        if problem is None:
            problem = _check_cash(conn, account, amount, exclude_request=request_id)
        if problem:
            return {"ok": False, "error": problem}

        effect: dict
        ref_id = req["ref_id"]
        if kind == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ref_id,))
            effect = {"invoice_id": ref_id, "invoice_status": "paid"}
        elif kind == "rent":
            next_due = conn.execute("SELECT next_due FROM leases WHERE id = ?", (ref_id,)).fetchone()["next_due"]
            next_due = _add_month(next_due)
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (next_due, ref_id))
            effect = {"lease_id": ref_id, "lease_next_due": next_due}
        else:  # purchase: record the vendor bill as paid
            lead = conn.execute("SELECT lead_days FROM vendors WHERE id = ?", (req["vendor_id"],)).fetchone()["lead_days"]
            cur = conn.execute(
                "INSERT INTO invoices (vendor_id, amount, due_date, status, description) "
                "VALUES (?, ?, ?, 'paid', ?)",
                (req["vendor_id"], amount, today,
                 f"Purchase order {req['qty']} x {req['sku']} {req['size']} (request {request_id})"),
            )
            ref_id = cur.lastrowid
            effect = {"invoice_id": ref_id, "invoice_status": "paid",
                      "stock_eta": _add_days(today, lead)}

        balance = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()["balance"]
        new_balance = round(balance - amount, 2)
        pay = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
            (kind, ref_id, amount, account, today, f"{approved_by} (human)"),
        )
        conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (new_balance, today, account))
        conn.execute(
            "UPDATE payment_requests SET status = 'approved', decided_by = ?, decided_at = ?, payment_id = ? WHERE id = ?",
            (approved_by, _stamp(), pay.lastrowid, request_id),
        )
        _ticket_note(
            conn, req["ticket_id"],
            f"Approved request {request_id}: paid {kind} ${amount:,.2f} (payment {pay.lastrowid}).",
            "resolved" if req["resolves_ticket"] else None,
        )
    return {
        "ok": True,
        "request_id": request_id,
        "payment_id": pay.lastrowid,
        "kind": kind,
        "amount": amount,
        "account": account,
        "paid_at": today,
        "approved_by": f"{approved_by} (human)",
        "balance_after": new_balance,
        "ticket_resolved": bool(req["resolves_ticket"]),
        **effect,
    }


@mcp.tool
def reject_payment_request(request_id: int, rejected_by: str, note: str = "") -> dict:
    """HUMAN ONLY - mark a pending request rejected. No money moves.
    Writes: payment_requests, tickets (note)."""
    rejected_by = " ".join(rejected_by.split())[:60]
    if not rejected_by:
        return {"ok": False, "error": "rejected_by is required"}
    with _connect() as conn:
        req = conn.execute("SELECT * FROM payment_requests WHERE id = ?", (request_id,)).fetchone()
        if req is None:
            return {"ok": False, "error": f"Request {request_id} not found"}
        if req["status"] != "pending":
            return {"ok": False, "error": f"Request {request_id} is already {req['status']}"}
        note = " ".join(note.split())[:300]
        conn.execute(
            "UPDATE payment_requests SET status = 'rejected', decided_by = ?, decided_at = ?, decision_note = ? WHERE id = ?",
            (rejected_by, _stamp(), note or None, request_id),
        )
        _ticket_note(conn, req["ticket_id"], f"Rejected request {request_id}" + (f": {note}" if note else "."))
    return {"ok": True, "request_id": request_id, "status": "rejected"}


@mcp.tool
def adjust_inventory(sku: str, size: str, delta: int, reason: str) -> dict:
    """Change on-hand stock for one SKU/size by delta (negative = items leave
    the shop for an order; positive = restock received). Stock can't go below
    zero and a reason is required. Writes: inventory."""
    if delta == 0 or not reason.strip():
        return {"ok": False, "error": "delta must be non-zero and reason is required"}
    with _connect() as conn:
        row = conn.execute(
            "SELECT qty FROM inventory WHERE sku = ? AND size = ?", (sku, size)
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"{sku} size {size} not in inventory"}
        new_qty = row["qty"] + delta
        if new_qty < 0:
            return {
                "ok": False,
                "error": f"Only {row['qty']} on hand; cannot remove {-delta}",
            }
        conn.execute(
            "UPDATE inventory SET qty = ? WHERE sku = ? AND size = ?", (new_qty, sku, size)
        )
    return {
        "ok": True,
        "sku": sku,
        "size": size,
        "old_qty": row["qty"],
        "new_qty": new_qty,
        "reason": " ".join(reason.split())[:200],
    }


if __name__ == "__main__":
    mcp.run(show_banner=False)
