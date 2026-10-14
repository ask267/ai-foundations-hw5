import { useEffect, useState } from 'react'
import { API_URL } from './api'
import { TICKET_TYPE_LABEL } from './agents'
import { AgentFloor } from './components/AgentFloor'
import { ApprovalTray } from './components/ApprovalTray'
import { CashMeter } from './components/CashMeter'
import { LiveFeed } from './components/LiveFeed'
import { RunSummary } from './components/RunSummary'
import { TicketRail } from './components/TicketRail'
import { useDesk } from './useDesk'

function fmtShopDate(iso: string | null) {
  if (!iso) return '—'
  const d = new Date(`${iso}T12:00:00`)
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
}

function useElapsed(since: number | null) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (since === null) return
    const id = window.setInterval(() => setNow(Date.now()), 500)
    return () => window.clearInterval(id)
  }, [since])
  return since === null ? 0 : Math.max(0, Math.round((now - since) / 1000))
}

export default function App() {
  const desk = useDesk()
  const [selected, setSelected] = useState<number | null>(null)
  const [signer, setSigner] = useState(() => localStorage.getItem('desk.signer') ?? 'Owner')
  const [confirmReset, setConfirmReset] = useState(false)

  useEffect(() => localStorage.setItem('desk.signer', signer), [signer])

  // Default to the first ticket once they load.
  useEffect(() => {
    if (selected === null && desk.tickets.length) setSelected(desk.tickets[0].id)
  }, [desk.tickets, selected])

  const { loadRun } = desk
  const ticket = desk.tickets.find((t) => t.id === selected) ?? null
  const run = ticket ? desk.runs[ticket.id] : undefined
  const running = run?.status === 'running'
  const elapsed = useElapsed(running ? run!.startedAt : null)

  // Restore the last run for a ticket the server still remembers.
  useEffect(() => {
    if (ticket?.last_run_id && !run) void loadRun(ticket.id, ticket.last_run_id)
  }, [ticket?.id, ticket?.last_run_id, run, loadRun])

  return (
    <div className="app">
      <div className="glow glow--a" />
      <div className="glow glow--b" />

      <header className="top">
        <div className="brand">
          <div className="brand__mark">CC</div>
          <div>
            <div className="brand__name">
              Campus Customs <em>Night Desk</em>
            </div>
            <div className="brand__sub">five agents · one queue · you hold the pen</div>
          </div>
        </div>

        <div className="top__date">
          <span className="eyebrow">Shop date</span>
          <span className="top__day">{fmtShopDate(desk.shopDate)}</span>
        </div>

        <CashMeter cash={desk.cash} />

        <div className="top__actions">
          {confirmReset ? (
            <div className="confirm">
              Reset everything to the original data?
              <button className="btn btn--pink btn--sm" onClick={() => { setConfirmReset(false); void desk.reset() }}>Reset</button>
              <button className="btn btn--ghost btn--sm" onClick={() => setConfirmReset(false)}>Cancel</button>
            </div>
          ) : (
            <button className="btn btn--ghost btn--sm" disabled={desk.busy} onClick={() => setConfirmReset(true)} title="Copy the original database back">
              ↺ Reset desk
            </button>
          )}
        </div>
      </header>

      {desk.online === false && (
        <div className="banner">
          Can't reach the desk backend at <code>{API_URL}</code>. Start it from <code>backend/</code> with{' '}
          <code>uvicorn main:app --reload --port 8000</code>.
        </div>
      )}
      {desk.error && desk.online !== false && (
        <div className="banner banner--soft" onClick={() => desk.setError(null)}>
          {desk.error} <span className="banner__x">dismiss</span>
        </div>
      )}

      <main className="layout">
        <TicketRail tickets={desk.tickets} selected={selected} runs={desk.runs} onSelect={setSelected} />

        <section className="stage">
          {ticket ? (
            <>
              <div className="brief">
                <div className="brief__left">
                  <span className="eyebrow">
                    {TICKET_TYPE_LABEL[ticket.type] ?? ticket.type} · from {ticket.requester}
                  </span>
                  <h1>
                    <span className="brief__no">#{ticket.id}</span> {ticket.subject}
                  </h1>
                  <div className="facts">
                    {ticket.sku && <span className="fact">{ticket.sku}</span>}
                    {ticket.size && <span className="fact">size {ticket.size}</span>}
                    {ticket.qty !== null && <span className="fact">qty {ticket.qty}</span>}
                    {ticket.invoice_id !== null && <span className="fact">invoice #{ticket.invoice_id}</span>}
                    {ticket.lease_id !== null && <span className="fact">lease #{ticket.lease_id}</span>}
                    <span className={`fact fact--${ticket.status}`}>{ticket.status.replace('_', ' ')}</span>
                  </div>
                  <p className="brief__note">“{ticket.notes?.split('\n')[0]}”</p>
                </div>
                <div className="brief__cta">
                  <button
                    className={`go ${running ? 'is-running' : ''}`}
                    disabled={desk.busy || desk.online === false}
                    onClick={() => void desk.startRun(ticket.id)}
                  >
                    <span className="go__label">
                      {running ? `Team on it · ${elapsed}s` : run ? 'Run the team again' : 'Send to the team'}
                    </span>
                    <span className="go__arrow">{running ? '' : '→'}</span>
                  </button>
                  <span className="brief__hint">
                    {desk.busy && !running
                      ? 'The team is busy on another ticket.'
                      : 'The Boss reads it first, then calls only who it needs.'}
                  </span>
                </div>
              </div>

              <AgentFloor events={run?.events ?? []} running={running} />

              <div className="below">
                <LiveFeed events={run?.events ?? []} running={running} />
                {run?.detail && !running ? (
                  <RunSummary detail={run.detail} ticketId={ticket.id} pendingIds={desk.pending.map((p) => p.id)} />
                ) : (
                  <section className="summary summary--empty">
                    <div className="panel-head">
                      <span className="eyebrow">What happened</span>
                    </div>
                    <p>{running ? 'The summary appears here when the Boss signs off.' : 'No run yet for this ticket.'}</p>
                  </section>
                )}
              </div>
            </>
          ) : (
            <div className="stage__empty">Loading the queue…</div>
          )}
        </section>

        <ApprovalTray
          pending={desk.pending}
          history={desk.history}
          signer={signer}
          setSigner={setSigner}
          onDecide={(id, ok) => desk.decide(id, ok, signer.trim() || 'Owner')}
        />
      </main>
    </div>
  )
}
