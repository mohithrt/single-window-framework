import { useRef, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'

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
  const [dragActive, setDragActive] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  function addFiles(selected: File[]) {
    const valid: File[] = []
    for (const file of selected) {
      if (!['application/pdf', 'image/jpeg', 'image/png'].includes(file.type)) {
        setError(`${file.name}: upload a PDF, JPG, or PNG file.`)
        continue
      }
      if (file.size > 15 * 1024 * 1024) {
        setError(`${file.name}: maximum file size is 15 MB.`)
        continue
      }
      valid.push(file)
    }
    if (valid.length) {
      setFiles((current) => [...current, ...valid])
      setError('')
    }
  }

  function onFiles(event: ChangeEvent<HTMLInputElement>) {
    addFiles(Array.from(event.target.files ?? []))
    event.target.value = ''
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragActive(false)
    if (!busy) addFiles(Array.from(event.dataTransfer.files))
  }

  function removeFile(index: number) {
    setFiles((current) => current.filter((_, currentIndex) => currentIndex !== index))
  }

  async function startManual() {
    setBusy(true)
    setError('')
    try { await createDraft(0) }
    catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not start the application.')
      setBusy(false)
    }
  }

  async function startWithDocuments() {
    if (!files.length) {
      inputRef.current?.click()
      return
    }
    setBusy(true)
    setError('')
    try {
      await createDraft(5)
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
          <p>Enter your details manually or upload your documents. You can edit and overwrite information before submitting.</p>
        </div>

        <div className="application-entry-options">
          <button type="button" className="entry-option" disabled={busy} onClick={() => void startManual()}>
            <span className="entry-option-icon">✎</span>
            <span><strong>Enter manually</strong><small>Fill the application form yourself. Every field stays editable.</small></span>
            <b>→</b>
          </button>
          <div className="entry-upload-option">
            <div className="entry-upload-heading">
              <span className="entry-option-icon">↥</span>
              <span><strong>Upload documents</strong><small>Upload multiple documents and continue with the extracted information.</small></span>
            </div>
            <div
              className={`entry-upload-zone ${dragActive ? 'drag-active' : ''} ${busy ? 'disabled' : ''}`}
              onDragOver={(event) => { event.preventDefault(); if (!busy) setDragActive(true) }}
              onDragLeave={() => setDragActive(false)}
              onDrop={onDrop}
            >
              <strong>{dragActive ? 'Drop documents here' : 'Drag & drop documents here'}</strong>
              <span>PDF · JPG · PNG · up to 15 MB each</span>
              <button type="button" className="entry-browse-button" disabled={busy} onClick={() => inputRef.current?.click()}>Browse files</button>
              <input ref={inputRef} type="file" hidden multiple accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={onFiles} />
            </div>
            {files.length > 0 && <ul className="entry-file-list">{files.map((file, index) => <li key={`${file.name}-${file.size}-${index}`}><span>FILE</span><strong>{file.name}</strong><button type="button" onClick={() => removeFile(index)} disabled={busy}>Remove</button></li>)}</ul>}
            <button type="button" className="entry-continue-button" disabled={busy || files.length === 0} onClick={() => void startWithDocuments()}>
              {busy ? 'Preparing…' : files.length ? `Continue with ${files.length} document${files.length > 1 ? 's' : ''} →` : 'Choose documents to continue'}
            </button>
          </div>
        </div>

        <div className="application-entry-note">
          <span>✓</span>
          <div><strong>You stay in control</strong><small>Uploaded information can be corrected or overwritten, and existing documents can be replaced later.</small></div>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <a className="application-entry-back" href="/applicant">← Back to dashboard</a>
      </div>
    </main>
  )
}
