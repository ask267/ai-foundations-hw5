# AI Foundations — Homework 5: Campus Customs Night Desk

A five-agent back office for the Campus Customs shop. **Boss, Inventory, Accounting, Facilities, and CustomerService** (PydanticAI, `gpt-6-luna` via Portkey) work a ticket queue. Every shop fact and change goes through one **FastMCP server** over a SQLite database. A **FastAPI** backend runs the team, and a **React** board lets a human watch the agents and **approve every payment**: agents can only *prepare* money, never move it.

```
React board (frontend/, :5173) ──► FastAPI (backend/main.py, :8000) ──► agent team (backend/team.py)
                                          │                                   │
                                          └──────► campus-customs MCP server (mcp_server/server.py) ◄──┘
                                                              │
                                                  data/campus_customs_new.db
```

Full documentation is in **[`output/harness.md`](output/harness.md)**. It covers the tables, all 18 MCP tools, the agents, API routes, the dashboard, and the safety rules.

## Layout

```
hw5/
├── AI_prompts.md              prompts used for each problem
├── requirements.txt           Python deps (MCP server + agents + backend)
├── .env.example               copy to .env and add PORTKEY_API_KEY
├── .mcp.json                  campus-customs MCP server entry (Claude Code + backend)
├── data/
│   ├── campus_customs.db      original seed database (never modified)
│   └── campus_customs_new.db  working copy (state after the Problem 9 run: checking $160.00)
├── mcp_server/                server.py (FastMCP, 18 tools), README.md
├── backend/                   main.py (API), team.py (agent loop), models.py, mcp_link.py,
│                              audit.py, agents/ (one file per role), prompts/ (one .md per agent)
├── frontend/                  React + Vite + TypeScript board
└── output/                    harness.md, mcp_smoke.json, desk_tickets.html, design.md,
                               resolved_tickets.json, resolved_board.html (+ images),
                               audit_trail.json, github_url.txt
```

## Setup (once)

Requires Python 3.11+ and Node 20+.

```bash
cd hw5
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env            # then put your PORTKEY_API_KEY in .env

cd frontend && npm install && cd ..
```

## 1. Copy the original DB to the working copy (when you need a clean run)

`data/campus_customs_new.db` is the working copy that the MCP server, agents, and board use. It's submitted in its **post-Problem-9 state** (all three tickets resolved, checking **$160.00**), which matches the Cash tab in `output/desk_tickets.html`. To start over from the original data:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

You can also click **↺ Reset desk** on the board (`POST /api/reset`), which does the same copy. The MCP server adds a `payment_requests` table on first use, so a fresh copy works right away.

## 2. Start the MCP server

The `campus-customs` server runs over **stdio**, so it's normally started for you:
- **The backend and agent team** launch it from `.mcp.json` every time they need it. You don't need a separate terminal.
- **Claude Code:** open this `hw5` folder as the project. Claude Code reads `.mcp.json`, asks you to approve `campus-customs`, and the tools appear as `mcp__campus-customs__*`.
- **To run it by hand** (e.g. to check it starts):
  ```bash
  source .venv/bin/activate
  python mcp_server/server.py
  ```
  It waits for an MCP client on stdin/stdout. Press Ctrl+C to stop.

## 3. Start the FastAPI backend

```bash
cd backend
source ../.venv/bin/activate
uvicorn main:app --reload --port 8000
```

Check it at http://localhost:8000/api/health and http://localhost:8000/api/tickets.

## 4. Start the React board

In a second terminal:

```bash
cd frontend
npm run dev
```

This opens the desk at **http://localhost:5173** and talks to the backend at `http://localhost:8000` (set in `frontend/.env.example` / `VITE_API_URL`; that address is also the default).

## 5. Reset the DB before a full three-ticket run

1. Click **↺ Reset desk** on the board, or run `cp data/campus_customs.db data/campus_customs_new.db` with the backend stopped. Checking should read **$3,400.00**.
2. Pick **#101**, click **Send to the team**, and watch the agents. When an $840.00 check appears under *Needs your signature*, click **Approve & pay**.
3. Do the same for **#102**: approve the $2,400.00 rent check.
4. Run **#103**. It produces a quote only, with no payment.
5. Expected end state: all three tickets **resolved**, checking **$160.00** ($3,400 − $840 − $2,400).

Every step is appended to `output/audit_trail.json`, which is never wiped. Note that running tickets or resetting changes the working DB, so the submitted evidence in `output/` describes the run recorded there.

## Agent team from the command line (optional)

```bash
cd backend && source ../.venv/bin/activate
python team.py "Status briefing on all open tickets. Check only." --read-only
```

## Safety in one paragraph

Each agent sees only its role's MCP tools. Writes must come from a Boss-led run. Agents can only **prepare** payments and purchases (`payment_requests`). Cash changes only when a human approves on the board (`POST /api/payments/{id}/approve`), which re-checks the bill against the database first. The database checks block wrong amounts, duplicates, overdrafts, early rent, and negative stock. Customers never see costs, margins, or cash. Limits on delegation depth, hand-offs, steps, requests, tool calls, and tokens keep each run bounded. Details are in `output/harness.md` → *Safety*.

## Outputs (`output/`)

| File | What it is |
|---|---|
| `harness.md` | How the whole system works |
| `mcp_smoke.json` | Problem 4 MCP tool smoke test |
| `desk_tickets.html` | Expected plan vs Actual for each ticket, the Cash tab, and the Reflection tab |
| `design.md` | Dashboard design choices |
| `resolved_tickets.json` | Final status, outcome, agent contributions, and human approvals per ticket |
| `resolved_board.html` | Screenshots of the board for each resolved ticket |
| `audit_trail.json` | Append-only log of every agent step, tool call, delegation, and human approval |
| `github_url.txt` | This repository's URL |

> Never commit a real `.env`. It's in `.gitignore`; only `.env.example` is tracked.
