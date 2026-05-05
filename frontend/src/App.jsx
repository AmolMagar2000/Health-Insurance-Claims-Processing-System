import { useState, useEffect } from 'react'
import ClaimForm from './components/ClaimForm.jsx'
import ResultDisplay from './components/ResultDisplay.jsx'
import UploadMode from './components/UploadMode.jsx'

const API = 'http://localhost:8000'

export default function App() {
  const [page, setPage]           = useState('form')
  const [result, setResult]       = useState(null)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState(null)
  const [testCases, setTestCases] = useState([])
  const [members, setMembers]     = useState([])
  const [stats, setStats]         = useState({ total: 0, approved: 0, manual: 0, rejected: 0 })

  useEffect(() => {
    fetch(`${API}/test-cases`).then(r => r.json()).then(d => setTestCases(d.test_cases || [])).catch(() => {})
    fetch(`${API}/members`).then(r => r.json()).then(d => setMembers(d.members || [])).catch(() => {})
  }, [])

  async function handleSubmit(payload) {
    setLoading(true); setError(null); setResult(null)
    try {
      const res = await fetch(`${API}/submit-claim`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail || `HTTP ${res.status}`) }
      const data = await res.json()
      setResult(data)
      setStats(s => ({
        total:    s.total + 1,
        approved: s.approved + (['APPROVED', 'PARTIAL'].includes(data.decision) ? 1 : 0),
        manual:   s.manual   + (data.decision === 'MANUAL_REVIEW' ? 1 : 0),
        rejected: s.rejected + (data.decision === 'REJECTED' ? 1 : 0),
      }))
    } catch(e) { setError(e.message) }
    finally { setLoading(false) }
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>

      {/* ── Sidebar ── */}
      <aside style={{
        width: 240, minHeight: '100vh', flexShrink: 0,
        background: 'var(--sidebar)', borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column',
        position: 'sticky', top: 0, height: '100vh', overflowY: 'auto',
      }}>
        {/* Logo */}
        <div style={{ padding: '20px 18px 16px', borderBottom: '1px solid var(--border2)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 38, height: 38, borderRadius: 10, fontWeight: 800, fontSize: 18,
              background: 'linear-gradient(135deg,#d97706 0%,#f59e0b 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#fff', boxShadow: '0 2px 8px rgba(217,119,6,.35)',
            }}>P</div>
            <div>
              <div style={{ fontWeight: 800, fontSize: 15.5, color: 'var(--text)', lineHeight: 1 }}>Plum Claims</div>
              <div style={{ fontSize: 10, color: 'var(--muted)', fontWeight: 600, letterSpacing: '.05em', textTransform: 'uppercase', marginTop: 3 }}>AI · Multi-Agent</div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ padding: '14px 10px', flex: 1 }}>
          <NavSection label="OVERVIEW">
            <NavItem icon="⊞" label="Dashboard"    active={page === 'dashboard'} onClick={() => setPage('dashboard')} />
          </NavSection>
          <NavSection label="PROCESSING">
            <NavItem icon="📋" label="Submit Claim" active={page === 'form'}      onClick={() => setPage('form')} />
            <NavItem icon="📎" label="Upload Mode"  active={page === 'upload'}    onClick={() => setPage('upload')} badge="NEW" />
          </NavSection>
          <NavSection label="PIPELINE AGENTS">
            {[
              ['1', 'Gatekeeper',  'Doc + member validation'],
              ['2', 'Doc Quality', 'Readability checks'],
              ['3', 'Extractor',   'AI vision + OCR fallback'],
              ['4', 'Adjudicator', 'Pure Python policy'],
              ['5', 'Auditor',     'Fraud + finalise'],
            ].map(([n, name, desc]) => (
              <div key={n} style={{ display: 'flex', gap: 9, padding: '5px 8px', alignItems: 'flex-start' }}>
                <span style={{
                  width: 20, height: 20, borderRadius: '50%', background: 'var(--accent-bg)',
                  color: 'var(--accent-h)', fontSize: 10, fontWeight: 700,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0, marginTop: 1, border: '1px solid #fed7aa',
                }}>{n}</span>
                <div>
                  <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text2)', lineHeight: 1 }}>{name}</div>
                  <div style={{ fontSize: 10.5, color: 'var(--muted2)', marginTop: 2 }}>{desc}</div>
                </div>
              </div>
            ))}
          </NavSection>
        </nav>

        {/* Status pill */}
        <div style={{ margin: 10, padding: '9px 12px', background: 'var(--green-bg)', border: '1px solid #bbf7d0', borderRadius: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <div style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--green)', flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--green)' }}>Pipeline Online</div>
              <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 1 }}>LangGraph · FastAPI</div>
            </div>
          </div>
        </div>
      </aside>

      {/* ── Main ── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'auto' }}>

        {/* Topbar */}
        <header style={{
          background: 'var(--surface)', borderBottom: '1px solid var(--border2)',
          padding: '12px 28px', display: 'flex', alignItems: 'center', gap: 16,
          position: 'sticky', top: 0, zIndex: 10,
          boxShadow: '0 1px 4px rgba(0,0,0,.06)',
        }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 17, color: 'var(--text)' }}>
              { page === 'form' ? 'Submit Claim'
              : page === 'upload' ? 'Upload Mode'
              : 'Dashboard' }
            </div>
            <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 1 }}>
              { page === 'form' ? 'Run a claim through all 5 pipeline agents'
              : page === 'upload' ? 'Upload a real invoice image · Tests live Gemini vision extraction'
              : 'Session overview' }
            </div>
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 16, alignItems: 'center' }}>
            {stats.total > 0 && (
              <div style={{ display: 'flex', gap: 14 }}>
                {[
                  ['Processed', stats.total,    'var(--text)'],
                  ['Approved',  stats.approved, 'var(--green)'],
                  ['Flagged',   stats.manual,   'var(--yellow)'],
                  ['Rejected',  stats.rejected, 'var(--red)'],
                ].map(([l, v, c]) => (
                  <div key={l} style={{ textAlign: 'center' }}>
                    <div style={{ fontWeight: 700, fontSize: 16, color: c, lineHeight: 1 }}>{v}</div>
                    <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 2 }}>{l}</div>
                  </div>
                ))}
              </div>
            )}
            <span className="badge badge-green" style={{ fontSize: 11 }}>● LIVE</span>
          </div>
        </header>

        {/* Content */}
        <main style={{ flex: 1, padding: '24px 28px' }}>

          {page === 'dashboard' && (
            <DashboardPage stats={stats} onNavigate={setPage} members={members} />
          )}

          {page === 'form' && (
            <div style={{
              display: 'grid',
              gridTemplateColumns: result ? '1fr 1fr' : '640px',
              gap: 24, alignItems: 'start',
            }}>
              <ClaimForm testCases={testCases} members={members}
                onSubmit={handleSubmit} loading={loading} error={error} />
              {result && <ResultDisplay result={result} />}
            </div>
          )}

          {page === 'upload' && <UploadMode API={API} />}
        </main>
      </div>
    </div>
  )
}

