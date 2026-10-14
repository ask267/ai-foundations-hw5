// After a run: the Boss's verdict, one card per agent saying what it did,
// the customer draft (as a postcard), and the run's cost.
import type { AgentName, RunDetail } from '../api'
import { AGENTS, shorten, toolPhrase } from '../agents'
import { Avatar } from './Avatar'

/** "approve request #2" is done once request 2 is no longer pending. */
function isDone(item: string, pendingIds: number[]) {
  const m = item.match(/request\s*#?(\d+)/i)
  return m ? !pendingIds.includes(Number(m[1])) : false
}

export function RunSummary({ detail, ticketId, pendingIds }: { detail: RunDetail; ticketId: number; pendingIds: number[] }) {
  const result = detail.run?.result
  const outcome = result?.output?.tickets?.find((t) => t.ticket_id === ticketId) ?? result?.output?.tickets?.[0]
  const agents = (Object.keys(AGENTS) as AgentName[]).filter((a) => detail.by_agent[a])
  const customer = outcome?.customer_message ?? result?.output?.customer_message

  return (
    <section className="summary">
      <div className="panel-head">
        <span className="eyebrow">What happened</span>
        {result && (
          <span className="summary__cost">
            {result.usage.total_tokens.toLocaleString()} tokens · {result.usage.requests} model calls ·{' '}
            {result.delegations} hand-offs · {result.duration_s.toFixed(0)}s
          </span>
        )}
      </div>

      {result?.stop_reason !== 'completed' && result && (
        <div className="summary__warn">Run stopped early ({result.stop_reason}). {result.error}</div>
      )}

      {outcome && (
        <blockquote className="verdict">
          <span className="verdict__status">ticket #{outcome.ticket_id} → {outcome.status}</span>
          “{outcome.summary}”
          <cite>— The Boss</cite>
        </blockquote>
      )}

      <div className="did">
        {agents.map((name) => {
          const d = detail.by_agent[name]!
          const meta = AGENTS[name]
          const last = d.said[d.said.length - 1]
          return (
            <article key={name} className={`did__card did__card--${meta.voice}`} style={{ ['--hue' as string]: meta.hue }}>
              <header>
                <Avatar agent={name} mood="done" size={40} />
                <div>
                  <h4>{meta.label}</h4>
                  <span>{d.steps} steps</span>
                </div>
              </header>
              <p>{last ? shorten(last, 260) : 'No summary.'}</p>
              <div className="chips">
                {Object.entries(d.tools).map(([tool, n]) => (
                  <span key={tool} className="chip" title={toolPhrase(tool)}>
                    {tool}
                    {n > 1 ? ` ×${n}` : ''}
                  </span>
                ))}
                {Object.entries(d.asked).map(([who, n]) => (
                  <span key={who} className="chip chip--ask">
                    → {AGENTS[who as AgentName]?.label ?? who}
                    {n > 1 ? ` ×${n}` : ''}
                  </span>
                ))}
              </div>
            </article>
          )
        })}
      </div>

      {(outcome?.needs_human?.length ?? 0) > 0 && (
        <div className="todo">
          <div className="eyebrow">Left for a human</div>
          <ul>
            {outcome!.needs_human.map((n, i) => (
              <li key={i} className={isDone(n, pendingIds) ? 'is-done' : ''}>
                {n}
                {isDone(n, pendingIds) && <span className="todo__done"> ✓ decided</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {customer && (
        <div className="postcard">
          <div className="postcard__stamp">CC</div>
          <div className="eyebrow">Draft reply · a human sends this</div>
          <p>{customer}</p>
        </div>
      )}

      {outcome?.actions && outcome.actions.length > 0 && (
        <div className="actions-list">
          <div className="eyebrow">Changes made</div>
          {outcome.actions.map((a, i) => (
            <div key={i} className="action">
              <code>{a.tool}</code> {a.summary}
            </div>
          ))}
        </div>
      )}

      {result && (
        <div className="summary__foot">
          gpt-6-luna · run {result.run_id} · every step is in output/audit_trail.json
        </div>
      )}
    </section>
  )
}
