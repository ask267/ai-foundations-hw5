# Campus Customs — Harness

How the Campus Customs back office works: a SQLite database, one MCP server that is the only way to read or change it, five PydanticAI agents that work the ticket queue, a FastAPI backend, and a React dashboard where a human watches the agents and approves every dollar.

```
 React board (frontend/, :5173)
        │  fetch  /api/...
        ▼
 FastAPI backend (backend/main.py, :8000) ──── POST /api/tickets/{id}/run ───► Agent team (backend/team.py)
        │  MCP client (admin)                                                  Boss ⇄ Inventory ⇄ Accounting ⇄ Facilities ⇄ CustomerService
        │  approve / reject / read                                                    │  MCP client (per run, filtered per role)
        ▼                                                                             ▼
                     campus-customs MCP server (mcp_server/server.py, FastMCP, stdio)
                                         │  sqlite3
                                         ▼
                               data/campus_customs_new.db  (working copy; reset from campus_customs.db)
        every agent step, tool call, delegation and human approval ──► output/audit_trail.json (append-only)
```

**Contents:** Data files · Tables (+ `payment_requests`) · How the tables link · The three tickets · MCP server and tools · The five agents and their loop · Audit trail · Safety (guardrails + token limits) · Backend API routes · Frontend dashboard · Problem 9 full-run results

