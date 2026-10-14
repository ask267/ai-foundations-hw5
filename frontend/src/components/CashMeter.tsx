// Big checking-balance counter that rolls down when a payment is approved.
import { useEffect, useRef, useState } from 'react'
import type { Cash } from '../api'
import { fmtMoney } from '../agents'

function useTween(target: number | null, ms = 1400) {
  const [value, setValue] = useState(target ?? 0)
  const from = useRef(target ?? 0)
  useEffect(() => {
    if (target === null) return
    const start = performance.now()
    const a = from.current
    let raf = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms)
      const eased = 1 - Math.pow(1 - t, 4)
      setValue(a + (target - a) * eased)
      if (t < 1) raf = requestAnimationFrame(tick)
      else from.current = target
    }
    raf = requestAnimationFrame(tick)
    // Background tabs pause requestAnimationFrame; always land on the real number.
    const settle = window.setTimeout(() => {
      setValue(target)
      from.current = target
    }, ms + 60)
    return () => {
      cancelAnimationFrame(raf)
      window.clearTimeout(settle)
    }
  }, [target, ms])
  return value
}

export function CashMeter({ cash }: { cash: Cash | null }) {
  const balance = cash?.balance ?? null
  const shown = useTween(balance)
  const prev = useRef<number | null>(null)
  const [drop, setDrop] = useState<{ amount: number; key: number } | null>(null)

  useEffect(() => {
    if (balance === null) return
    if (prev.current !== null && balance < prev.current) {
      setDrop({ amount: prev.current - balance, key: Date.now() })
    }
    prev.current = balance
  }, [balance])

  return (
    <div className="cash">
      <div className="cash__label">
        Checking <span className="cash__asof">as of {cash?.as_of ?? '—'}</span>
      </div>
      <div className="cash__value" aria-live="polite" key={`v-${drop?.key ?? 0}`} data-dropped={drop ? 'yes' : 'no'}>
        {balance === null ? '—' : fmtMoney(shown)}
      </div>
      {drop && (
        <div className="cash__drop" key={drop.key}>
          −{fmtMoney(drop.amount)}
        </div>
      )}
      <div className="cash__pending">
        {cash && cash.pending_requests_total > 0 ? (
          <>
            {fmtMoney(cash.pending_requests_total)} awaiting your signature →{' '}
            <b>{fmtMoney(cash.balance_if_all_approved)}</b> after
          </>
        ) : (
          'nothing waiting for your signature'
        )}
      </div>
    </div>
  )
}
