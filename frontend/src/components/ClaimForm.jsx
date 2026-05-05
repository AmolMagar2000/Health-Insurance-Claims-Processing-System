import { useState } from 'react'

const CATEGORIES = ['CONSULTATION', 'DIAGNOSTIC', 'PHARMACY', 'DENTAL', 'VISION', 'ALTERNATIVE_MEDICINE']

function Field({ label, children, hint }) {
  return (
    <div>
      <label className="field-label">{label}</label>
      {children}
      {hint && <div style={{ fontSize: 11, color: 'var(--muted2)', marginTop: 4 }}>{hint}</div>}
    </div>
  )
}

const DEFAULT_DOCS = JSON.stringify([
  {
    file_id: 'F001', actual_type: 'PRESCRIPTION', quality: 'GOOD',
    content: {
      doctor_name: 'Dr. Arun Sharma', doctor_registration: 'KA/45678/2015',
      patient_name: 'Rajesh Kumar', date: '2024-11-01', diagnosis: 'Viral Fever',
      medicines: ['Paracetamol 650mg', 'Vitamin C 500mg'],
    },
  },
  {
    file_id: 'F002', actual_type: 'HOSPITAL_BILL', quality: 'GOOD',
    content: {
      hospital_name: 'City Clinic', patient_name: 'Rajesh Kumar',
      line_items: [{ description: 'Consultation Fee', amount: 1000 }, { description: 'CBC', amount: 500 }],
      total: 1500,
    },
  },
], null, 2)

