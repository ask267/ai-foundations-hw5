# Campus Customs: Night Desk (dashboard design)

**Run it:** with `hw5/.venv` active (see `README.md`), start the backend (`cd backend && uvicorn main:app --reload --port 8000`), then the board (`cd frontend && npm run dev`). Vite opens `http://localhost:5173`. The board calls the backend at the URL in `frontend/.env` (`VITE_API_URL=http://localhost:8000`).

## The idea

The board isn't a log viewer; it's a desk you work at. Tickets come in as paper stubs. Five small creatures work the problem in front of you, and nothing costs money until **you** sign a check. The design borrows its type and motion from the hw4 storefront: Instrument Serif headlines, Inter Tight body text, JetBrains Mono for numbers, soft easing, and a bit of 3D tilt. It moves that look into this project's black-and-pink palette, so it reads as Campus Customs after closing time: a quiet back office lit in pink.

## Layout: three columns, left to right

| Column | What's there | Why |
|---|---|---|
| **The queue** (left) | The three tickets as **ticket stubs**: big serif number, type, subject, requester, a dashed perforation with punched notches, and a status pill | You always see the whole queue and how many are resolved ("1/3 resolved") |
| **The stage** (center) | A **brief** for the selected ticket (serif headline, mono fact chips, the customer's own words in italics) with one big pink **Send to the team** button. Below it is **the floor**, where the agents work. Below that, the **Live wire** feed sits next to **What happened** | The center column follows the work in order: what was asked, who's doing it, what they're saying, what came out |
| **Needs your signature** (right) | Prepared payments as **checks**, a "Signing as" field, and a **receipt tape** of everything approved or rejected | Money decisions get their own column so they're never buried in agent chatter |

Across the top, a sticky bar holds the brand, the **shop date** (from `desk`, not the real clock), the **Checking** balance, and **Reset desk**.

Below 1280px the signature column moves under the stage. Below 820px everything stacks into one column.

## How the agents read differently

Each agent is a **CSS-only creature** (no images), with its own accessory, color, and speaking style. You can tell who is talking at a glance, even in the feed:

| Agent | Look | Voice in their speech bubble |
|---|---|---|
| **The Boss** | Hot pink, gold **crown**, bigger than everyone, top center | *Serif italic*, like a manager's note |
| **Inventory** | Light pink, yellow **hard hat** | `monospace`, because it's all counts and SKUs |
| **Accounting** | Peach, green **banker's visor** | `monospace` on faint **ledger lines** |
| **Facilities** | Lilac, a little **key** on its ear | Sits on a faint **blueprint grid** |
| **Customer Service** | Blush, a **headset** | Rounder, softer bubble in plain warm text |

Their state shows on their faces:
- **Working:** the creature bobs, its mouth moves, and its bubble glows in its color.
- **Done:** happy closed-arc eyes.
- **Idle:** sleepy line eyes.
- **Blocked:** desaturated, with a frown.
- **Benched:** agents the Boss never called on this ticket fade to grey with "not needed on this one". You can see the routing was **selective**, which was the goal of the Problem 6 plan.

**Delegation threads:** faint dotted lines link the Boss to every specialist. When the Boss (or anyone) calls `ask_teammate`, that line turns into a **marching pink dash**, in the teammate's color, until the teammate answers; then it stays as a solid trace. A specialist-to-specialist hand-off (e.g. Customer Service asking Accounting) draws an arc between them. You can read the call graph straight off the floor.

The bubbles never show raw tool names. `check_stock {"sku":"CC-TEE-WHITE","size":"S"}` becomes "counting CC-TEE-WHITE size S (need 1)…", and `prepare_payment` becomes "preparing invoice payment $840.00 for your signature…".

## Live wire and What happened

- **Live wire** turns each audit event into one plain-English line (agent name in its color, time, text). Hand-offs are pink, finished summaries are serif italic, and refusals or harness blocks are red. It auto-scrolls and shows a pulsing "streaming" pill while the run is live. It polls `/api/events?run_id=…&since=…` every ~1s.
- **What happened** appears when the Boss signs off:
  - the Boss's verdict as a pink pull quote with the final status
  - one **card per agent who worked**: their last words, a chip for each MCP tool they used (with ×counts), and pink chips for whom they asked
  - **Left for a human**: items tick off with "✓ decided" once you sign or reject the check
  - the customer reply drafted as a **paper postcard** with a pink stamp, because a human still has to send it
  - **Changes made** (writes only)
  - the run's cost: tokens, model calls, hand-offs, and seconds

## How resolved tickets show up

When a run finishes and the Boss marks the ticket `resolved`, a **rubber stamp slams onto the stub**: "RESOLVED" in pink ink, rotated, with a quick scale-down "thunk". The stub then dims slightly, like a finished ticket on a spike. `waiting` gets a dashed yellow stamp and `escalated` a red one. While the team is working, the stub has a **pink sheen sweeping across it** and a "team working" pill. A "✍ 1 to sign" pill on the stub means that ticket has a check waiting for you.

## How cash shows up

- **Checking** is the biggest number on the screen, in tabular mono, at the top right.
- Under it: "$840.00 awaiting your signature → **$2,560.00** after". You see the effect of a decision *before* you make it.
- Prepared payments arrive in the right column as **pink paper checks**: "Pay to Vendor invoice #501", the amount in a boxed field, the agent's reason as the **memo**, and "prepared by Accounting · ticket #101".
- **Approve & pay** writes your name across the signature line in pink script, then the check slides away. Only after that does the board call `POST /api/payments/{id}/approve`, the one route that moves money.
- The balance then **rolls down** like an odometer ($3,400.00 → $2,560.00), flashes pink, and a **"−$840.00"** chip floats up and fades. A line prints onto the **receipt tape** (thermal-paper colors with a torn zig-zag bottom): "Vendor invoice #501 −$840.00, approved by Archita". Rejected checks print as a struck-through "void".

## Why it's enjoyable to use

- **You're the owner, not an observer.** The one moment that matters, spending money, feels like signing a check, not clicking an "OK" dialog. Your name goes on it.
- **Agents feel like a team.** Five little creatures with hats, a crown, a visor, and a headset, each talking in their own type style, make a multi-agent trace something you *watch* instead of parse.
- **Selective routing is visible.** Greyed-out benched agents and lit threads show the Boss only called who it needed, which is exactly what the Problem 6 plan predicted.
- **Paper metaphors carry meaning:** ticket stub = request, stamp = status, check = pending money, receipt = paid money, postcard = a message for a human to send.
- **Calm by default.** A dark background, one accent color, motion only where something changed (stamp, odometer, sheen, marching thread), and `prefers-reduced-motion` turns all of it off.
- **Honest numbers.** Every figure on screen comes from the API, which reads it through the MCP server. The board never computes a balance itself; it just animates between real values.

## Implementation notes

- React 19 + Vite + TypeScript, with no UI libraries. Everything is plain CSS (`src/index.css`); creatures and stamps are pure CSS.
- `src/api.ts`: typed client for every Problem 7 route. `src/useDesk.ts`: polling (tickets, cash, and payments every 4s; live events every ~1.1s). `src/agents.ts`: the agent roster, tool-to-sentence phrasing, and feed formatting.
- Components: `TicketRail`, `AgentFloor` (+ `Avatar`), `LiveFeed`, `RunSummary`, `ApprovalTray`, `CashMeter`.
- The backend's CORS allows the Vite page on `http(s)://localhost:5173` (and 5174 or `127.0.0.1`, in case 5173 is taken).
