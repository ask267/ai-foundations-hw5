// All server state for the desk: tickets, cash, approvals, and live team runs.
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type AuditEvent, type Cash, type PaymentRequest, type RunDetail, type Ticket } from './api'

export interface TicketRun {
  runId: string
  status: 'running' | 'completed' | 'usage_limit' | 'error'
  events: AuditEvent[]
  cursor: number
  detail: RunDetail | null
  startedAt: number
}

const eventKey = (e: AuditEvent) => e.index ?? `${e.time}|${e.event}|${e.agent}|${e.tool ?? e.teammate ?? ''}`

const REFRESH_MS = 4000
const LIVE_MS = 1100

export function useDesk() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [pending, setPending] = useState<PaymentRequest[]>([])
  const [history, setHistory] = useState<PaymentRequest[]>([])
  const [online, setOnline] = useState<boolean | null>(null)
  const [shopDate, setShopDate] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [runs, setRuns] = useState<Record<number, TicketRun>>({})
  const runsRef = useRef(runs)
  runsRef.current = runs

  const refresh = useCallback(async () => {
    try {
      const [hl, t, c, p, h] = await Promise.all([
        api.health(),
        api.tickets(),
        api.cash(),
        api.payments('pending'),
        api.payments('all'),
      ])
      setShopDate(hl.shop_date)
      setTickets(t)
      setCash(c)
      setPending(p.requests)
      setHistory(h.requests.filter((r) => r.status !== 'pending'))
      setOnline(true)
    } catch (e) {
      setOnline(false)
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void refresh()
    const id = window.setInterval(refresh, REFRESH_MS)
    return () => window.clearInterval(id)
  }, [refresh])

  // Bring back the last finished run for a ticket (e.g. after a page reload).
  const loadRun = useCallback(async (ticketId: number, runId: string) => {
    if (runsRef.current[ticketId]?.runId === runId) return
    try {
      const detail = await api.run(runId)
      const status = detail.run?.status ?? 'completed'
      setRuns((r) =>
        r[ticketId]?.runId === runId
          ? r // the live poller already owns this run
          : {
              ...r,
              [ticketId]: {
                runId,
                status,
                events: detail.events,
                cursor: Math.max(0, ...detail.events.map((e) => (e.index ?? -1) + 1)),
                detail: status === 'running' ? null : detail,
                startedAt: Date.now(),
              },
            },
      )
    } catch {
      /* run not kept by the server any more */
    }
  }, [])

  const startRun = useCallback(async (ticketId: number) => {
    setError(null)
    try {
      const state = await api.runTicket(ticketId)
      setRuns((r) => ({
        ...r,
        [ticketId]: { runId: state.run_id, status: 'running', events: [], cursor: 0, detail: null, startedAt: Date.now() },
      }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  // Live polling for every running run.
  useEffect(() => {
    const id = window.setInterval(async () => {
      const live = Object.entries(runsRef.current).filter(([, r]) => r.status === 'running')
      for (const [tid, r] of live) {
        try {
          const ev = await api.events(r.runId, r.cursor)
          const end = ev.events.find((e) => e.event === 'run_end')
          let detail: RunDetail | null = null
          if (end) detail = await api.run(r.runId)
          setRuns((all) => {
            const cur = all[Number(tid)]
            if (!cur || cur.runId !== r.runId) return all
            const seen = new Set(cur.events.map(eventKey))
            const fresh = ev.events.filter((e) => !seen.has(eventKey(e)))
            return {
              ...all,
              [tid]: {
                ...cur,
                events: [...cur.events, ...fresh],
                cursor: ev.next_since,
                status: detail ? detail.run?.status ?? (end?.stop_reason as TicketRun['status']) ?? 'completed' : cur.status,
                detail: detail ?? cur.detail,
              },
            }
          })
          if (detail) void refresh()
        } catch {
          /* keep polling */
        }
      }
    }, LIVE_MS)
    return () => window.clearInterval(id)
  }, [refresh])

  const decide = useCallback(
    async (id: number, approve: boolean, by: string) => {
      setError(null)
      try {
        if (approve) await api.approve(id, by)
        else await api.reject(id, by)
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      }
      await refresh()
    },
    [refresh],
  )

  const reset = useCallback(async () => {
    setError(null)
    try {
      await api.reset()
      setRuns({})
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    await refresh()
  }, [refresh])

  const busy = Object.values(runs).some((r) => r.status === 'running')

  return { shopDate, tickets, cash, pending, history, online, error, setError, runs, busy, startRun, loadRun, decide, reset, refresh }
}
