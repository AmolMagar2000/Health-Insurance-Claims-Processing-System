import { useState } from 'react'

const DECISION_CONFIG = {
  APPROVED:      { cls: 'badge-green',  label: 'Approved',       icon: '✅', borderColor: '#16a34a' },
  PARTIAL:       { cls: 'badge-yellow', label: 'Partially Approved', icon: '🟡', borderColor: '#d97706' },
  REJECTED:      { cls: 'badge-red',    label: 'Rejected',       icon: '❌', borderColor: '#dc2626' },
  MANUAL_REVIEW: { cls: 'badge-purple', label: 'Manual Review',  icon: '🔍', borderColor: '#7c3aed' },
}

function Collapse({ title, icon, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div style={{ marginBottom: 10 }}>
      <button type="button" className="section-toggle" onClick={() => setOpen(o => !o)}>
        <span>{icon} {title}</span>
        <span style={{ color: 'var(--muted2)', fontSize: 11 }}>{open ? '▲' : '▼'}</span>
      </button>
      {open && <div className="section-body">{children}</div>}
    </div>
  )
}

function KV({ k, v, vStyle }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid var(--border2)', fontSize: 13 }}>
      <span style={{ color: 'var(--muted)' }}>{k}</span>
      <span style={{ fontWeight: 600, color: 'var(--text2)', ...vStyle }}>{v}</span>
    </div>
  )
}

function ConfBar({ score }) {
  const pct = Math.round(score * 100)
  const color = pct >= 80 ? 'var(--green)' : pct >= 55 ? 'var(--yellow)' : 'var(--red)'
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 13 }}>
        <span style={{ color: 'var(--muted)' }}>Confidence Score</span>
        <span style={{ fontWeight: 700, color }}>{pct}%</span>
      </div>
      <div className="conf-track">
        <div className="conf-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  )
}

