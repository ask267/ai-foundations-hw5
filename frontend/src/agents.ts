// Who's who on the desk, and how to turn raw audit events into plain English.
import type { AgentName, AuditEvent } from './api'

export interface AgentMeta {
  name: AgentName
  label: string
  role: string
  voice: 'boss' | 'ledger' | 'count' | 'blueprint' | 'warm'
  hue: string // accent color for the station
  emoji: string // small glyph on the badge
}

export const AGENTS: Record<AgentName, AgentMeta> = {
  Boss: { name: 'Boss', label: 'The Boss', role: 'routes the work · sets status', voice: 'boss', hue: '#ff4fa3', emoji: '♛' },
  Inventory: { name: 'Inventory', label: 'Inventory', role: 'stock · sizes · restocks', voice: 'count', hue: '#ff9bd0', emoji: '▦' },
  Accounting: { name: 'Accounting', label: 'Accounting', role: 'cash · bills · prepares pay', voice: 'ledger', hue: '#ffc3a1', emoji: '$' },
  Facilities: { name: 'Facilities', label: 'Facilities', role: 'lease · landlord · couriers', voice: 'blueprint', hue: '#c9a7ff', emoji: '⌂' },
  CustomerService: { name: 'CustomerService', label: 'Customer Service', role: 'drafts replies to people', voice: 'warm', hue: '#ffd9ec', emoji: '✉' },
}

export const SPECIALISTS: AgentName[] = ['Inventory', 'Accounting', 'Facilities', 'CustomerService']
export const isAgent = (a: string): a is AgentName => a in AGENTS

function parseArgs(raw?: string): Record<string, unknown> {
  if (!raw) return {}
  try {
    return JSON.parse(raw)
  } catch {
    // The audit log cuts long args (e.g. a long note) mid-JSON; recover the
    // simple "key":value pairs that came before the cut.
    const out: Record<string, unknown> = {}
    for (const m of raw.matchAll(/"(\w+)":\s*("([^"\\]*)"|-?\d+(?:\.\d+)?|true|false)/g)) {
      out[m[1]] = m[3] ?? (m[2] === 'true' ? true : m[2] === 'false' ? false : Number(m[2]))
    }
    return out
  }
}

const money = (n: unknown) =>
  typeof n === 'number' ? `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '$?'

/** "counting CC-TEE-WHITE size S…" — a human sentence for one MCP tool call. */
export function toolPhrase(tool: string, rawArgs?: string): string {
  const a = parseArgs(rawArgs)
  switch (tool) {
    case 'get_ticket': return `reading ticket #${a.ticket_id ?? ''}`
    case 'list_tickets': return 'reading the ticket queue'
    case 'get_shop_date': return 'checking the desk calendar'
    case 'check_stock': return `counting ${a.sku ?? ''} size ${a.size ?? ''}${a.qty_needed ? ` (need ${a.qty_needed})` : ''}`
    case 'get_pricing': return `pulling the price sheet for ${a.sku ?? ''}`
    case 'quote_discount': return `pricing ${a.discount_pct ?? '?'}% off × ${a.qty ?? '?'}`
    case 'get_rent_due': return `checking lease #${a.lease_id ?? ''} against the notice`
    case 'get_invoice': return `opening invoice #${a.invoice_id ?? ''}`
    case 'list_vendors': return 'flipping through the vendor list'
    case 'get_cash_balance': return 'checking the bank balance'
    case 'list_payments': return 'scanning past payments'
    case 'list_payment_requests': return 'checking the approval tray'
    case 'prepare_payment': return `preparing ${a.kind ?? ''} payment ${money(a.amount)} for your signature`
    case 'prepare_purchase': return `preparing a purchase: ${a.qty ?? ''} × ${a.sku ?? ''} ${a.size ?? ''}`
    case 'update_ticket': return `marking ticket #${a.ticket_id ?? ''} ${a.status ?? ''}`
    case 'adjust_inventory': return `moving stock ${a.sku ?? ''} ${a.size ?? ''} by ${a.delta ?? ''}`
    case 'ask_teammate': return `asking ${a.teammate ?? 'a teammate'}`
    case 'final_result': return 'writing up the report'
    default: return tool.replaceAll('_', ' ')
  }
}

export interface FeedLine {
  key: string
  time: string
  agent: string
  kind: 'start' | 'tool' | 'result' | 'ask' | 'answer' | 'say' | 'done' | 'block' | 'refused' | 'run'
  text: string
  ok?: boolean
}

/** One readable feed line per interesting audit event (null = skip). */
export function feedLine(e: AuditEvent): FeedLine | null {
  const key = `${e.index ?? e.time}-${e.event}-${e.agent}-${e.tool ?? e.teammate ?? ''}`
  const base = { key, time: e.time, agent: e.agent }
  switch (e.event) {
    case 'run_start': return { ...base, kind: 'run', text: 'Ticket handed to the team' }
    case 'agent_start': return e.depth ? { ...base, kind: 'start', text: 'picks up the task' } : null
    case 'tool_call': return { ...base, kind: 'tool', text: toolPhrase(e.tool ?? '', e.args) }
    case 'tool_result':
      return e.ok === false ? { ...base, kind: 'result', ok: false, text: `${e.tool} said no: ${shorten(e.result ?? '', 120)}` } : null
    case 'delegate_call': return { ...base, kind: 'ask', text: `→ ${e.teammate}: ${shorten(e.task ?? '', 150)}` }
    case 'delegate_refused': return { ...base, kind: 'refused', text: `can't ask ${e.teammate}: ${e.reason}` }
    case 'model_step': return e.text ? { ...base, kind: 'say', text: shorten(e.text, 180) } : null
    case 'agent_end':
      return e.stop_reason === 'completed'
        ? { ...base, kind: 'done', text: shorten(e.summary ?? 'done', 220) }
        : { ...base, kind: 'block', ok: false, text: `stopped: ${e.stop_reason} ${e.error ?? ''}` }
    case 'guard_block': return { ...base, kind: 'block', ok: false, text: `blocked by the harness: ${e.reason}` }
    case 'run_end': return { ...base, kind: 'run', text: `Run finished (${e.stop_reason})` }
    default: return null
  }
}

export function shorten(s: string, n: number) {
  const t = s.replace(/\s+/g, ' ').trim()
  return t.length > n ? `${t.slice(0, n - 1)}…` : t
}

export const fmtMoney = (n: number) =>
  `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export const TICKET_TYPE_LABEL: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price override',
}
