// Typed client for the Campus Customs Desk API (backend/main.py).

export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

export type AgentName = 'Boss' | 'Inventory' | 'Accounting' | 'Facilities' | 'CustomerService'
export type TicketStatus = 'open' | 'in_progress' | 'waiting' | 'resolved' | 'escalated'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: TicketStatus
  notes: string | null
  created_at: string
  state: 'open' | 'resolved'
  pending_requests: number[]
  last_run_id: string | null
}

export interface Cash {
  account: string
  balance: number
  as_of: string
  pending_requests_total: number
  balance_if_all_approved: number
}

export interface PaymentRequest {
  id: number
  kind: 'invoice' | 'rent' | 'purchase'
  ref_id: number | null
  vendor_id: number | null
  sku: string | null
  size: string | null
  qty: number | null
  amount: number
  account: string
  ticket_id: number | null
  reason: string
  resolves_ticket: number
  status: 'pending' | 'approved' | 'rejected'
  prepared_by: string
  prepared_at: string
  decided_by: string | null
  decided_at: string | null
  decision_note: string | null
  payment_id: number | null
}

export interface AuditEvent {
  index?: number
  time: string
  event: string
  run_id: string | null
  agent: string
  depth?: number
  chain?: string[]
  tool?: string
  args?: string
  ok?: boolean
  result?: string
  teammate?: string
  task?: string
  summary?: string
  text?: string | null
  reason?: string
  step?: number
  stop_reason?: string
  error?: string | null
  tool_calls?: { tool: string; args: string }[]
  input_tokens?: number
  output_tokens?: number
}

export interface AgentDigest {
  said: string[]
  tools: Record<string, number>
  asked: Record<string, number>
  steps: number
}

export interface ActionTaken { tool: string; summary: string }

export interface TicketOutcome {
  ticket_id: number
  status: TicketStatus
  summary: string
  handled_by: AgentName[]
  actions: ActionTaken[]
  needs_human: string[]
  customer_message?: string | null
  payment_requests?: number[]
}

export interface TeamOutput {
  summary: string
  tickets?: TicketOutcome[]
  needs_human: string[]
  customer_message?: string | null
}

export interface TeamRunResult {
  run_id: string
  stop_reason: 'completed' | 'usage_limit' | 'error'
  error?: string | null
  output: TeamOutput | null
  usage: { requests: number; tool_calls: number; input_tokens: number; output_tokens: number; total_tokens: number }
  delegations: number
  duration_s: number
}

export interface RunState {
  run_id: string
  ticket_id: number
  task: string
  status: 'running' | 'completed' | 'usage_limit' | 'error'
  started_at: string
  finished_at: string | null
  result: TeamRunResult | null
}

export interface RunDetail {
  run: RunState | null
  by_agent: Partial<Record<AgentName, AgentDigest>>
  events: AuditEvent[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* not JSON */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<{ ok: boolean; model: string; shop_date: string | null; team_busy: boolean }>('/api/health'),
  tickets: () => request<Ticket[]>('/api/tickets'),
  cash: () => request<Cash>('/api/cash'),
  payments: (status = 'pending') =>
    request<{ count: number; requests: PaymentRequest[] }>(`/api/payments?status=${status}`),
  runTicket: (id: number) => request<RunState>(`/api/tickets/${id}/run`, { method: 'POST', body: '{}' }),
  run: (runId: string) => request<RunDetail>(`/api/runs/${runId}`),
  events: (runId: string, since: number) =>
    request<{ events: AuditEvent[]; next_since: number; team_busy: boolean }>(
      `/api/events?run_id=${runId}&since=${since}&limit=500`,
    ),
  approve: (id: number, by: string) =>
    request<Record<string, unknown>>(`/api/payments/${id}/approve`, { method: 'POST', body: JSON.stringify({ by }) }),
  reject: (id: number, by: string, note = '') =>
    request<Record<string, unknown>>(`/api/payments/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ by, note }),
    }),
  reset: () => request<{ ok: boolean }>('/api/reset', { method: 'POST' }),
}
