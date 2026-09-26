import { useState } from 'react'

async function createDraft(step: number) {
  const token = localStorage.getItem('mahaclear_access_token')
  if (!token) { window.location.assign('/login'); return }
  const response = await fetch('/api/applications', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail ?? 'Could not start the application.')
  }
  const application = await response.json()
  window.location.assign(`/applicant/applications/${application.id}/edit?step=${step}`)
}

export default function ApplicationEntryPage() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function choose(step: number) {
    setBusy(true)
    setError('')
    try {
      await createDraft(step)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not start the application.')
      setBusy(false)
    }
  }

  return (
    <main className="application-entry-page">
      <div className="application-entry-card">
        <a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a>
        <div className="application-entry-copy">
          <span className="eyebrow"><i /> NEW APPLICATION</span>
          <h1>How would you like to provide your information?</h1>
          <p>You can enter everything yourself or start with your documents. You can edit and overwrite the information before submitting.</p>
        </div>
        <div className="application-entry-options">
          <button type="button" className="entry-option" disabled={busy} onClick={() => void choose(0)}>
            <span className="entry-option-icon">✎</span>
            <span><strong>Enter manually</strong><small>Fill the application form yourself. Every field stays editable.</small></span>
            <b>→</b>
          </button>
          <button type="button" className="entry-option" disabled={busy} onClick={() => void choose(5)}>
            <span className="entry-option-icon">↥</span>
            <span><strong>Upload documents</strong><small>Upload multiple documents first, then review and edit the application details.</small></span>
            <b>→</b>
          </button>
        </div>
        <div className="application-entry-note">
          <span>✓</span>
          <div><strong>You stay in control</strong><small>Uploaded information can be corrected or overwritten, and an existing document can be replaced later.</small></div>
        </div>
        {busy && <p className="application-entry-status">Preparing your secure draft…</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <a className="application-entry-back" href="/applicant">← Back to dashboard</a>
      </div>
    </main>
  )
}