export default function ResultDisplay({ result }) {
  const cfg = DECISION_CONFIG[result.decision] || DECISION_CONFIG.MANUAL_REVIEW
  const rejectReasons = result.rejection_reasons || []
  const fraudFlags    = result.fraud_flags || []
  const errors        = result.errors || []
  const lineItems     = result.line_item_decisions || []
  const trace         = result.trace_log || []

  // Parse pipeline steps from trace for the visual pipeline display
  const steps = [
    { name: 'Gatekeeper',    key: 'AGENT 1' },
    { name: 'Doc Quality',   key: 'AGENT 2' },
    { name: 'Extractor',     key: 'AGENT 3' },
    { name: 'Adjudicator',   key: 'AGENT 4' },
    { name: 'Auditor',       key: 'AGENT 5' },
  ].map(s => ({
    ...s,
    ran:     trace.some(l => l.includes(s.key)),
    ok:      trace.some(l => l.includes(s.key) && l.includes('✓')),
    failed:  trace.some(l => l.includes(s.key) && l.includes('✗')),
  }))

  return (
    <div className="card" style={{
      padding: 0, overflow: 'hidden',
      borderTop: `3px solid ${cfg.borderColor}`,
      maxHeight: '92vh', display: 'flex', flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border2)', background: 'var(--surface2)', flexShrink: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--text)' }}>Claim Decision</div>
            <div style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--mono)', marginTop: 4 }}>{result.claim_id}</div>
          </div>
          <span className={`badge ${cfg.cls}`} style={{ fontSize: 13 }}>
            {cfg.icon} {cfg.label}
          </span>
        </div>
      </div>

      {/* Scrollable content */}
      <div style={{ padding: '16px 20px', overflowY: 'auto', flex: 1 }}>

        {/* ── Pipeline visual ── */}
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 18, flexWrap: 'wrap' }}>
          {steps.map((s, i) => (
            <div key={s.name} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{
                padding: '4px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                background: !s.ran ? 'var(--surface2)' : s.failed ? 'var(--red-bg)' : 'var(--green-bg)',
                color:      !s.ran ? 'var(--muted2)'   : s.failed ? 'var(--red)'    : 'var(--green)',
                border: `1px solid ${!s.ran ? 'var(--border2)' : s.failed ? '#fecaca' : '#bbf7d0'}`,
              }}>
                {!s.ran ? '○' : s.failed ? '✗' : '✓'} {s.name}
              </div>
              {i < steps.length - 1 && <span style={{ color: 'var(--muted2)', fontSize: 12 }}>→</span>}
            </div>
          ))}
        </div>

        {/* ── Re-upload required ── */}
        {result.re_upload_required && (
          <div style={{ padding: '12px 16px', marginBottom: 14, background: 'var(--yellow-bg)', border: '1px solid #fde68a', borderRadius: 8 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--yellow)', marginBottom: 6 }}>📎 Re-upload Required</div>
            <div style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.6 }}>{result.re_upload_message}</div>
          </div>
        )}

        {/* ── Errors (early exit, doc mismatch) ── */}
        {errors.length > 0 && !result.re_upload_required && (
          <div style={{ padding: '12px 16px', marginBottom: 14, background: 'var(--red-bg)', border: '1px solid #fecaca', borderRadius: 8 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--red)', marginBottom: 8 }}>⚠ Issues Detected</div>
            {errors.map((e, i) => (
              <div key={i} style={{ fontSize: 13, color: 'var(--red)', lineHeight: 1.6, marginBottom: 4 }}>• {e}</div>
            ))}
          </div>
        )}

        {/* ── Financials ── */}
        {['APPROVED', 'PARTIAL'].includes(result.decision) && (
          <Collapse title="Financial Summary" icon="💰" defaultOpen>
            <KV k="Claimed Amount"  v={`₹${(result.claimed_amount || 0).toLocaleString()}`} />
            <KV k="Approved Amount" v={`₹${(result.approved_amount || 0).toLocaleString()}`} vStyle={{ color: cfg.borderColor, fontSize: 15 }} />
            <KV k="Member Deduction" v={`₹${((result.claimed_amount || 0) - (result.approved_amount || 0)).toLocaleString()}`} />
            <div style={{ marginTop: 14 }}><ConfBar score={result.confidence_score || 0} /></div>
          </Collapse>
        )}

        {/* ── Rejection ── */}
        {result.decision === 'REJECTED' && (
          <Collapse title="Rejection Details" icon="❌" defaultOpen>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
              {rejectReasons.map((r, i) => (
                <span key={i} className="badge badge-red">{r.replace(/_/g, ' ')}</span>
              ))}
            </div>
            {errors.map((e, i) => (
              <div key={i} style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.7, marginBottom: 6, paddingLeft: 8, borderLeft: '3px solid #fecaca' }}>
                {e}
              </div>
            ))}
            <div style={{ marginTop: 14 }}><ConfBar score={result.confidence_score || 0} /></div>
          </Collapse>
        )}

        {/* ── Manual review ── */}
        {result.decision === 'MANUAL_REVIEW' && (
          <Collapse title="Manual Review Required" icon="🔍" defaultOpen>
            <div style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 12, lineHeight: 1.7, padding: '10px 12px', background: 'var(--purple-bg)', borderRadius: 8, border: '1px solid #ddd6fe' }}>
              This claim has been flagged for human review. An operations team member will assess it within 24–48 hours.
            </div>
            {fraudFlags.map((f, i) => (
              <div key={i} style={{ fontSize: 13, padding: '8px 12px', background: 'var(--yellow-bg)', border: '1px solid #fde68a', borderRadius: 6, marginBottom: 6, color: 'var(--text2)' }}>
                🚩 {f}
              </div>
            ))}
            <div style={{ marginTop: 14 }}><ConfBar score={result.confidence_score || 0} /></div>
          </Collapse>
        )}

        {/* ── Line items ── */}
        {lineItems.length > 0 && (
          <Collapse title={`Line Item Breakdown (${lineItems.length} items)`} icon="📋" defaultOpen>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: 'var(--surface2)' }}>
                    {['Procedure', 'Amount', 'Status', 'Reason'].map(h => (
                      <th key={h} style={{ textAlign: 'left', padding: '6px 10px', color: 'var(--muted)', fontWeight: 600, borderBottom: '1px solid var(--border2)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {lineItems.map((item, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--border2)' }}>
                      <td style={{ padding: '7px 10px', color: 'var(--text)', fontWeight: 500 }}>{item.description}</td>
                      <td style={{ padding: '7px 10px', color: 'var(--text2)' }}>₹{(item.claimed_amount || 0).toLocaleString()}</td>
                      <td style={{ padding: '7px 10px' }}>
                        <span className={`badge ${item.status === 'APPROVED' ? 'badge-green' : 'badge-red'}`} style={{ fontSize: 11 }}>
                          {item.status}
                        </span>
                      </td>
                      <td style={{ padding: '7px 10px', color: 'var(--muted)', fontSize: 11.5 }}>{item.reason || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Collapse>
        )}

        {/* ── Fraud flags ── */}
        {fraudFlags.length > 0 && result.decision !== 'MANUAL_REVIEW' && (
          <Collapse title={`Fraud Signals (${fraudFlags.length})`} icon="🚩" defaultOpen={false}>
            {fraudFlags.map((f, i) => (
              <div key={i} style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 6 }}>🚩 {f}</div>
            ))}
          </Collapse>
        )}

        {/* ── Claim metadata ── */}
        <Collapse title="Claim Info" icon="ℹ" defaultOpen={false}>
          <KV k="Member ID"    v={result.member_id} />
          {result.member_info && <KV k="Member Name" v={result.member_info.name} />}
          <KV k="Category"     v={result.category} />
          <KV k="Treat. Date"  v={result.treatment_date} />
          <KV k="Policy"       v={result.policy_id} />
          {result.hospital_name && <KV k="Hospital" v={result.hospital_name} />}
        </Collapse>

        {/* ── Extracted data ── */}
        {result.extracted_data && Object.keys(result.extracted_data).length > 0 && (
          <Collapse title="Extracted Data" icon="🔬" defaultOpen={false}>
            <pre style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--text2)', lineHeight: 1.8, maxHeight: 240, overflowY: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
              {JSON.stringify(result.extracted_data, null, 2)}
            </pre>
          </Collapse>
        )}

        {/* ── Full trace ── */}
        <Collapse title={`Audit Trace (${trace.length} entries)`} icon="📜" defaultOpen={false}>
          <div style={{ maxHeight: 380, overflowY: 'auto' }}>
            {trace.map((line, i) => {
              const isHeader = line.startsWith('═') || line.startsWith('AGENT') || line.startsWith('FINAL') || line.startsWith('PIPELINE')
              const isOk   = line.includes('✓')
              const isBad  = line.includes('✗') || line.includes('⚠')
              const cls    = isHeader ? 'trace-header' : isOk ? 'trace-ok' : isBad ? 'trace-warn' : 'trace-muted'
              return (
                <div key={i} className={`trace-line ${cls}`} style={{ paddingLeft: line.startsWith('  ') ? 14 : 0 }}>
                  {line}
                </div>
              )
            })}
          </div>
        </Collapse>
      </div>
    </div>
  )
}
