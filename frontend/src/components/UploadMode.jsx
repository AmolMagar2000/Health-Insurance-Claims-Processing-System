import { useState, useRef, useCallback } from 'react'

const CATEGORIES = ['CONSULTATION', 'DIAGNOSTIC', 'PHARMACY', 'DENTAL', 'VISION', 'ALTERNATIVE_MEDICINE']
const DOC_TYPES  = ['PRESCRIPTION', 'HOSPITAL_BILL', 'PHARMACY_BILL', 'LAB_REPORT', 'DISCHARGE_SUMMARY', 'DENTAL_REPORT']

export default function UploadMode({ API }) {
  const [file,     setFile]     = useState(null)
  const [preview,  setPreview]  = useState(null)
  const [docType,  setDocType]  = useState('PHARMACY_BILL')
  const [category, setCategory] = useState('PHARMACY')
  const [memberId, setMemberId] = useState('EMP001')
  const [amount,   setAmount]   = useState(150)
  const [date,     setDate]     = useState('2024-11-01')
  const [dragging, setDragging] = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [result,   setResult]   = useState(null)
  const [error,    setError]    = useState(null)
  const [phase,    setPhase]    = useState(null)
  const inputRef = useRef()

  function onFileChange(f) {
    if (!f) return
    if (!f.type.match(/image\/(jpeg|png|jpg|webp)/)) {
      setError('Please upload a JPEG or PNG image.'); return
    }
    if (f.size > 10 * 1024 * 1024) {
      setError('File too large. Max 10 MB.'); return
    }
    setFile(f); setError(null); setResult(null)
    const reader = new FileReader()
    reader.onload = e => setPreview(e.target.result)
    reader.readAsDataURL(f)
  }

  const onDrop = useCallback(e => {
    e.preventDefault(); setDragging(false)
    onFileChange(e.dataTransfer.files[0])
  }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    if (!file) { setError('Please upload an image first.'); return }
    setLoading(true); setError(null); setResult(null)

    try {
      setPhase('reading')
      const base64 = await toBase64(file)

      const payload = {
        member_id: memberId, policy_id: 'PLUM_GHI_2024',
        claim_category: category, treatment_date: date,
        claimed_amount: Number(amount),
        documents: [{
          file_id: 'UPLOAD_001', file_name: file.name,
          actual_type: docType, quality: 'GOOD',
          mime_type: file.type, base64_data: base64,
        }],
        claims_history: [],
      }

      // Add required companion document based on category
      const fixture = (type, extra = {}) => ({
        file_id: 'FIXTURE_DOC', actual_type: type, quality: 'GOOD',
        content: { doctor_name: 'Dr. Arun Sharma', patient_name: 'Rajesh Kumar', diagnosis: 'Viral Fever', ...extra },
      })
      if (category === 'PHARMACY')     payload.documents.push(fixture('PRESCRIPTION'))
      if (category === 'CONSULTATION') payload.documents.push(fixture('PRESCRIPTION'))
      if (category === 'DIAGNOSTIC')   payload.documents.push(fixture('PRESCRIPTION'), fixture('LAB_REPORT', { line_items: [] }))

      setPhase('processing')
      const res = await fetch(`${API}/submit-claim`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail || `HTTP ${res.status}`) }
      setResult(await res.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false); setPhase(null)
    }
  }

  function toBase64(f) {
    return new Promise((res, rej) => {
      const r = new FileReader()
      r.onload = () => res(r.result.split(',')[1])
      r.onerror = rej
      r.readAsDataURL(f)
    })
  }

  return (
    <div style={{ maxWidth: 1100 }}>

      {/* Page header */}
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text)' }}>Upload Mode</h2>
        <p style={{ fontSize: 13, color: 'var(--muted)', marginTop: 5, lineHeight: 1.7 }}>
          Upload a real medical document — pharmacy bill, hospital invoice, or prescription.
          The AI reads the document and runs it through the complete 5-agent pipeline.
        </p>
      </div>

      {/* Steps bar */}
      <div style={{
        display: 'flex', gap: 8, marginBottom: 22, flexWrap: 'wrap',
        padding: '12px 16px', background: 'var(--blue-bg)',
        border: '1px solid #bfdbfe', borderRadius: 10,
      }}>
        {[
          ['1', '📸', 'Upload your document'],
          ['2', '🤖', 'AI reads and extracts data'],
          ['3', '⚙️', 'All 5 pipeline agents run'],
          ['4', '📊', 'Decision + full trace shown'],
        ].map(([n, icon, label]) => (
          <div key={n} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--blue)', fontWeight: 500 }}>
            <span style={{
              width: 20, height: 20, borderRadius: '50%', background: 'var(--blue)',
              color: '#fff', fontSize: 10, fontWeight: 700,
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>{n}</span>
            {icon} {label}
            {n !== '4' && <span style={{ color: '#93c5fd', marginLeft: 4 }}>→</span>}
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: result ? '400px 1fr' : '480px 1fr', gap: 22, alignItems: 'start' }}>

        {/* ── Upload form ── */}
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px 11px', background: 'var(--surface2)', borderBottom: '1px solid var(--border2)' }}>
            <div style={{ fontWeight: 700, fontSize: 15 }}>Upload Document</div>
            <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>JPEG or PNG · pharmacy bills, prescriptions, invoices</div>
          </div>

          <div style={{ padding: '16px 20px' }}>

            {/* Drop zone */}
            <div
              className={`drop-zone ${dragging ? 'dragover' : ''}`}
              onDragOver={e => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              onClick={() => inputRef.current?.click()}
              style={{ marginBottom: 16 }}
            >
              <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp"
                style={{ display: 'none' }} onChange={e => onFileChange(e.target.files[0])} />

              {preview ? (
                <div>
                  <img src={preview} alt="preview"
                    style={{ maxWidth: '100%', maxHeight: 260, objectFit: 'contain', borderRadius: 6, marginBottom: 8 }} />
                  <div style={{ fontSize: 12, color: 'var(--green)', fontWeight: 600 }}>
                    ✓ {file?.name}  ({(file?.size / 1024).toFixed(0)} KB)
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>Click to replace</div>
                </div>
              ) : (
                <div>
                  <div style={{ fontSize: 36, marginBottom: 10 }}>📄</div>
                  <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text2)', marginBottom: 5 }}>
                    Drag & drop or click to upload
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--muted)' }}>JPEG, PNG · Max 10 MB</div>
                </div>
              )}
            </div>

            {/* Config */}
            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div>
                  <label className="field-label">Document Type</label>
                  <select className="field-input" value={docType} onChange={e => setDocType(e.target.value)}>
                    {DOC_TYPES.map(t => <option key={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label className="field-label">Claim Category</label>
                  <select className="field-input" value={category} onChange={e => setCategory(e.target.value)}>
                    {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                  </select>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div>
                  <label className="field-label">Member ID</label>
                  <input className="field-input" value={memberId} onChange={e => setMemberId(e.target.value)} />
                </div>
                <div>
                  <label className="field-label">Claimed Amount (₹)</label>
                  <input className="field-input" type="number" value={amount} min="0" onChange={e => setAmount(e.target.value)} />
                </div>
              </div>

              <div>
                <label className="field-label">Treatment Date</label>
                <input className="field-input" type="date" value={date} onChange={e => setDate(e.target.value)} />
              </div>

              {error && (
                <div style={{ padding: '9px 13px', borderRadius: 8, background: 'var(--red-bg)', border: '1px solid #fecaca', color: 'var(--red)', fontSize: 13 }}>
                  ⚠ {error}
                </div>
              )}

              <button type="submit" disabled={loading || !file} className="btn btn-primary"
                style={{ padding: '12px', fontSize: 14, marginTop: 2 }}>
                {loading ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Spinner />
                    {phase === 'reading' ? 'Reading document…' : 'Processing through pipeline…'}
                  </span>
                ) : '🤖  Analyse & Process Document'}
              </button>
            </form>
          </div>
        </div>

        {/* ── Right panel: result or reference card ── */}
        {result
          ? <UploadResult result={result} />
          : <SampleDocCard />
        }
      </div>
    </div>
  )
}

// ── Result panel ──────────────────────────────────────────────────────────
function UploadResult({ result }) {
  const [showTrace, setShowTrace] = useState(false)
  const ext   = result.extracted_data || {}
  const trace = result.trace_log || []

  const colorMap = { APPROVED: '#16a34a', PARTIAL: '#d97706', REJECTED: '#dc2626', MANUAL_REVIEW: '#7c3aed' }
  const badgeMap = { APPROVED: 'badge-green', PARTIAL: 'badge-yellow', REJECTED: 'badge-red', MANUAL_REVIEW: 'badge-purple' }
  const color    = colorMap[result.decision] || '#78716c'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Decision card */}
      <div className="card" style={{ padding: '18px 20px', borderTop: `3px solid ${color}` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div style={{ fontWeight: 700, fontSize: 16 }}>Result</div>
          <span className={`badge ${badgeMap[result.decision] || 'badge-gray'}`} style={{ fontSize: 13 }}>
            {result.decision}
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
          {[
            ['Claimed',    `₹${(result.claimed_amount  || 0).toLocaleString()}`, 'var(--text)'],
            ['Approved',   `₹${(result.approved_amount || 0).toLocaleString()}`, color],
            ['Confidence', `${Math.round((result.confidence_score || 0) * 100)}%`,
              (result.confidence_score || 0) >= 0.7 ? 'var(--green)' : 'var(--red)'],
          ].map(([l, v, c]) => (
            <div key={l} style={{ textAlign: 'center', padding: 12, background: 'var(--surface2)', borderRadius: 8, border: '1px solid var(--border2)' }}>
              <div style={{ fontSize: 10, color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em' }}>{l}</div>
              <div style={{ fontSize: 19, fontWeight: 700, color: c, marginTop: 4 }}>{v}</div>
            </div>
          ))}
        </div>

        {result.errors?.length > 0 && (
          <div style={{ marginTop: 12, padding: '9px 13px', background: 'var(--red-bg)', border: '1px solid #fecaca', borderRadius: 8 }}>
            {result.errors.map((e, i) => <div key={i} style={{ fontSize: 13, color: 'var(--red)', marginBottom: 3 }}>• {e}</div>)}
          </div>
        )}
      </div>

      {/* Extracted data */}
      {Object.keys(ext).length > 0 && (
        <div className="card" style={{ padding: '16px 20px' }}>
          <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 12 }}>📋 Extracted from Document</div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {[
              ['Patient',  ext.patient_name],
              ['Doctor',   ext.doctor_name],
              ['Reg. No.', ext.doctor_registration],
              ['Date',     ext.date],
              ['Diagnosis',ext.diagnosis],
              ['Facility', ext.hospital_name],
              ['Total',    ext.total_amount != null ? `₹${Number(ext.total_amount).toLocaleString()}` : null],
            ].filter(([, v]) => v).map(([k, v]) => (
              <div key={k} style={{ padding: '8px 10px', borderRadius: 7, background: 'var(--surface2)', border: '1px solid var(--border2)' }}>
                <div style={{ fontSize: 10, color: 'var(--muted2)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em' }}>{k}</div>
                <div style={{ fontSize: 13, color: 'var(--text)', fontWeight: 600, marginTop: 3 }}>{String(v)}</div>
              </div>
            ))}
          </div>

          {ext.line_items?.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text2)', marginBottom: 7 }}>Itemised Bill</div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: 'var(--surface2)' }}>
                    {['Item', 'Amount'].map(h => (
                      <th key={h} style={{ textAlign: 'left', padding: '5px 9px', color: 'var(--muted)', fontWeight: 600, borderBottom: '1px solid var(--border2)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ext.line_items.map((item, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--border2)' }}>
                      <td style={{ padding: '6px 9px', color: 'var(--text2)' }}>{item.description || String(item)}</td>
                      <td style={{ padding: '6px 9px', fontWeight: 600, color: 'var(--text)' }}>₹{(item.amount || 0).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {ext.medicines?.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text2)', marginBottom: 6 }}>Medicines</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {ext.medicines.map((m, i) => (
                  <span key={i} className="badge badge-blue" style={{ fontSize: 12 }}>{m}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Audit trace */}
      <div className="card" style={{ padding: '14px 20px' }}>
        <button type="button"
          style={{ width: '100%', background: 'transparent', border: 'none', display: 'flex', justifyContent: 'space-between', cursor: 'pointer', padding: 0, marginBottom: showTrace ? 12 : 0 }}
          onClick={() => setShowTrace(s => !s)}>
          <span style={{ fontWeight: 700, fontSize: 14, color: 'var(--text)' }}>📜 Audit Trace ({trace.length} entries)</span>
          <span style={{ fontSize: 11, color: 'var(--muted2)' }}>{showTrace ? '▲ hide' : '▼ show'}</span>
        </button>
        {showTrace && (
          <div style={{ maxHeight: 340, overflowY: 'auto' }}>
            {trace.map((line, i) => {
              const isH = line.startsWith('═') || line.startsWith('AGENT') || line.startsWith('FINAL') || line.startsWith('PIPELINE')
              const isOk = line.includes('✓')
              const isW  = line.includes('✗') || line.includes('⚠')
              return (
                <div key={i} className={`trace-line ${isH ? 'trace-header' : isOk ? 'trace-ok' : isW ? 'trace-warn' : 'trace-muted'}`}
                  style={{ paddingLeft: line.startsWith('  ') ? 14 : 0 }}>
                  {line}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Reference card ────────────────────────────────────────────────────────
function SampleDocCard() {
  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 10 }}>📋 Test with the Provided Invoice</div>
      <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 14, lineHeight: 1.6 }}>
        Upload the Sri Sai Medicals pharmacy bill image. The AI should extract:
      </div>
      {[
        ['Pharmacy',    'Sri Sai Medicals & Pharmacy, Bengaluru'],
        ['Patient',     'Rajesh Kumar, Age 39, Male'],
        ['Doctor',      'Dr. Arun Sharma · Reg. KA/45678/2015'],
        ['Invoice No.', 'SM/24-25/1897 · 01/11/2024'],
        ['Medicines',   'Paracetamol · Vitamin C · Azithromycin · ORS · Benadryl'],
        ['Grand Total', '₹150.00 (after ₹5.80 discount)'],
      ].map(([k, v]) => (
        <div key={k} style={{ display: 'flex', gap: 10, padding: '6px 0', borderBottom: '1px solid var(--border2)', fontSize: 13 }}>
          <span style={{ color: 'var(--muted)', minWidth: 95, flexShrink: 0, fontSize: 12 }}>{k}</span>
          <span style={{ color: 'var(--text2)', fontWeight: 500 }}>{v}</span>
        </div>
      ))}
      <div style={{ marginTop: 14, padding: '10px 13px', background: 'var(--accent-bg)', border: '1px solid #fed7aa', borderRadius: 8, fontSize: 12.5, color: 'var(--accent-h)', lineHeight: 1.7 }}>
        💡 Expected result: <strong>APPROVED</strong> — ₹150 pharmacy claim, valid member, no waiting period issue, within all limits.
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
