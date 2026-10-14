// Left rail: the three tickets as physical ticket stubs with rubber stamps.
import type { Ticket } from '../api'
import { TICKET_TYPE_LABEL } from '../agents'
import type { TicketRun } from '../useDesk'

const STAMP: Record<string, string> = {
  resolved: 'Resolved',
  waiting: 'Waiting',
  escalated: 'Escalated',
  in_progress: 'In progress',
}

export function TicketRail({
  tickets,
  selected,
  runs,
  onSelect,
}: {
  tickets: Ticket[]
  selected: number | null
  runs: Record<number, TicketRun>
  onSelect: (id: number) => void
}) {
  return (
    <aside className="rail">
      <div className="rail__head">
        <span className="eyebrow">The queue</span>
        <span className="rail__count">
          {tickets.filter((t) => t.state === 'resolved').length}/{tickets.length} resolved
        </span>
      </div>
      {tickets.map((t, i) => {
        const run = runs[t.id]
        const live = run?.status === 'running'
        return (
          <button
            key={t.id}
            className={`stub ${selected === t.id ? 'is-selected' : ''} is-${t.status} ${live ? 'is-live' : ''}`}
            style={{ ['--i' as string]: i }}
            onClick={() => onSelect(t.id)}
          >
            <div className="stub__top">
              <span className="stub__no">#{t.id}</span>
              <span className="stub__type">{TICKET_TYPE_LABEL[t.type] ?? t.type}</span>
            </div>
            <div className="stub__subject">{t.subject}</div>
            <div className="stub__from">from {t.requester}</div>
            <div className="stub__perf" />
            <div className="stub__foot">
              {live ? (
                <span className="pill pill--live"><i /> team working</span>
              ) : (
                <span className={`pill pill--${t.status}`}>{t.status.replace('_', ' ')}</span>
              )}
              {t.pending_requests.length > 0 && (
                <span className="pill pill--sign">✍ {t.pending_requests.length} to sign</span>
              )}
            </div>
            {STAMP[t.status] && t.status !== 'in_progress' && (
              <span className={`stamp stamp--${t.status}`}>{STAMP[t.status]}</span>
            )}
          </button>
        )
      })}
      {tickets.length === 0 && <div className="rail__empty">No tickets yet…</div>}
    </aside>
  )
}