**Quick start**
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt   # once, in hw5/
cp .env.example .env                                                                       # add PORTKEY_API_KEY
cd backend && uvicorn main:app --reload --port 8000                                        # API + agents (+ MCP via .mcp.json)
cd frontend && npm install && npm run dev                                                  # board at http://localhost:5173
```
Full step-by-step instructions are in `README.md`.

## Data files

| File | Purpose |
|---|---|
| `data/campus_customs.db` | Original seed database. **Read-only — never modified.** |
| `data/campus_customs_new.db` | Working copy (starts as a byte-for-byte copy of the original). The MCP server reads and writes only this file. On first use it adds one table, `payment_requests`. |

To reset the working copy, click **Reset desk** on the board (`POST /api/reset`), or copy the original over it again:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

## Tables

### `desk`
Fields: `date_today` (TEXT), `notes` (TEXT)

Why it matters: sets the shop's "today" (2026-08-31), so agents judge due dates and overdue items against this date, not the real clock.

### `inventory`
Fields: `sku` (TEXT), `name` (TEXT), `size` (TEXT), `qty` (INTEGER), `location` (TEXT). Primary key is (`sku`, `size`).

Why it matters: the stock count per SKU and size, so agents can check whether an order can be filled and where the item is shelved.

### `pricing`
Fields: `sku` (TEXT, PK), `unit_cost` (REAL), `list_price` (REAL)

Why it matters: gives cost and list price, so agents can quote prices and work out how much discount the margin can take.

### `vendors`
Fields: `id` (INTEGER, PK), `name` (TEXT), `specialty` (TEXT), `lead_days` (INTEGER)

Why it matters: shows who supplies or reprints what and how long it takes, so agents can promise realistic restock dates.

### `leases`
Fields: `id` (INTEGER, PK), `space_name` (TEXT), `landlord` (TEXT), `monthly_rent` (REAL), `next_due` (TEXT), `notes` (TEXT)

Why it matters: the shop's rent obligation (amount, landlord, due date), so agents can verify a rent notice before any money moves.

### `cash_accounts`
Fields: `name` (TEXT, PK), `balance` (REAL), `date` (TEXT)

Why it matters: the cash available to pay bills. Agents must check it before approving payments so the account is never overdrawn.

### `payments`
Fields: `id` (INTEGER, PK), `kind` (TEXT), `ref_id` (INTEGER), `amount` (REAL), `account` (TEXT), `paid_at` (TEXT), `approved_by` (TEXT)

Why it matters: the audit log of money paid out (empty at start). Every payment is recorded here with the human who approved it (agents only prepare payments; see Problem 7).

### `invoices`
Fields: `id` (INTEGER, PK), `vendor_id` (INTEGER, FK → `vendors.id`), `amount` (REAL), `due_date` (TEXT), `status` (TEXT), `description` (TEXT)

Why it matters: bills the shop owes vendors, so agents can see what is unpaid or overdue and tie a payment back to its bill.

### `tickets`
Fields: `id` (INTEGER, PK), `type` (TEXT), `requester` (TEXT), `subject` (TEXT), `sku` (TEXT), `size` (TEXT), `qty` (INTEGER), `lease_id` (INTEGER, FK → `leases.id`), `invoice_id` (INTEGER, FK → `invoices.id`), `status` (TEXT), `notes` (TEXT), `created_at` (TEXT)

Why it matters: the agents' work queue. Each ticket is a request to resolve, and its `sku`/`size`, `lease_id`, or `invoice_id` points to the data needed to resolve it.

### `payment_requests` (added by the MCP server in Problem 7)
Fields: `id` (INTEGER, PK), `kind` (invoice / rent / purchase), `ref_id`, `vendor_id`, `sku`, `size`, `qty`, `amount`, `account`, `ticket_id`, `reason`, `resolves_ticket`, `status` (pending / approved / rejected), `prepared_by`, `prepared_at`, `decided_by`, `decided_at`, `decision_note`, `payment_id`

Why it matters: holds money the agents want to spend, kept apart from money actually spent. Accounting can only add `pending` rows here; a human turns one into a `payments` row by approving it.

## How the tables link

```
tickets.sku + tickets.size ──► inventory (sku, size)
tickets.sku ─────────────────► pricing.sku
tickets.lease_id ────────────► leases.id
tickets.invoice_id ──────────► invoices.id ──► vendors.id (invoices.vendor_id)
payments.ref_id ─────────────► invoices.id or leases.id (depending on payments.kind)
payments.account ────────────► cash_accounts.name
payment_requests.ticket_id ──► tickets.id
payment_requests.ref_id ─────► invoices.id or leases.id;  payment_requests.payment_id ──► payments.id
```

## The three open tickets (as of desk date 2026-08-31)

### Ticket 101 — `customer_order` from Tauhid Zaman
- Wants 1 × `CC-TEE-WHITE` (Classic Bulldog Tee) in size **S**.
- **inventory:** size S has `qty = 0` (Aisle B), so it can't be filled from stock. Sizes M, L, and XL are in stock (5, 3, and 2).
- **pricing:** unit cost $8.00, list price $28.00.
- **invoice 501:** $840.00 to vendor 1 for "Rush reprint CC-TEE-WHITE S". It was due 2026-08-28 and is still `open`, so it is **3 days overdue**.
- **vendor 1:** Bulldog Print Co (apparel reprint), lead time 5 days.
- What this means: the size S restock depends on a reprint bill that hasn't been paid yet. Even once it's paid, the 5-day lead time means the earliest delivery is about 2026-09-05.

### Ticket 102 — `rent_notice` from Elm City Properties
- Email says shop rent is due in 2 days.
- **lease 1:** Chapel Street shop, landlord Elm City Properties, $2,400.00/month, `next_due` 2026-09-02. This matches the notice (2 days after 2026-08-31).
- **cash_accounts:** checking balance is $3,400.00 (as of 2026-08-31).
- What this means: before paying, confirm the requester, amount, and due date against the lease record, then record the payment in `payments`.

### Ticket 103 — `price_override` from Yale AI Club
- Wants 20 × `CC-HOOD-NAVY` (Basic Hoodie Big Yale) in size **M** and is asking for a bulk discount.
- **inventory:** size M has only `qty = 8` (Aisle A), **12 short**. Other sizes: S 4, L 14, XL 6.
- **pricing:** unit cost $22.00, list price $58.00. At list price the order is $1,160 with $720 margin. The price floor is $22/unit, the break-even point.
- What this means: a discount means an agent changes the price (it needs a margin check and approval). Filling the full order needs either a reprint or a size swap.

### Cross-ticket constraint: cash
Paying both open obligations (invoice 501 at $840 plus rent at $2,400 = **$3,240**) leaves **$160** in checking. Both bills fit, but there is almost no room for anything else, such as a second reprint for the hoodie order. Agents should check the balance before each payment.

## MCP server (`mcp_server/server.py`)

A FastMCP server named `campus-customs`, which every agent in this homework shares. It reads only from `data/campus_customs_new.db`, returns values exactly as stored (plus simple math on them), and returns `"found": false` instead of guessing when a record doesn't exist. All three tools are read-only.

### Tool 1 — `check_stock(sku, size, qty_needed=1)`
- **Reads:** `inventory`
- **Unlocks:** Ticket **101**, Tauhid Zaman's order for 1 × `CC-TEE-WHITE` size S
- **Why it's the right tool:** Ticket 101 asks whether we can ship one Classic Bulldog Tee in size S. `check_stock('CC-TEE-WHITE', 'S', 1)` returns `qty_on_hand: 0`, `can_fill: false`, and the in-stock alternatives (M: 5, L: 3, XL: 2). The agent can then truthfully tell Tauhid the item is out of stock and offer a size swap instead of promising a tee we don't have. (The same call with `('CC-HOOD-NAVY', 'M', 20)` also shows ticket 103's 12-unit shortfall.)

### Tool 2 — `get_rent_due(lease_id)`
- **Reads:** `leases`, `desk`, `cash_accounts`
- **Unlocks:** Ticket **102**, Elm City Properties' "rent due in 2 days" email (linked to `lease_id = 1`)
- **Why it's the right tool:** Ticket 102 is an emailed payment demand. `get_rent_due(1)` lets the agent check it against our own records before any money moves: landlord Elm City Properties, $2,400.00, due 2026-09-02, `days_until_due: 2` from the desk date 2026-08-31. It also returns the $3,400.00 checking balance, so the agent knows the rent can be covered.

### Tool 3 — `get_pricing(sku, qty=1)`
- **Reads:** `pricing`
- **Unlocks:** Ticket **103**, Yale AI Club's bulk-discount request for 20 × `CC-HOOD-NAVY`
- **Why it's the right tool:** Ticket 103 is a price-override request, so the agent needs the real cost floor before it can offer any discount. `get_pricing('CC-HOOD-NAVY', 20)` returns $22.00 cost and $58.00 list ($1,160.00 at list, $440.00 at cost). The maximum discount before a loss is 62.1%, so any bulk price the agent proposes stays profitable.

### Added later
The gap noted here (nothing read `invoices`, `vendors`, or `payments`, and nothing could write) was closed by 11 tools in Problem 5 and 4 more in Problem 7. `record_payment`, added in Problem 5, was removed in Problem 7, so the server now has 18 tools. See **MCP tools (full list)** below.

## Connecting the MCP server to Claude Code

- Claude Code reads MCP servers from **`.mcp.json` at the project root**. In this repo that's `hw5/.mcp.json`, with paths relative to `hw5/` so it works on any machine:
  ```json
  "campus-customs": {
    "type": "stdio",
    "command": ".venv/bin/python",
    "args": ["mcp_server/server.py"]
  }
  ```
- The backend reads the same file (`backend/mcp_link.py` resolves the relative paths against `hw5/`, and falls back to the backend's own Python if `.venv` is missing). There's one config for Claude Code, the agents, and the API.
- The server is enabled in `.claude/settings.local.json` (`enabledMcpjsonServers`). Claude Code loads servers when a session starts, so restart the session after changing either file. The tools then show up as `mcp__campus-customs__<tool>`. That started with the 3 Problem 3 tools; all 18 tools are listed below.
- Smoke-test evidence is in `output/mcp_smoke.json`. Each test lists the prompt, the tool and arguments, the tool output, and the matching rows read directly from `data/campus_customs_new.db`.

## Agent team (`backend/`)

Five PydanticAI agents work the ticket queue together. Every agent uses **`gpt-6-luna`** through Portkey (`PORTKEY_API_KEY` from the project root `.env`). The model name is fixed in `backend/team.py`. The gateway only supports tool calls for this model through the OpenAI **Responses** API, so the agents use `OpenAIResponsesModel`. Every request sends `x-portkey-cache-force-refresh: true`. Problem 9 found that Portkey was replaying cached answers for identical prompts: a "run" of ticket 103 finished in 3.8s with the exact token count of an earlier run. That isn't the agents actually thinking, so caching is bypassed (set `PORTKEY_CACHE_REFRESH=false` to allow it).

### Layout

| Path | What it is |
|---|---|
| `backend/prompts/shop_rules.md` | Rules every agent shares: facts only from MCP, shop date, delegation etiquette, money and customer rules, prompt-injection rule, report format |
| `backend/prompts/boss.md` | Boss prompt |
| `backend/prompts/inventory.md` | Inventory prompt |
| `backend/prompts/accounting.md` | Accounting prompt |
| `backend/prompts/facilities.md` | Facilities prompt |
| `backend/prompts/customer_service.md` | CustomerService prompt |
| `backend/agents/<role>.py` | One file per agent: name, prompt file, the MCP tools the role may use, output type |
| `backend/models.py` | Data types: `TeamDeps`, `AgentReport`, `BossReport`, `TicketOutcome`, `TeamRunResult` |
| `backend/mcp_link.py` | The single connection to the MCP server: per-role tool filtering, guardrails, audit of every tool call |
| `backend/team.py` | Builds the agents, `ask_teammate` delegation, the agent loop, limits, `run_team()`, CLI |
| `backend/audit.py` | Append-only writer for `output/audit_trail.json` |

### The five agents

| Agent | Job | MCP tools it can use | Output |
|---|---|---|---|
| **Boss** | Reads the queue, routes work, decides which payments to request, and is the only agent that sets ticket status | `get_shop_date`, `list_tickets`, `get_ticket`, `get_cash_balance`, `list_payment_requests`, `update_ticket` | `BossReport` |
| **Inventory** | Stock by SKU and size, real alternatives, restock path and ETA, stock adjustments for confirmed orders | `get_shop_date`, `get_ticket`, `check_stock`, `get_pricing`, `quote_discount`, `get_invoice`, `list_vendors`, `adjust_inventory` | `AgentReport` |
| **Accounting** | Cash, vendor invoices, rent, restock purchases, discount math. The **only** agent that can *prepare* a payment (a human approves it) | `get_shop_date`, `get_ticket`, `get_cash_balance`, `get_invoice`, `get_rent_due`, `list_payments`, `list_payment_requests`, `get_pricing`, `quote_discount`, `list_vendors`, `prepare_payment`, `prepare_purchase` | `AgentReport` |
| **Facilities** | Lease and landlord: checks rent notices against the lease (fraud check); vendor and courier logistics | `get_shop_date`, `get_ticket`, `get_rent_due`, `list_vendors`, `get_cash_balance` | `AgentReport` |
| **CustomerService** | Drafts honest customer replies (a human sends them); never sees costs | `get_shop_date`, `get_ticket`, `check_stock`, `get_invoice` | `AgentReport` |

All five also have **`ask_teammate(teammate, task)`**, which lets any agent ask any other agent for help (full mesh). The teammate runs its own loop inside the caller's tool call and returns its structured report. A teammate already in the current chain is refused, which prevents A→B→A loops.

### Agent loop

1. `run_team(task, entry="Boss", read_only=False, run_id=None)` opens **one** MCP connection for the whole run and starts the entry agent's loop (`agent.iter`).
2. Each loop step is one model response. It either calls tools (MCP tools, filtered to the role, or `ask_teammate`) or returns its final structured report.
3. A delegation starts the teammate's loop with `depth + 1`, the chain extended, and the **same shared usage counter**, so team-wide limits cover every agent together.
4. The run ends when the entry agent returns its report, or when a limit or error stops it. The stop reason is recorded either way.

### How to run

```bash
cd hw5 && source .venv/bin/activate          # the single env from requirements.txt
cd backend
python team.py "Status briefing on all open tickets. Check only." --read-only
python team.py "Work ticket 102 end to end."
```

Flags: `--entry <Agent>` starts the run at a different agent. `--read-only` blocks all writes. `--db PATH` uses a different database copy (e.g. a scratch copy for testing).

## MCP tools (full list)

Server: `mcp_server/server.py` (FastMCP, `campus-customs`), using `data/campus_customs_new.db`. All shop facts come from these tools, for the agents and for the API routes alike; there is no other shop-data layer. The server adds one table on first use, `payment_requests`, for payments the agents prepare and a human decides on.

| Tool | Type | Tables | Used by | Added in |
|---|---|---|---|---|
| `check_stock(sku, size, qty_needed)` | read | `inventory` | Inventory, CustomerService | P3 |
| `get_rent_due(lease_id)` | read | `leases`, `desk`, `cash_accounts` | Accounting, Facilities | P3 |
| `get_pricing(sku, qty)` | read | `pricing` | Inventory, Accounting | P3 |
| `get_shop_date()` | read | `desk` | all | P5 |
| `list_tickets(status)` | read | `tickets` | Boss | P5 |
| `get_ticket(ticket_id)` | read | `tickets`, `inventory`, `pricing`, `leases`, `invoices`, `vendors` | all | P5 |
| `quote_discount(sku, qty, discount_pct)` | read | `pricing`, `inventory` | Inventory, Accounting | P5 |
| `get_invoice(invoice_id)` | read | `invoices`, `vendors`, `desk` | Inventory, Accounting, CustomerService | P5 |
| `list_vendors()` | read | `vendors` | Inventory, Accounting, Facilities | P5 |
| `get_cash_balance()` | read | `cash_accounts`, `invoices`, `desk` | Boss, Accounting, Facilities | P5 |
| `list_payments(limit)` | read | `payments` | Accounting | P5 |
| `list_payment_requests(status)` | read | `payment_requests` | Boss, Accounting, API | P7 |
| `update_ticket(ticket_id, status, note)` | **write** | `tickets` | Boss | P5 |
| `adjust_inventory(sku, size, delta, reason)` | **write** | `inventory` | Inventory | P5 |
| `prepare_payment(kind, ref_id, amount, ticket_id, reason, resolves_ticket)` | **write** (request only, no cash moves) | `payment_requests` (checks `invoices`/`leases`, `payments`, `cash_accounts`) | Accounting | P7 |
| `prepare_purchase(vendor_id, sku, size, qty, ticket_id, reason, resolves_ticket)` | **write** (request only, no cash moves) | `payment_requests` (amount = `pricing.unit_cost` × qty) | Accounting | P7 |
| `approve_payment_request(request_id, approved_by)` | **write, human only** | `payment_requests`, `payments`, `cash_accounts`, `invoices` / `leases`, `tickets` | API approve route only | P7 |
| `reject_payment_request(request_id, rejected_by, note)` | **write, human only** | `payment_requests`, `tickets` | API reject route only | P7 |

`record_payment` (P5) was removed in Problem 7. Agents can't move money at all; the only thing that changes cash is `approve_payment_request`, called by the approve route after a person clicks Approve.

Which tool unlocks which ticket:
- **101 (tee size S):** `get_ticket` → `check_stock` (0 on hand, alternatives) → `get_invoice(501)` (reprint bill $840, 3 days overdue, ETA 2026-09-05 if paid today) → `prepare_payment('invoice', 501, 840)` (pending until a human approves) → CustomerService draft.
- **102 (rent notice):** `get_ticket` → `get_rent_due(1)` (Facilities checks the landlord, $2,400, and the due date) → `list_payments` and `get_cash_balance` → `prepare_payment('rent', 1, 2400, resolves_ticket=True)` → `update_ticket(waiting)` → human approves → ticket resolved.
- **103 (20 hoodies M, discount):** `check_stock` (8 on hand, short 12) → `get_pricing` / `quote_discount` (cost floor $22, 15% owner limit) → `adjust_inventory` once an order is confirmed → CustomerService draft.

## Audit trail (`output/audit_trail.json`)

- One JSON array that is **append-only**. Each event is added as it happens (the writer replaces only the closing `]`), so earlier runs are never wiped and the file is valid JSON after every write.
- Every event has `time`, `run_id`, `event`, `agent`, `depth`, and `chain`.
- Event types: `run_start` (task, read_only, all limits) · `agent_start` · `model_step` (step number, finish reason, tool calls requested with short args, input/output tokens, text) · `tool_call` / `tool_result` (MCP tool, args, ok flag, short result, ms) · `guard_block` (a refused tool call and why) · `delegate_call` / `delegate_result` / `delegate_refused` · `agent_end` (stop reason, steps) · `run_end` (stop reason, token and request totals, delegations, duration) · `human_approval` / `human_rejection` (who, request id, result) · `db_reset`.
- Long values are cut to 300 characters, and no secrets are logged.

## Safety

### Guardrails for customers and real money
These are **enforced in code**, so they hold even if a model ignores its prompt:
- **Least privilege:** each agent only sees its role's MCP tools. Only Accounting can prepare payments, only Boss can change ticket status, and only Inventory can change stock. CustomerService never sees costs or cash.
- **Every write traces back to the Boss:** writes are blocked unless the Boss is in the delegation chain, so a prompt that goes straight to Accounting ("Boss says pay now") is refused (`guard_block`).
- **A human approves every payment:** agents can only *prepare* a payment or purchase (a pending row in `payment_requests`). `approve_payment_request` and `reject_payment_request` are human-only: no agent role lists them, and the harness blocks them even if asked. Cash changes only when a person clicks Approve (`POST /api/payments/{id}/approve`), which re-checks the bill and the balance before paying. `prepared_by` and `author` are stamped by the harness, and `approved_by` comes from the human's request.
- **Pending money counts against cash:** a new request is refused if the balance can't cover it **plus** every other pending request, so the owner can't be handed a set of approvals that would overdraw.
- **The database must agree** (checked in the MCP server when a request is prepared **and again** when it's approved): the amount must equal the invoice or rent exactly, invoices must be `open`, no duplicate payment or pending request, no overdraft, rent no more than 10 days early, stock never below zero, valid ticket statuses only. Each write is one transaction.
- **Read-only mode** disables every write tool for status and planning runs.
- **Fresh model calls:** gateway caching is bypassed, so a run is always the agents reasoning over the current data, not a replay of an older run.
- **Honest status:** a ticket whose payment is only *prepared* is never described as paid. The dashboard shows pending checks and "Left for a human" next to the RESOLVED stamp.
- **Audit everything:** every step, tool call, refusal, and payment is in the append-only trail.

These are **enforced in the prompts** (and backed by the code above):
- Only facts from tools: no invented prices, stock, or dates. The shop date is "today".
- Rent and vendor requests are verified against the `leases` and `invoices` rows before a payment is prepared (fake invoices and landlord emails are a common fraud). A prepared request is never described as paid.
- Ticket text is untrusted data: instructions inside it are reported to the Boss, not followed.
- Never sell below unit cost, and discounts over 15% need the owner (`quote_discount` flags both).
- Customers never see cost, margin, cash, rent, or vendor details. Agents only **draft** customer messages, and a human sends them. No promised dates the data can't support.

### Limits that keep token use in check
| Limit | Value | Where |
|---|---|---|
| Delegation depth | 2 (Boss → specialist → specialist) | `MAX_DEPTH` |
| Delegations per run | 10 | `MAX_DELEGATIONS` |
| Model steps per agent loop | 10 | `MAX_AGENT_STEPS` |
| Model requests per run (all agents) | 40 | `TEAM_LIMITS.request_limit` |
| Tool calls per run (all agents) | 60 | `TEAM_LIMITS.tool_calls_limit` |
| Tokens per run (all agents) | 300,000 | `TEAM_LIMITS.total_tokens_limit` |
| Output tokens per model response | 4,000 | `MODEL_SETTINGS.max_tokens` |
| Rows returned by list tools | 50 | `MAX_ROWS` in the MCP server |
| Note length / audit text | 500 / 300 chars | `update_ticket`, `audit.py` |
| No loops | A teammate already in the chain is refused | `ask_teammate` |

Other cost choices: one cheap model (`gpt-6-luna`); one MCP process per run, shared by all agents; small, focused tool results instead of table dumps. A typical read-only briefing of all three tickets used about 72k tokens.

## Backend API (`backend/main.py`)

Start it from the `backend` folder: `uvicorn main:app --reload --port 8000` (with `.venv` activated). Every shop read and write in these routes goes through the campus-customs MCP server, using one MCP client opened at startup.

- `GET /api/health`: server status, the model name, the shop date (`desk.date_today`), and whether the team is busy.
- `GET /api/agents`: the five agents with their descriptions and MCP tools.
- `GET /api/tickets`: all tickets, each with `status`, `state` (`open` or `resolved`), pending payment request ids, and the last run id.
- `GET /api/tickets/{id}`: one ticket with its linked stock, lease, and invoice rows.
- `POST /api/tickets/{id}/run`: runs the agent team on that ticket in the background and returns a `run_id` right away (202). Returns 409 if a run is already going. The optional body is `{task, read_only}`.
- `GET /api/runs`: the team runs started since the server came up, newest first.
- `GET /api/runs/{run_id}`: one run's status, final report, every audit event, and `by_agent` (what each agent said, which tools it used, whom it asked).
- `GET /api/events?since=N&run_id=…&limit=…`: recent audit-trail events after index `N`, plus `by_agent` and `next_since` so the board can poll.
- `GET /api/payments?status=pending`: payment and purchase requests the agents prepared (`pending`, `approved`, `rejected`, or `all`).
- `POST /api/payments/{id}/approve`: **the human Approve button**, and the only route that changes cash. It re-checks the request, then pays it: a new `payments` row, a lower balance, the invoice marked paid or the lease due date moved forward, and a ticket note. Body: `{by}`.
- `POST /api/payments/{id}/reject`: the human Reject button. It marks the request rejected and moves no money. Body: `{by, note}`.
- `GET /api/cash`: the checking balance from `cash_accounts`, plus pending request totals and the balance if every pending request were approved.
- `POST /api/reset`: copies `data/campus_customs.db` over `data/campus_customs_new.db` for a fresh run. Refused while the team is running. The audit trail is kept and a `db_reset` event is added.

### Ticket status rule (Problems 8–9)
The Boss sets `resolved` when the **team's** part of a ticket is done: facts checked, payment *prepared*, customer reply *drafted*. Anything left for a human (approve request #id, send the draft, the customer's choice) goes in `needs_human`, and the dashboard shows it. `waiting` is **only** for when a teammate couldn't finish its own work (a tool failed or data is missing). Waiting on a customer or the owner is not "blocked" (clarified in Problem 9, after the Boss parked 101 as `waiting` twice). `escalated` means the ticket can't be handled safely. A prepared payment is still unpaid until a human approves it.

## Frontend dashboard (`frontend/`)

React + Vite + TypeScript, with no UI library. Start it with `npm run dev`; it opens the desk at `http://localhost:5173`. It talks to the backend at `VITE_API_URL` in `frontend/.env` (default `http://localhost:8000`), and the backend's CORS allows that page (http/https, localhost/127.0.0.1, ports 5173/5174). The look and the reasons behind it are in `output/design.md`.

