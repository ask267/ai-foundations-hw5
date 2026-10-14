// The desk floor: the Boss up top, four specialists below, live delegation
// threads between them, and a speech bubble with what each agent is doing.
import type { AgentName, AuditEvent } from '../api'
import { AGENTS, SPECIALISTS, isAgent, shorten, toolPhrase } from '../agents'
import { Avatar, type Mood } from './Avatar'

export interface AgentLive {
  mood: Mood
  line: string | null
  calls: number
  tools: Record<string, number>
}

export interface Thread {
  from: AgentName
  to: AgentName
  open: boolean // asked but not answered yet
}

export function deriveFloor(events: AuditEvent[]) {
  const live = {} as Record<AgentName, AgentLive>
  const depth = {} as Record<AgentName, number>
  for (const name of Object.keys(AGENTS) as AgentName[]) {
    live[name] = { mood: 'idle', line: null, calls: 0, tools: {} }
    depth[name] = 0
  }
  const threads = new Map<string, Thread>()

  for (const e of events) {
    if (!isAgent(e.agent)) continue
    const a = live[e.agent]
    switch (e.event) {
      case 'agent_start':
        depth[e.agent] += 1
        a.mood = 'working'
        a.calls += 1
        a.line = 'reading the task…'
        break
      case 'tool_call':
        a.tools[e.tool ?? '?'] = (a.tools[e.tool ?? '?'] ?? 0) + 1
        a.line = `${toolPhrase(e.tool ?? '', e.args)}…`
        break
      case 'model_step':
        if (e.text) a.line = shorten(e.text, 150)
        break
      case 'delegate_call':
        if (e.teammate && isAgent(e.teammate)) {
          threads.set(`${e.agent}>${e.teammate}`, { from: e.agent, to: e.teammate, open: true })
          a.line = `asking ${AGENTS[e.teammate].label}…`
        }
        break
      case 'delegate_result':
        if (e.teammate && isAgent(e.teammate)) {
          const t = threads.get(`${e.agent}>${e.teammate}`)
          if (t) t.open = false
          a.line = `heard back from ${AGENTS[e.teammate].label}`
        }
        break
      case 'guard_block':
        a.line = `🚫 ${shorten(e.reason ?? 'blocked', 120)}`
        break
      case 'agent_end':
        depth[e.agent] = Math.max(0, depth[e.agent] - 1)
        if (depth[e.agent] === 0) {
          a.mood = e.stop_reason === 'completed' ? 'done' : 'blocked'
          a.line = e.summary ? shorten(e.summary, 170) : e.error ?? 'stopped'
        }
        break
    }
  }
  return { live, threads: [...threads.values()] }
}

// Station positions on a 100×100 board (x = centre, y = top of the station).
const POS: Record<AgentName, { x: number; y: number }> = {
  Boss: { x: 50, y: 4 },
  Inventory: { x: 12.5, y: 50 },
  Accounting: { x: 37.5, y: 50 },
  Facilities: { x: 62.5, y: 50 },
  CustomerService: { x: 87.5, y: 50 },
}
const BOSS_OUT = 22 // just under the Boss's avatar
const SPEC_IN = 50 // top of a specialist's avatar
const SPEC_MID = 62 // middle of a specialist's avatar

function threadPath(t: Thread) {
  const a = POS[t.from]
  const b = POS[t.to]
  if (t.from !== 'Boss' && t.to !== 'Boss') {
    // specialist ↔ specialist: a low arc between the two avatars
    const mx = (a.x + b.x) / 2
    return `M ${a.x} ${SPEC_MID} Q ${mx} ${SPEC_MID - 16} ${b.x} ${SPEC_MID}`
  }
  const [top, bottom] = t.from === 'Boss' ? [a, b] : [b, a]
  const my = (BOSS_OUT + SPEC_IN) / 2
  return `M ${top.x} ${BOSS_OUT} C ${top.x} ${my}, ${bottom.x} ${my}, ${bottom.x} ${SPEC_IN}`
}

export function AgentFloor({ events, running }: { events: AuditEvent[]; running: boolean }) {
  const { live, threads } = deriveFloor(events)
  const idleAll = events.length === 0

  return (
    <div className={`floor ${running ? 'is-running' : ''}`}>
      <svg className="floor__threads" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
        {SPECIALISTS.map((s) => (
          <path key={s} className="thread thread--ghost" d={threadPath({ from: 'Boss', to: s, open: false })} />
        ))}
        {threads.map((t) => (
          <path
            key={`${t.from}-${t.to}`}
            className={`thread ${t.open ? 'thread--open' : 'thread--done'}`}
            d={threadPath(t)}
            style={{ ['--hue' as string]: AGENTS[t.to].hue }}
          />
        ))}
      </svg>

      {(Object.keys(POS) as AgentName[]).map((name) => {
        const meta = AGENTS[name]
        const a = live[name]
        const p = POS[name]
        const benched = !idleAll && !running && a.calls === 0
        return (
          <div
            key={name}
            className={`station station--${meta.voice} is-${a.mood} ${benched ? 'is-benched' : ''} ${name === 'Boss' ? 'station--boss' : ''}`}
            style={{ left: `${p.x}%`, top: `${p.y}%`, ['--hue' as string]: meta.hue }}
          >
            <Avatar agent={name} mood={a.mood} size={name === 'Boss' ? 74 : 60} />
            <div className="station__name">
              <span className="station__glyph">{meta.emoji}</span> {meta.label}
              {a.calls > 1 && <span className="station__x">×{a.calls}</span>}
            </div>
            <div className="station__role">{meta.role}</div>
            <div className={`bubble bubble--${meta.voice} ${a.line ? '' : 'bubble--quiet'}`}>
              {a.line ?? (benched ? 'not needed on this one' : idleAll ? 'waiting for a ticket' : '…')}
            </div>
          </div>
        )
      })}
    </div>
  )
}