// ── Nav helpers ────────────────────────────────────────────────────────────
function NavSection({ label, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted2)', textTransform: 'uppercase', letterSpacing: '.08em', padding: '0 8px', marginBottom: 5 }}>
        {label}
      </div>
      {children}
    </div>
  )
}

function NavItem({ icon, label, active, onClick, badge }) {
  return (
    <button onClick={onClick} style={{
      width: '100%', display: 'flex', alignItems: 'center', gap: 9,
      padding: '8px 10px', borderRadius: 7, border: 'none',
      background: active ? 'var(--accent-bg)' : 'transparent',
      borderLeft: `3px solid ${active ? 'var(--accent)' : 'transparent'}`,
      color: active ? 'var(--accent-h)' : 'var(--text2)',
      fontWeight: active ? 600 : 500, cursor: 'pointer',
      textAlign: 'left', fontSize: 13.5, fontFamily: 'inherit',
      marginBottom: 2, transition: 'all .12s',
    }}>
      <span style={{ width: 18, textAlign: 'center', fontSize: 14 }}>{icon}</span>
      <span style={{ flex: 1 }}>{label}</span>
      {badge && (
        <span style={{ fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 99, background: 'var(--accent)', color: '#fff' }}>
          {badge}
        </span>
      )}
    </button>
  )
}

// ── Dashboard Page ─────────────────────────────────────────────────────────
function DashboardPage({ stats, onNavigate, members }) {
  return (
    <div>
      <div style={{ marginBottom: 22 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)' }}>Portfolio Overview</h2>
        <p style={{ color: 'var(--muted)', fontSize: 13, marginTop: 4 }}>Live snapshot of this session's claim activity</p>
      </div>

      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 22 }}>
        {[
          { label: 'Total Processed', val: stats.total,    sub: 'This session',    color: 'var(--accent)', icon: '📊' },
          { label: 'Approved',        val: stats.approved, sub: 'Good standing',   color: 'var(--green)',  icon: '✅' },
          { label: 'Manual Review',   val: stats.manual,   sub: 'Requires action', color: 'var(--yellow)', icon: '⚠️' },
          { label: 'Rejected',        val: stats.rejected, sub: 'Not covered',     color: 'var(--red)',    icon: '❌' },
        ].map(s => (
          <div key={s.label} className="stat-card" style={{ borderTop: `3px solid ${s.color}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <div>
                <div className="stat-label">{s.label}</div>
                <div className="stat-value" style={{ color: s.color }}>{s.val}</div>
                <div className="stat-sub">{s.sub}</div>
              </div>
              <span style={{ fontSize: 24 }}>{s.icon}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Quick actions */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 22 }}>
        <div className="card" style={{ padding: 22 }}>
          <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>📋 Submit a Claim</div>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 16, lineHeight: 1.6 }}>
            Use the 12 built-in test cases or enter details manually. All 5 agents will run with full audit trace.
          </div>
          <button className="btn btn-primary" onClick={() => onNavigate('form')}>Open Claim Form →</button>
        </div>
        <div className="card" style={{ padding: 22 }}>
          <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>
            📎 Upload Mode
            <span style={{ marginLeft: 8, fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 99, background: 'var(--accent)', color: '#fff' }}>NEW</span>
          </div>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 16, lineHeight: 1.6 }}>
            Upload a real pharmacy bill or hospital invoice. Tests the live Gemini vision + OCR extraction pipeline end-to-end.
          </div>
          <button className="btn btn-primary" onClick={() => onNavigate('upload')}>Try Upload Mode →</button>
        </div>
      </div>

      {/* Members table */}
      {members.length > 0 && (
        <div className="card" style={{ padding: 22 }}>
          <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 14 }}>
            👥 Member Roster — {members.filter(m => m.relationship === 'SELF').length} employees
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: 10 }}>
            {members.filter(m => m.relationship === 'SELF').map(m => (
              <div key={m.member_id} style={{ padding: '10px 14px', borderRadius: 8, background: 'var(--surface2)', border: '1px solid var(--border2)' }}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{m.name}</div>
                <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>{m.member_id} · Joined {m.join_date}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