| Board area | What it shows | Routes it uses |
|---|---|---|
| Top bar | Shop date, **Checking** balance (rolls down when a payment is approved, with "$X awaiting your signature → $Y after"), Reset desk | `GET /api/health`, `GET /api/cash`, `POST /api/reset` |
| Queue (left) | The three tickets as stubs: status pill, a "✍ n to sign" badge, and a **RESOLVED / WAITING / ESCALATED** rubber stamp | `GET /api/tickets` (every 4s) |
| Brief + **Send to the team** | The selected ticket's facts; the button starts a run (disabled while the team is busy) | `POST /api/tickets/{id}/run` |
| Agent floor | Five CSS creatures (Boss on top, four specialists), each with a live speech bubble in its own voice. Delegation threads light up while a hand-off is open; agents the Boss didn't call grey out | `GET /api/events?run_id&since` (every ~1s while running) |
| Live wire | Each audit event turned into a plain-English line ("counting CC-TEE-WHITE size S…") | same events feed |
| What happened | The Boss's verdict, one card per agent (last words, tool chips, whom it asked), "Left for a human", the customer draft as a postcard, changes made, and tokens/time | `GET /api/runs/{run_id}` |
| Needs your signature (right) | Pending requests as **checks** (payee, amount, memo, prepared by, ticket). **Approve & pay** / Reject, and a receipt tape of decisions | `GET /api/payments`, `POST /api/payments/{id}/approve`, `POST /api/payments/{id}/reject` |

