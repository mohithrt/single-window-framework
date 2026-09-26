import { useEffect, useRef, useState } from 'react'
import type { ApplicationDocument, ApplicationsResponse, ApplicationRecord } from './applicationTypes'
import { DOCUMENT_TYPES, formatDate, statusLabel } from './applicationTypes'

function authHeaders() {
  const token = localStorage.getItem('mahaclear_access_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function labelFor(type: string) {
  return DOCUMENT_TYPES.find(([id]) => id === type)?.[1] || type.replaceAll('_', ' ')
}

function formatSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function ApplicantDocumentsPage() {
  const [data, setData] = useState<ApplicationsResponse | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [documentType, setDocumentType] = useState<string>(DOCUMENT_TYPES[0][0])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const replaceRef = useRef<HTMLInputElement>(null)
  const [replaceTarget, setReplaceTarget] = useState<{ applicationId: number; documentId: number } | null>(null)

  async function load() {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    const response = await fetch('/api/applications', { headers: authHeaders() })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Unable to load your documents.')
    const next = body as ApplicationsResponse
    setData(next)
    setSelectedId(current => current ?? next.applications[0]?.id ?? null)
  }

  useEffect(() => {
    void load().catch(caught => setError(caught instanceof Error ? caught.message : 'Unable to load your documents.'))
  }, [])

  const signOut = () => {
    localStorage.removeItem('mahaclear_access_token')
    window.location.assign('/login')
  }

  const selected = data?.applications.find(application => application.id === selectedId) || null

  async function upload(application: ApplicationRecord, file: File, type: string, replacingId?: number) {
    setBusy(true); setError(''); setMessage('')
    try {
      const form = new FormData()
      form.append('document_type', type)
      form.append('file', file)
      const url = replacingId
        ? `/api/applications/${application.id}/documents/${replacingId}/replace`
        : `/api/applications/${application.id}/documents`
      const response = await fetch(url, { method: 'POST', headers: authHeaders(), body: form })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : body.detail?.message || 'Document upload failed.')
      setMessage(replacingId ? 'Document replaced successfully.' : 'Document added successfully.')
      await load()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Document upload failed.')
    } finally {
      setBusy(false)
      if (inputRef.current) inputRef.current.value = ''
      if (replaceRef.current) replaceRef.current.value = ''
      setReplaceTarget(null)
    }
  }

  async function remove(application: ApplicationRecord, document: ApplicationDocument) {
    if (!window.confirm(`Remove ${document.file_name} from ${application.application_number}?`)) return
    setBusy(true); setError(''); setMessage('')
    try {
      const response = await fetch(`/api/applications/${application.id}/documents/${document.id}`, { method: 'DELETE', headers: authHeaders() })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(typeof body.detail === 'string' ? body.detail : 'Unable to remove the document.')
      }
      setMessage('Document removed.')
      await load()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to remove the document.')
    } finally {
      setBusy(false)
    }
  }

  async function view(application: ApplicationRecord, document: ApplicationDocument) {
    setError('')
    try {
      const response = await fetch(`/api/applications/${application.id}/documents/${document.id}/download`, { headers: authHeaders() })
      if (!response.ok) throw new Error('Unable to open this document.')
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const opened = window.open(url, '_blank', 'noopener,noreferrer')
      if (!opened) {
        const link = window.document.createElement('a')
        link.href = url
        link.download = document.file_name
        link.click()
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to open this document.')
    }
  }

  function chooseAdd() {
    if (!selected) { setError('Select an application first.'); return }
    inputRef.current?.click()
  }

  function chooseReplace(applicationId: number, documentId: number) {
    setReplaceTarget({ applicationId, documentId })
    replaceRef.current?.click()
  }

  async function onAddFile(file: File | undefined) {
    if (!file || !selected) return
    await upload(selected, file, documentType)
  }

  async function onReplaceFile(file: File | undefined) {
    if (!file || !replaceTarget) return
    const application = data?.applications.find(item => item.id === replaceTarget.applicationId)
    if (!application) return
    const current = application.documents.find(item => item.id === replaceTarget.documentId)
    await upload(application, file, current?.document_type || documentType, replaceTarget.documentId)
  }

  const totalDocuments = data?.applications.reduce((sum, app) => sum + app.documents.length, 0) || 0

  return (
    <div className="applicant-shell">
      <header className="applicant-topbar">
        <a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a>
        <div className="applicant-topbar-spacer" aria-hidden="true" />
        <button className="applicant-signout" type="button" onClick={signOut}><span className="signout-icon">↪</span><strong>Sign out</strong></button>
      </header>

      <aside className="applicant-sidebar">
        <div className="workspace-nav-label">APPLICANT WORKSPACE</div>
        <a className="side-link selected" href="/applicant"><span>▣</span> Documents</a>
        <a className="side-link" href="/applicant/permissions"><span>◎</span> Permissions &amp; fees</a>
        <a className="side-link" href="/notifications"><span>◉</span> Verification &amp; updates</a>
        <a className="side-link" href="/applicant/applications"><span>▤</span> My applications</a>
        <div className="sidebar-note"><span className="sidebar-note-mark">✳</span><strong>One window.<br />Every approval.</strong><small>North-Star · SIH 2026</small></div>
        <div className="sidebar-bottom">MAHACLEAR-AI <span>·</span> APPLICANT</div>
      </aside>

      <main className="applicant-main documents-main">
        <div className="breadcrumb">APPLICANT WORKSPACE <span>/</span> DOCUMENTS</div>
        <div className="applicant-heading">
          <div><span className="eyebrow"><i /> DOCUMENT CENTRE</span><h1>Your documents</h1><p>View, add, replace and remove the documents attached to your applications.</p></div>
          <button className="primary-button new-application-button" type="button" onClick={chooseAdd} disabled={busy || !selected}>Add document <span>＋</span></button>
        </div>

        <input ref={inputRef} className="visually-hidden-input" type="file" accept=".pdf,.jpg,.jpeg,.png,.docx,application/pdf,image/jpeg,image/png,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={event => void onAddFile(event.target.files?.[0])} />
        <input ref={replaceRef} className="visually-hidden-input" type="file" accept=".pdf,.jpg,.jpeg,.png,.docx,application/pdf,image/jpeg,image/png,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={event => void onReplaceFile(event.target.files?.[0])} />

        {error && <div className="applicant-error" role="alert">{error} <button onClick={() => window.location.reload()}>Retry</button></div>}
        {message && <div className="documents-success" role="status">{message}</div>}

        {!data ? (!error ? <div className="loading-panel">Loading your documents…</div> : null) : (
          <>
            <section className="documents-toolbar">
              <label>APPLICATION
                <select value={selectedId ?? ''} onChange={event => setSelectedId(Number(event.target.value))}>
                  {data.applications.map(application => <option key={application.id} value={application.id}>{application.application_number}{application.industry_type ? ` · ${application.industry_type}` : ''}</option>)}
                </select>
              </label>
              <label>DOCUMENT TYPE
                <select value={documentType} onChange={event => setDocumentType(event.target.value)}>
                  {DOCUMENT_TYPES.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
                </select>
              </label>
              <div className="documents-count"><strong>{selected?.documents.length || 0}</strong> documents in this application <span>·</span> <strong>{totalDocuments}</strong> across all applications</div>
            </section>

            {selected ? (
              <section className="documents-panel">
                <div className="documents-panel-heading">
                  <div><span className="card-kicker">APPLICATION</span><h2>{selected.application_number}</h2><p>{selected.company_name || 'Company details pending'} <span>·</span> {selected.industry_type || 'Industry not specified'}</p></div>
                  <span className={`status-pill ${selected.status === 'APPROVED' ? 'approved' : selected.status === 'REJECTED' ? 'rejected' : selected.status === 'ACTION_REQUIRED' ? 'action' : selected.status === 'IN_REVIEW' ? 'pending' : 'draft'}`}><i />{statusLabel(selected.status)}</span>
                </div>
                {selected.documents.length === 0 ? (
                  <div className="empty-applications"><span className="empty-mark">＋</span><h3>No documents uploaded yet</h3><p>Choose a document type above and add the first PDF, image or DOCX.</p><button className="primary-button" type="button" onClick={chooseAdd}>Add first document <span>→</span></button></div>
                ) : (
                  <div className="document-list">
                    {selected.documents.map(document => (
                      <article className="document-row" key={document.id}>
                        <div className={`document-type-icon ${document.media_type.includes('pdf') ? 'pdf' : document.media_type.includes('image') ? 'image' : 'docx'}`}>{document.media_type.includes('pdf') ? 'PDF' : document.media_type.includes('image') ? 'IMG' : 'DOCX'}</div>
                        <div className="document-row-main"><strong>{labelFor(document.document_type)}</strong><span>{document.file_name} · {formatSize(document.size_bytes)} · uploaded {formatDate(document.uploaded_at)}</span></div>
                        <span className={`document-status ${document.status.toLowerCase()}`}><i />{document.status}</span>
                        <div className="document-actions"><button type="button" onClick={() => void view(selected, document)} disabled={busy}>View</button><button type="button" onClick={() => chooseReplace(selected.id, document.id)} disabled={busy}>Replace</button><button type="button" className="danger-action" onClick={() => void remove(selected, document)} disabled={busy}>Remove</button></div>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            ) : (
              <div className="empty-applications"><h3>No applications available</h3><p>Create an application first, then upload its documents here.</p><a className="primary-button" href="/applicant/applications/new">New application <span>→</span></a></div>
            )}
          </>
        )}
      </main>

      <footer className="workspace-footer"><span>MAHACLEAR-AI <span>· Document centre</span></span><span>TEAM NORTH-STAR <i>·</i> SIH 2026</span></footer>
    </div>
  )
}
