// A scrolling, human-readable log of the run (built from audit events).
import { useEffect, useRef } from 'react'
import type { AuditEvent } from '../api'
import { AGENTS, feedLine, isAgent } from '../agents'

export function LiveFeed({ events, running }: { events: AuditEvent[]; running: boolean }) {
  const lines = events.map(feedLine).filter((l) => l !== null)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [lines.length])

  return (
    <section className="feed">
      <div className="panel-head">
        <span className="eyebrow">Live wire</span>
        {running && <span className="pill pill--live"><i /> streaming</span>}
      </div>
      <div className="feed__list">
        {lines.length === 0 && <div className="feed__empty">Pick a ticket and send it to the team. Every step shows up here.</div>}
        {lines.map((l) => {
          const hue = isAgent(l.agent) ? AGENTS[l.agent].hue : '#888'
          return (
            <div key={l.key} className={`line line--${l.kind} ${l.ok === false ? 'line--bad' : ''}`} style={{ ['--hue' as string]: hue }}>
              <span className="line__time">{new Date(l.time).toLocaleTimeString([], { minute: '2-digit', second: '2-digit' })}</span>
              <span className="line__who">{isAgent(l.agent) ? AGENTS[l.agent].label : l.agent}</span>
              <span className="line__text">{l.text}</span>
            </div>
          )
        })}
        <div ref={end} />
      </div>
    </section>
  )
}
