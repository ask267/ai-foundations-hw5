// Right column: payments the agents prepared, shown as checks waiting for a
// human signature, plus a receipt tape of what's been approved or rejected.
import { useState } from 'react'
import type { PaymentRequest } from '../api'
import { fmtMoney } from '../agents'

function payee(r: PaymentRequest) {
  if (r.kind === 'invoice') return `Vendor invoice #${r.ref_id}`
  if (r.kind === 'rent') return `Rent · lease #${r.ref_id}`
  return `Purchase · ${r.qty} × ${r.sku} ${r.size}`
}

export function ApprovalTray({
  pending,
  history,
  signer,
  setSigner,
  onDecide,
}: {
  pending: PaymentRequest[]
  history: PaymentRequest[]
  signer: string
  setSigner: (s: string) => void
  onDecide: (id: number, approve: boolean) => Promise<void>
}) {
  const [busy, setBusy] = useState<number | null>(null)
  const [signed, setSigned] = useState<number | null>(null)

  async function decide(id: number, approve: boolean) {
    setBusy(id)
    if (approve) {
      // Let the signature write itself across the line before the check clears.
      setSigned(id)
      await new Promise((r) => window.setTimeout(r, 1100))
    }
    await onDecide(id, approve)
    setBusy(null)
    window.setTimeout(() => setSigned(null), 900)
  }

  return (
    <aside className="tray">
      <div className="panel-head">
        <span className="eyebrow">Needs your signature</span>
        <span className="tray__count">{pending.length}</span>
      </div>

      <label className="signer">
        <span>Signing as</span>
        <input value={signer} onChange={(e) => setSigner(e.target.value)} maxLength={40} />
      </label>

      {pending.length === 0 && (
        <div className="tray__empty">
          <div className="tray__empty-pen">✒︎</div>
          No checks to sign. Agents can only <em>prepare</em> payments; when they do, they land here.
        </div>
      )}

      {pending.map((r) => (
        <div key={r.id} className={`check ${signed === r.id ? 'is-signing' : ''}`}>
          <div className="check__top">
            <span className="check__bank">Campus Customs · {r.account}</span>
            <span className="check__no">No. {String(r.id).padStart(4, '0')}</span>
          </div>
          <div className="check__payee">
            <span>Pay to</span> {payee(r)}
          </div>
          <div className="check__amount">{fmtMoney(r.amount)}</div>
          <div className="check__memo">
            <span>Memo</span> {r.reason}
          </div>
          <div className="check__meta">
            prepared by <b>{r.prepared_by}</b>
            {r.ticket_id ? <> · ticket #{r.ticket_id}</> : null}
          </div>
          <div className="check__sig">
            <div className="check__line">{signed === r.id ? <span className="check__ink">{signer}</span> : null}</div>
            <div className="check__actions">
              <button className="btn btn--ghost" disabled={busy !== null || !signer.trim()} onClick={() => decide(r.id, false)}>
                Reject
              </button>
              <button className="btn btn--pink" disabled={busy !== null || !signer.trim()} onClick={() => decide(r.id, true)}>
                {busy === r.id ? 'Paying…' : 'Approve & pay'}
              </button>
            </div>
          </div>
        </div>
      ))}

      {history.length > 0 && (
        <div className="receipts">
          <div className="eyebrow">Receipt tape</div>
          {history.map((r) => (
            <div key={r.id} className={`receipt receipt--${r.status}`}>
              <span className="receipt__what">{payee(r)}</span>
              <span className="receipt__amt">{r.status === 'approved' ? `−${fmtMoney(r.amount)}` : 'void'}</span>
              <span className="receipt__who">
                {r.status} by {r.decided_by}
              </span>
            </div>
          ))}
        </div>
      )}
    </aside>
  )
}
