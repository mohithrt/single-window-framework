import { useEffect, useState } from 'react'
import type { ChangeEvent } from 'react'
import type { PrevalidationResult } from './applicationTypes'

type Props = { applicationId: number }
type UploadState = { label: string; percent: number } | null

function token() { return localStorage.getItem('mahaclear_access_token') }

function requestUpload(url: string, documentType: string, file: File, onProgress: (percent: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest()
    const body = new FormData()
    body.append('document_type', documentType)
    body.append('file', file)
    request.open('POST', url)
    const accessToken = token()
    if (accessToken) request.setRequestHeader('Authorization', `Bearer ${accessToken}`)
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round(event.loaded * 100 / event.total))
    }
    request.onerror = () => reject(new Error('Upload failed. Check your connection and try again.'))
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) resolve()
      else {
        let message = 'Upload failed.'
        try { message = JSON.parse(request.responseText).detail ?? message } catch { /* use generic message */ }
        reject(new Error(message))
      }
    }
    request.send(body)
  })
}

export default function PrevalidationPage({ applicationId }: Props) {
  const [result, setResult] = useState<PrevalidationResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState<UploadState>(null)
  const [error, setError] = useState('')

  async function load(run = false) {
    const accessToken = token()
    if (!accessToken) { window.location.assign('/login'); return }
    setBusy(true)
    setError('')
    try {
      const response = await fetch(`/api/applications/${applicationId}/prevalidation${run ? '/run' : ''}`, {
        method: run ? 'POST' : 'GET',
        headers: { Authorization: `Bearer ${accessToken}` },
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.detail ?? 'Could not check these documents.')
      setResult(payload as PrevalidationResult)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load pre-validation.')
    } finally { setBusy(false) }
  }

  useEffect(() => { void load(true) }, [applicationId])

  async function upload(category: string, file: File, replaceId?: number) {
    if (file.size > 15 * 1024 * 1024) { setError(`${file.name} exceeds the 15 MB limit.`); return }
    if (!['application/pdf', 'image/jpeg', 'image/png'].includes(file.type)) { setError('Choose a PDF, JPG, or PNG file.'); return }
    setError('')
    setUploading({ label: file.name, percent: 0 })
    try {
      if (replaceId) {
        // Replace keeps the original document category and links the new file to the same record.
        await new Promise<void>((resolve, reject) => {
          const request = new XMLHttpRequest()
          const body = new FormData()
          body.append('file', file)
          request.open('POST', `/api/applications/${applicationId}/documents/${replaceId}/replace`)
          const accessToken = token()
          if (accessToken) request.setRequestHeader('Authorization', `Bearer ${accessToken}`)
          request.upload.onprogress = (event) => { if (event.lengthComputable) setUploading({ label: file.name, percent: Math.round(100 * event.loaded / event.total) }) }
          request.onerror = () => reject(new Error('Upload failed.'))
          request.onload = () => request.status >= 200 && request.status < 300 ? resolve() : reject(new Error(JSON.parse(request.responseText || '{}').detail ?? 'Replace failed.'))
          request.send(body)
        })
      } else {
        await requestUpload(`/api/applications/${applicationId}/documents`, category, file, (percent) => setUploading({ label: file.name, percent }))
      }
      await load(true)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Upload failed.') }
    finally { setUploading(null) }
  }

  async function onSelect(category: string, event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) await upload(category, file)
  }

  async function remove(documentId: number) {
    const response = await fetch(`/api/applications/${applicationId}/documents/${documentId}`, {
      method: 'DELETE', headers: { Authorization: `Bearer ${token()}` },
    })
    if (!response.ok) { setError('Could not delete this document.'); return }
    await load(true)
  }

  if (!result && !error) return <main className="wizard-message"><span className="eyebrow"><i /> DOCUMENT CHECK</span><h1>Loading pre-validation…</h1></main>

  return <div className="wizard-shell">
    <header className="wizard-topbar"><a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a><div className="wizard-top-meta"><span>PRE-VALIDATION</span><strong>{result?.application_number ?? `Application ${applicationId}`}</strong></div><a className="wizard-exit" href={`/applicant/applications/${applicationId}/edit?step=5`}>Back to application <span>↗</span></a></header>
    <main className="prevalidation-main">
      <div className="wizard-heading"><div><span className="eyebrow"><i /> BEFORE SUBMISSION</span><h1>Document pre-validation</h1><p>Review each document, fix issues, and run the checks again before submitting.</p></div><button className="primary-button" disabled={busy || Boolean(uploading)} onClick={() => void load(true)}>{busy ? 'Checking…' : 'Run checks again'} <span>↻</span></button></div>
      {error && <div className="wizard-error" role="alert">{error}</div>}
      {uploading && <div className="upload-progress-panel"><div><strong>Uploading {uploading.label}</strong><span>{uploading.percent}%</span></div><progress max="100" value={uploading.percent} /></div>}
      {result && <>
        <section className={`prevalidation-summary tone-${result.overall_status.toLowerCase()}`}>
          <span className="validation-indicator">{result.overall_status === 'VALID' ? '✓' : result.overall_status === 'WARNING' ? '!' : '×'}</span>
          <div><span className="card-kicker">CHECK RESULT</span><h2>{result.can_submit ? 'Ready to submit with notes' : 'Fix required items before submission'}</h2><p>{result.counts.INVALID} problems · {result.counts.MISSING} missing · {result.counts.WARNING} warnings</p></div>
        </section>
        <section className="validation-list" aria-label="Document validation results">
          {result.documents.map((item) => <article className={`validation-card tone-${item.status.toLowerCase()}`} key={item.document_type}>
            <div className="validation-card-main"><span className="validation-indicator">{item.status === 'VALID' ? '✓' : item.status === 'WARNING' ? '!' : '×'}</span><div><div className="validation-title"><h2>{item.document_label}</h2><span className={`validation-badge tone-${item.status.toLowerCase()}`}>{item.status}</span>{item.required && <span className="required-badge">REQUIRED</span>}</div>
              {item.documents.length ? item.documents.map((doc) => <div className="validation-file" key={doc.id}><span>{doc.file_name}</span><label className="inline-upload">Replace<input type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" disabled={Boolean(uploading)} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void upload(item.document_type, file, doc.id) }} /></label><button type="button" className="inline-delete" disabled={Boolean(uploading)} onClick={() => void remove(doc.id)}>Remove</button></div>) : <p className="validation-empty">{item.required ? 'No document uploaded' : 'Optional document not provided'}</p>}
              {item.issues.map((issue) => <p className="validation-issue" key={issue.id}>{issue.message}{issue.detected_value && issue.expected_value ? ` (${issue.detected_value} found; ${issue.expected_value} expected)` : ''}</p>)}
            </div><label className="validation-upload">{item.documents.length ? 'Add another' : 'Upload'}<input type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" disabled={Boolean(uploading)} onChange={(event) => void onSelect(item.document_type, event)} /></label></div>
          </article>)}
        </section>
        <div className="prevalidation-actions"><a className="secondary-button button-link" href={`/applicant/applications/${applicationId}/edit?step=5`}>← Edit application documents</a><a className="primary-button button-link" href={`/applicant/applications/${applicationId}/edit?step=6`}>{result.can_submit ? 'Continue to review' : 'Review issues'} <span>→</span></a></div>
      </>}
    </main>
  </div>
}