export default function ClaimForm({ testCases, onSubmit, loading, error }) {
  const [form, setForm] = useState({
    member_id: 'EMP001', policy_id: 'PLUM_GHI_2024',
    claim_category: 'CONSULTATION', treatment_date: '2024-11-01',
    claimed_amount: 1500, hospital_name: '', ytd_claims_amount: 0,
    simulate_component_failure: false, pre_auth_id: '',
  })
  const [docsJson,    setDocsJson]    = useState(DEFAULT_DOCS)
  const [historyJson, setHistoryJson] = useState('[]')
  const [jsonError,   setJsonError]   = useState(null)
  const [activeTab,   setActiveTab]   = useState('basic')

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  function loadTestCase(tc) {
    if (!tc) return
    const i = tc.input
    set('member_id',    i.member_id)
    set('policy_id',    i.policy_id)
    set('claim_category', i.claim_category)
    set('treatment_date', i.treatment_date)
    set('claimed_amount', i.claimed_amount)
    set('hospital_name', i.hospital_name || '')
    set('ytd_claims_amount', i.ytd_claims_amount || 0)
    set('simulate_component_failure', i.simulate_component_failure || false)
    setDocsJson(JSON.stringify(i.documents || [], null, 2))
    setHistoryJson(JSON.stringify(i.claims_history || [], null, 2))
    setJsonError(null)
  }

  function handleSubmit(e) {
    e.preventDefault()
    setJsonError(null)
    let docs, history
    try { docs    = JSON.parse(docsJson)    } catch { setJsonError('Documents JSON is invalid'); return }
    try { history = JSON.parse(historyJson) } catch { setJsonError('Claims history JSON is invalid'); return }
    onSubmit({
      ...form,
      claimed_amount:    Number(form.claimed_amount),
      ytd_claims_amount: Number(form.ytd_claims_amount),
      pre_auth_id:       form.pre_auth_id || null,
      hospital_name:     form.hospital_name || null,
      documents:         docs,
      claims_history:    history,
    })
  }

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      {/* Card header */}
      <div style={{ padding: '18px 22px 14px', borderBottom: '1px solid var(--border2)', background: 'var(--surface2)' }}>
        <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--text)' }}>Claim Submission Form</div>
        <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 3 }}>Fill manually or load one of the 12 test cases</div>
      </div>

      <div style={{ padding: '18px 22px' }}>

        {/* Test case loader */}
        {testCases.length > 0 && (
          <div style={{ marginBottom: 20 }}>
            <label className="field-label">Quick Load — Test Cases</label>
            <select className="field-input" defaultValue=""
              onChange={e => { const tc = testCases.find(t => t.case_id === e.target.value); if (tc) loadTestCase(tc) }}
              style={{ background: 'var(--accent-bg)', borderColor: '#fed7aa', color: 'var(--accent-h)', fontWeight: 600 }}
            >
              <option value="">— Select a test case (TC001–TC012) —</option>
              {testCases.map(tc => (
                <option key={tc.case_id} value={tc.case_id}>{tc.case_id}: {tc.case_name}</option>
              ))}
            </select>
          </div>
        )}

        {/* Tabs */}
        <div className="tabs" style={{ marginBottom: 18 }}>
          {[['basic', '📋 Basic Info'], ['documents', '📄 Documents'], ['advanced', '⚙️ Advanced']].map(([id, label]) => (
            <button key={id} className={`tab-btn ${activeTab === id ? 'active' : ''}`}
              onClick={() => setActiveTab(id)} type="button">{label}</button>
          ))}
        </div>

        <form onSubmit={handleSubmit}>
          {/* Basic tab */}
          {activeTab === 'basic' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                <Field label="Member ID">
                  <input className="field-input" value={form.member_id}
                    onChange={e => set('member_id', e.target.value)} required />
                </Field>
                <Field label="Policy ID">
                  <input className="field-input" value={form.policy_id}
                    onChange={e => set('policy_id', e.target.value)} required />
                </Field>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                <Field label="Claim Category">
                  <select className="field-input" value={form.claim_category}
                    onChange={e => set('claim_category', e.target.value)}>
                    {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                  </select>
                </Field>
                <Field label="Treatment Date">
                  <input className="field-input" type="date" value={form.treatment_date}
                    onChange={e => set('treatment_date', e.target.value)} required />
                </Field>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                <Field label="Claimed Amount (₹)">
                  <input className="field-input" type="number" value={form.claimed_amount} min="0"
                    onChange={e => set('claimed_amount', e.target.value)} required />
                </Field>
                <Field label="Hospital Name" hint="Used for network discount checks">
                  <input className="field-input" value={form.hospital_name} placeholder="e.g. Apollo Hospitals"
                    onChange={e => set('hospital_name', e.target.value)} />
                </Field>
              </div>
            </div>
          )}

          {/* Documents tab */}
          {activeTab === 'documents' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{
                padding: '10px 14px', borderRadius: 8, fontSize: 12.5, lineHeight: 1.7,
                background: 'var(--blue-bg)', border: '1px solid #bfdbfe', color: 'var(--blue)',
              }}>
                <strong>Format:</strong> Array of document objects. Each needs <code>file_id</code>, <code>actual_type</code>,
                <code>quality</code> (GOOD/POOR/UNREADABLE), and either <code>content</code> (test fixture) or <code>base64_data</code> (real image).
              </div>
              <Field label="Documents (JSON)">
                <textarea className="field-input"
                  style={{ fontFamily: 'var(--mono)', fontSize: 12, minHeight: 200, resize: 'vertical', lineHeight: 1.7 }}
                  value={docsJson} onChange={e => setDocsJson(e.target.value)} />
              </Field>
              <Field label="Claims History (for fraud checks)" hint="Array of past claims with date and amount fields">
                <textarea className="field-input"
                  style={{ fontFamily: 'var(--mono)', fontSize: 12, minHeight: 80, resize: 'vertical' }}
                  value={historyJson} onChange={e => setHistoryJson(e.target.value)} />
              </Field>
            </div>
          )}

          {/* Advanced tab */}
          {activeTab === 'advanced' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                <Field label="YTD Claims Amount (₹)"
                  hint="Total amount already claimed in this policy year. Tracked to enforce annual OPD limits.">
                  <input className="field-input" type="number" value={form.ytd_claims_amount} min="0"
                    onChange={e => set('ytd_claims_amount', e.target.value)} />
                </Field>
                <Field label="Pre-Auth ID"
                  hint="Pre-authorisation reference number obtained from insurer BEFORE getting an MRI / CT Scan above ₹10,000. Without this, the claim will be rejected.">
                  <input className="field-input" value={form.pre_auth_id} placeholder="e.g. PA-2024-0012"
                    onChange={e => set('pre_auth_id', e.target.value)} />
                </Field>
              </div>

              {/* Simulate failure */}
              <div style={{
                padding: '12px 16px', borderRadius: 8,
                background: 'var(--yellow-bg)', border: '1px solid #fde68a',
              }}>
                <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer' }}>
                  <input type="checkbox" style={{ marginTop: 3 }} checked={form.simulate_component_failure}
                    onChange={e => set('simulate_component_failure', e.target.checked)} />
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--yellow)' }}>Simulate AI Failure (Test Mode)</div>
                    <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 3, lineHeight: 1.6 }}>
                      Forces the AI extraction step to fail intentionally — activates the backup OCR system.
                      Use this to verify the pipeline handles outages gracefully without crashing.
                      Confidence score will drop to reflect lower extraction quality.
                    </div>
                  </div>
                </label>
              </div>
            </div>
          )}

          {/* Error message */}
          {(jsonError || error) && (
            <div style={{
              marginTop: 14, padding: '10px 14px', borderRadius: 8, fontSize: 13,
              background: 'var(--red-bg)', border: '1px solid #fecaca', color: 'var(--red)',
            }}>
              ⚠ {jsonError || error}
            </div>
          )}

          {/* Submit */}
          <button type="submit" disabled={loading} className="btn btn-primary"
            style={{ marginTop: 18, width: '100%', padding: '13px', fontSize: 14 }}>
            {loading
              ? <><Spinner />  Processing claim through 5 agents…</>
              : <>🚀  Process Claim</>}
          </button>
        </form>
      </div>
    </div>
  )
}

function Spinner() {
  return (
    <span style={{
      display: 'inline-block', width: 14, height: 14,
      border: '2px solid rgba(255,255,255,.3)', borderTopColor: '#fff',
      borderRadius: '50%', animation: 'spin 0.7s linear infinite',
    }} />
  )
}