## Problem 9 full-run results

The working database was reset (checking **$3,400.00**). All three tickets were then run from the board until resolved, and a human (Archita) approved both payments on the board. The final check: **$3,400.00 − $840.00 (invoice 501, ticket 101) − $2,400.00 (rent, lease 1, ticket 102) − $0.00 (ticket 103, quote only) = $160.00**, which equals `cash_accounts.balance`.

| Ticket | Final runs | Agents (who the Boss called first) | Money |
|---|---|---|---|
| 101 | `616363760829` (waiting) → approval → `3453b03e615b` (waiting) → Boss rule clarified → `18883d273587` (resolved) | **Inventory** first, Accounting, CustomerService (which also asked Inventory). Facilities not called | Request #1 → payment #1, −$840.00 |
| 102 | `e0dcbdc7df0b` (resolved) | **Facilities** first, then Accounting. Inventory and CustomerService not called | Request #2 → payment #2, −$2,400.00 |
| 103 | `1e6407939380` (resolved) | **Inventory** first, Accounting, CustomerService (which asked Accounting twice). Facilities not called | none |

Evidence: `output/desk_tickets.html` (Expected vs Actual per ticket, plus the Cash tab), `output/resolved_tickets.json`, `output/resolved_board.html` (board screenshots), and these run ids in `output/audit_trail.json`. The audit trail also keeps earlier test runs and an abandoned first attempt whose 103 run was a cache replay; the database was reset after it, so it doesn't affect the cash above.
