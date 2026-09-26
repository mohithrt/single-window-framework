import { useCallback, useEffect, useState } from 'react'
import type { ChangeEvent, FormEvent, ReactNode } from 'react'
import AuthenticatedDownload from './AuthenticatedDownload'

type View = 'dashboard' | 'queue' | 'inspections' | 'joint-inspections' | 'documents' | 'escalations' | 'reports' | 'profile' | 'review'
type Officer = { id: number; full_name: string; email: string; role: string }
type QueueItem = {
  approval_id: number; application_id: number; application_number: string; department_name: string
  applicant_name: string; company_name: string; industry_type: string | null; risk_tier: string | null
  application_status: string; approval_status: string; submitted_at: string | null
  sla_status: string; sla_due_at: string | null; days_overdue: number
}
type QueueResponse = { total: number; items: QueueItem[] }
type ApprovalDetail = {
  approval: { id: number; department_code: string; department_name: string; status: string; dependencies: string[]; decision_message: string | null; sla: { sla_status: string; sla_due_at: string | null; days_overdue: number } }
  applicant: { name: string; email: string; phone: string | null }
  application: Record<string, string | number | boolean | null>
  risk_assessment: Record<string, unknown>
  documents: Array<{ id: number; document_type: string; file_name: string; status: string; media_type: string; size_bytes: number; uploaded_at: string; ocr_text: string; ocr_fields: Record<string, string> }>
  prevalidation: { overall_status: string; issues: Array<{ document_label: string; status: string; message: string }> }
  other_department_statuses: Array<{ department_code: string; department_name: string; is_required: boolean; status: string; decision_message: string | null }>
  previous_remarks: Array<{ id: number; message: string; author: string; created_at: string }>
  inspections: Inspection[]
  audit_history: Array<{ id: number; action: string; from_status: string | null; to_status: string | null; message: string | null; actor: string; created_at: string; details: Record<string, unknown> }>
}
type Inspection = { id: number; application_id: number; approval_id: number | null; approval_ids?: number[]; application_number: string; department_name: string; inspection_type: string; status: string; scheduled_at: string; location: string; site?: string; instructions: string | null; scheduled_by: string | null; checklist?: Array<Record<string, unknown>>; findings?: string | null; photos?: Array<{ file_name: string; download_url?: string }>; remarks?: string | null; recommendation?: string | null; participants?: Array<{ approval_id: number; department_code: string; department_name: string; officer: string | null; status: string }> }

const nav: Array<[View, string, string]> = [
  ['dashboard', 'Dashboard', '◫'], ['queue', 'Application Queue', '▤'], ['inspections', 'Inspections', '☑'],
  ['joint-inspections', 'Joint Inspections', '⇄'], ['documents', 'Documents', '▧'],
  ['escalations', 'Escalations', '⚑'], ['reports', 'Reports', '▥'], ['profile', 'Profile', '◉'],
]
const label = (value: string | null | undefined) => value ? value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase()) : '—'
const dateLabel = (value: string | null | undefined) => value ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'
const dateOnly = (value: string | null | undefined) => value ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(value)) : '—'

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('mahaclear_access_token')
  if (!token) { window.location.assign('/login'); throw new Error('Sign in to continue.') }
  const response = await fetch(path, { ...init, headers: { Authorization: `Bearer ${token}`, ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers } })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'The request could not be completed.')
  return body as T
}

export default function OfficerPortal({ view, approvalId }: { view: View; approvalId?: number }) {
  const [officer, setOfficer] = useState<Officer | null>(null)
  const [authError, setAuthError] = useState('')
  useEffect(() => {
    void api<Officer>('/api/auth/me').then((current) => {
      if (current.role !== 'OFFICER') { window.location.assign(current.role === 'ADMIN' ? '/admin' : '/applicant'); return }
      setOfficer(current)
    }).catch((error: unknown) => setAuthError(error instanceof Error ? error.message : 'Unable to verify officer access.'))
  }, [])
  function signOut() { localStorage.removeItem('mahaclear_access_token'); window.location.assign('/login') }
  const titles: Record<View, string> = { dashboard: 'Officer dashboard', queue: view === 'escalations' ? 'Escalated applications' : 'Application queue', inspections: 'Inspections', 'joint-inspections': 'Joint inspections', documents: 'Documents', escalations: 'Escalations', reports: 'Reports', profile: 'Officer profile', review: 'Application review' }

  return <div className="officer-shell">
    <header className="officer-topbar"><a className="brand" href="/officer"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a><div className="officer-top-label">DEPARTMENT REVIEW PORTAL</div><a className="officer-notification-link" href="/notifications">Notifications</a><button className="signout-button" onClick={signOut}><span className="signout-icon" aria-hidden="true">↪</span><strong>Sign out</strong></button></header>
    <aside className="officer-sidebar"><div className="workspace-nav-label">OFFICER WORKSPACE</div>{nav.map(([key, name, icon]) => <a key={key} className={`side-link ${view === key || (view === 'review' && key === 'queue') ? 'selected' : ''}`} href={`/officer${key === 'dashboard' ? '' : `/${key}`}`}><span>{icon}</span>{name}</a>)}<div className="officer-sidebar-bottom"><strong>{officer?.full_name ?? 'Officer'}</strong><small>{officer?.email ?? 'Verified staff account'}</small></div></aside>
    <main className="officer-main"><div className="breadcrumb">OFFICER WORKSPACE <span>/</span> {titles[view].toUpperCase()}</div>
      {authError ? <div className="applicant-error" role="alert">{authError}</div> : !officer ? <div className="loading-panel">Verifying officer access…</div> : <>
        {view === 'dashboard' && <OfficerDashboard officer={officer} />}
        {view === 'queue' && <QueuePage />}
        {view === 'escalations' && <QueuePage escalations />}
        {view === 'review' && approvalId && <ReviewPage approvalId={approvalId} />}
        {view === 'inspections' && <InspectionList type="SINGLE" />}
        {view === 'joint-inspections' && <InspectionList type="JOINT" />}
        {view === 'documents' && <DocumentsPage />}
        {view === 'reports' && <ReportsPage />}
        {view === 'profile' && <ProfilePage officer={officer} />}
      </>}
    </main>
    <footer className="workspace-footer"><span>MAHACLEAR-AI <span>· Department review portal</span></span><span>TEAM NORTH-STAR <i>·</i> SIH 2026</span></footer>
  </div>
}

function PageHeading({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="officer-heading"><div><span className="eyebrow"><i /> OFFICER WORKSPACE</span><h1>{title}</h1><p>{description}</p></div>{action}</div>
}

function OfficerDashboard({ officer }: { officer: Officer }) {
  const [data, setData] = useState<Record<string, number | string> | null>(null)
  const [recent, setRecent] = useState<QueueResponse | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { void Promise.all([api<Record<string, number | string>>('/api/officer/dashboard'), api<QueueResponse>('/api/officer/queue?limit=6&sort_by=SLA&sort_order=ASC')]).then(([summary, queue]) => { setData(summary); setRecent(queue) }).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Unable to load the officer dashboard.')) }, [])
  const metrics = [
    ['PENDING APPLICATIONS', data?.pending_applications ?? 0, 'blue'], ['IN REVIEW', data?.in_review ?? 0, 'green'],
    ['HIGH RISK', data?.high_risk ?? 0, 'red'], ['SLA WARNING', data?.sla_warning ?? 0, 'amber'],
    ['SLA BREACHED', data?.sla_breached ?? 0, 'amber'], ['ESCALATED', data?.escalated ?? 0, 'red'],
    ['ACTION REQUIRED', data?.action_required ?? 0, 'purple'],
  ] as const
  return <>
    <PageHeading title="Officer dashboard" description={`Review assignments and service levels for ${String(data?.department ?? 'your department')}.`} action={<span className="officer-role-chip">{officer.full_name}</span>} />
    {error && <ErrorBox message={error} />}
    <section className="officer-metrics">{metrics.map(([title, value, tone]) => <article className="officer-metric" key={title}><span className={`officer-metric-dot ${tone}`} /><span className="card-kicker">{title}</span><strong>{value}</strong><small>In the current review queue</small></article>)}</section>
    <section className="officer-panel"><PanelHead eyebrow="RECENT WORK" title="Applications needing attention" action={<a className="officer-link" href="/officer/queue">Open full queue →</a>} />{recent?.items.length ? <QueueTable items={recent.items} /> : <Empty message="No applications are waiting in the officer queue." />}</section>
  </>
}

function QueuePage({ escalations = false }: { escalations?: boolean }) {
  const [items, setItems] = useState<QueueItem[]>([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [risk, setRisk] = useState('ALL')
  const [status, setStatus] = useState(escalations ? 'ESCALATED' : 'ALL')
  const [sla, setSla] = useState('ALL')
  const [sort, setSort] = useState('SUBMITTED')
  const [direction, setDirection] = useState('DESC')
  const [error, setError] = useState('')
  const refresh = useCallback(() => {
    const params = new URLSearchParams({ sort_by: sort, sort_order: direction, limit: '100' })
    if (search.trim()) params.set('search', search.trim())
    if (risk !== 'ALL') params.set('risk', risk)
    if (status !== 'ALL') params.set('status', status)
    if (sla !== 'ALL') params.set('sla', sla)
    void api<QueueResponse>(`/api/officer/queue?${params}`).then((result) => { setItems(result.items); setTotal(result.total); setError('') }).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Unable to load the application queue.'))
  }, [direction, risk, search, sla, sort, status])
  useEffect(() => { refresh() }, [refresh])
  return <>
    <PageHeading title={escalations ? 'Escalated applications' : 'Application queue'} description="Search and prioritize department approval work using risk, status, and SLA filters." />
    {error && <ErrorBox message={error} />}
    <section className="officer-panel queue-panel"><PanelHead eyebrow="REVIEW WORKLIST" title={`${total} approval${total === 1 ? '' : 's'}`} />
      <div className="queue-filters">
        <label className="queue-search">Search<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Application, company, applicant…" /></label>
        <label>Risk<select value={risk} onChange={(event) => setRisk(event.target.value)}><option value="ALL">All risks</option><option value="HIGH">High</option><option value="MEDIUM">Medium</option><option value="LOW">Low</option></select></label>
        <label>Status<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="ALL">All statuses</option>{['PENDING', 'IN_REVIEW', 'DOCUMENT_CORRECTION', 'INSPECTION_REQUIRED', 'ESCALATED', 'NOT_STARTED'].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
        <label>SLA<select value={sla} onChange={(event) => setSla(event.target.value)}><option value="ALL">All SLA</option><option value="WARNING">Warning</option><option value="BREACHED">Breached</option><option value="ESCALATED">Escalated</option><option value="ON_TRACK">On track</option><option value="BLOCKED">Blocked</option></select></label>
        <label>Sort by<select value={sort} onChange={(event) => setSort(event.target.value)}><option value="SUBMITTED">Submission date</option><option value="RISK">Risk</option><option value="SLA">SLA due</option><option value="COMPANY">Company</option><option value="STATUS">Status</option></select></label>
        <label>Order<select value={direction} onChange={(event) => setDirection(event.target.value)}><option value="DESC">Descending</option><option value="ASC">Ascending</option></select></label>
      </div>
      {items.length ? <QueueTable items={items} /> : <Empty message="No approval records match these filters." />}
    </section>
  </>
}

function QueueTable({ items }: { items: QueueItem[] }) {
  return <div className="officer-table-scroll"><table className="officer-table"><thead><tr><th>APPLICATION</th><th>COMPANY / APPLICANT</th><th>DEPARTMENT</th><th>RISK</th><th>STATUS</th><th>SLA</th><th>SUBMITTED</th><th /></tr></thead><tbody>{items.map((item) => <tr key={item.approval_id}>
    <td><strong>{item.application_number}</strong><small>{item.industry_type ?? 'Industry not selected'}</small></td><td>{item.company_name}<small>{item.applicant_name}</small></td><td>{item.department_name}</td><td><RiskBadge value={item.risk_tier} /></td><td><StatusBadge value={item.approval_status} /></td><td><SlaBadge value={item.sla_status} overdue={item.days_overdue} /></td><td>{dateOnly(item.submitted_at)}</td><td><a className="officer-review-link" href={`/officer/approvals/${item.approval_id}`}>Review →</a></td>
  </tr>)}</tbody></table></div>
}

function ReviewPage({ approvalId }: { approvalId: number }) {
  const [data, setData] = useState<ApprovalDetail | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [remark, setRemark] = useState('')
  const [reason, setReason] = useState('')
  const [correction, setCorrection] = useState('')
  const [inspectionDate, setInspectionDate] = useState('')
  const [inspectionLocation, setInspectionLocation] = useState('')
  const [inspectionInstructions, setInspectionInstructions] = useState('')
  const [notice, setNotice] = useState('')
  const refresh = useCallback(async () => {
    const detail = await api<ApprovalDetail>(`/api/officer/approvals/${approvalId}`)
    const joints = await api<{ items: Inspection[] }>('/api/officer/inspections?inspection_type=JOINT')
    detail.inspections = [...detail.inspections, ...joints.items.filter((item) => item.application_id === Number(detail.application.id)
      && item.approval_ids?.includes(detail.approval.id))]
    setData(detail)
  }, [approvalId])
  useEffect(() => { void refresh().catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Unable to load application review.')) }, [refresh])

  async function postAction(path: string, body?: unknown) {
    if (!data) return
    setBusy(true); setError(''); setNotice('')
    try {
      if (!path.endsWith('/start-review') && ['PENDING', 'INSPECTION_REQUIRED', 'ESCALATED'].includes(data.approval.status)) {
        await api(`/api/approvals/${approvalId}/start-review`, { method: 'POST' })
        await refresh()
      }
      const result = await api<{ status?: string }>(path, { method: 'POST', ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
      setNotice(result.status ? `Action saved. Approval status: ${label(result.status)}.` : 'Action saved.')
      await refresh()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The action could not be saved.') }
    finally { setBusy(false) }
  }
  function remarkSubmit(event: FormEvent) { event.preventDefault(); if (!remark.trim()) return; void postAction(`/api/officer/approvals/${approvalId}/remarks`, { message: remark }).then(() => setRemark('')) }
  function rejectSubmit(event: FormEvent) { event.preventDefault(); if (!reason.trim()) return; void postAction(`/api/approvals/${approvalId}/reject`, { reason }).then(() => setReason('')) }
  function correctionSubmit(event: FormEvent) { event.preventDefault(); if (!correction.trim()) return; void postAction(`/api/approvals/${approvalId}/request-correction`, { message: correction }).then(() => setCorrection('')) }
  function inspectionSubmit(event: FormEvent) {
    event.preventDefault()
    if (!inspectionDate || !inspectionLocation.trim()) return
    void postAction(`/api/officer/approvals/${approvalId}/inspections`, {
      inspection_type: 'SINGLE', scheduled_at: new Date(inspectionDate).toISOString(),
      location: inspectionLocation, instructions: inspectionInstructions || null,
    }).then(() => { setInspectionDate(''); setInspectionLocation(''); setInspectionInstructions('') })
  }

  if (error && !data) return <><PageHeading title="Application review" description="The review record could not be loaded."/><ErrorBox message={error}/></>
  if (!data) return <div className="loading-panel">Loading application and department records…</div>
  const app = data.application
  const assessment = data.risk_assessment
  const editable = data.approval.status === 'IN_REVIEW'
  const canStartReview = ['PENDING', 'INSPECTION_REQUIRED', 'ESCALATED'].includes(data.approval.status)
  return <>
    <PageHeading title={`Review ${String(app.application_number ?? '')}`} description={`${data.approval.department_name} · ${String(app.company_name ?? 'Company not provided')}`} action={<SlaBadge value={data.approval.sla.sla_status} overdue={data.approval.sla.days_overdue}/>}/>
    {error && <ErrorBox message={error}/ >}{notice && <div className="officer-notice" role="status">{notice}</div>}
    <div className="review-grid">
      <div className="review-main-column">
        <section className="officer-panel review-panel"><PanelHead eyebrow="APPLICANT" title="Applicant information"/><InfoGrid items={[["Name", data.applicant.name], ["Email", data.applicant.email], ["Phone", data.applicant.phone]]}/></section>
        <section className="officer-panel review-panel"><PanelHead eyebrow="APPLICATION" title="Project information"/><InfoGrid items={[["Company", app.company_name], ["Industry", app.industry_type], ["Project type", app.project_type], ["Project description", app.project_description], ["Investment", app.investment_amount == null ? null : `₹ ${Number(app.investment_amount).toLocaleString('en-IN')}`], ["Employees", app.number_of_employees], ["Built-up area", app.built_up_area], ["Power requirement", app.power_requirement], ["Water requirement", app.water_requirement], ["Location", app.project_location], ["Land details", app.land_details], ["MIDC area", app.midc_area === true ? String(app.midc_area_name ?? 'Yes') : app.midc_area === false ? 'No' : null], ["Pollution category", app.pollution_category], ["Hazardous materials", app.hazardous_materials === true ? String(app.hazardous_materials_details ?? 'Yes') : app.hazardous_materials === false ? 'No' : null], ["PAN / GSTIN / CIN", [app.pan, app.gstin, app.cin].filter(Boolean).join(' · ') || null]]}/></section>
        <section className="officer-panel review-panel"><PanelHead eyebrow="RISK ASSESSMENT" title="Risk factors" action={<RiskBadge value={String(assessment.risk_tier ?? 'UNASSESSED')}/>}/><div className="risk-summary-row"><strong>{assessment.risk_score == null ? 'Not assessed' : `${assessment.risk_score}/100`}</strong><span>{String(assessment.explanation ?? 'Risk tier reflects the saved application assessment.')}</span></div>{Array.isArray(assessment.factor_breakdown) && <div className="factor-list">{(assessment.factor_breakdown as Array<Record<string, unknown>>).map((factor, index) => <div className="factor-row" key={`${String(factor.key ?? factor.label)}-${index}`}><strong>{String(factor.label ?? factor.key)}</strong><span>{String(factor.value ?? '')}</span><small>{String(factor.explanation ?? '')}</small></div>)}</div>}</section>
        <section className="officer-panel review-panel"><PanelHead eyebrow="DOCUMENTS & OCR" title={`Uploaded documents · ${data.documents.length}`}/>{data.documents.length ? data.documents.map((doc) => <details className="officer-document" key={doc.id}><summary><span><strong>{doc.file_name}</strong><small>{label(doc.document_type)} · {(doc.size_bytes / 1024).toFixed(0)} KB</small></span><StatusBadge value={doc.status}/></summary><div className="ocr-fields">{Object.entries(doc.ocr_fields).map(([key, value]) => <p key={key}><strong>{label(key)}:</strong> {value}</p>)}</div><pre>{doc.ocr_text || 'No OCR text was extracted for this file.'}</pre></details>) : <Empty message="No documents are attached to this application."/>}</section>
        <section className="officer-panel review-panel"><PanelHead eyebrow="PRE-VALIDATION" title={`Checks · ${label(data.prevalidation.overall_status)}`}/>{data.prevalidation.issues.length ? <ul className="validation-list">{data.prevalidation.issues.map((issue, index) => <li key={`${issue.document_label}-${index}`}><StatusBadge value={issue.status}/><span><strong>{issue.document_label}</strong><small>{issue.message}</small></span></li>)}</ul> : <Empty message="No pre-validation issues were recorded."/>}</section>
        <section className="officer-panel review-panel"><PanelHead eyebrow="DEPARTMENT ROUTING" title="Other department statuses"/>{data.other_department_statuses.map((row) => <div className="department-row" key={row.department_code}><span><strong>{row.department_name}</strong><small>{row.is_required ? 'Required' : 'Not required'}</small></span><StatusBadge value={row.status}/></div>)}</section>
        <section className="officer-panel review-panel"><PanelHead eyebrow="INSPECTION DETAILS" title="Scheduled inspections"/>{data.inspections.length ? data.inspections.map((inspection) => <div className="inspection-card" key={inspection.id}><strong>{inspection.inspection_type === 'JOINT' ? 'Joint inspection' : 'Inspection'} · {dateLabel(inspection.scheduled_at)}</strong><span>{inspection.location}</span><small>{inspection.instructions || 'No additional instructions.'} · {label(inspection.status)}</small></div>) : <Empty message="No inspection has been scheduled."/>}</section>
        <section className="officer-panel review-panel"><PanelHead eyebrow="REVIEW HISTORY" title="Audit history"/>{data.audit_history.length ? <ol className="officer-history">{[...data.audit_history].reverse().map((event) => <li key={event.id}><span className="history-dot"/><div><strong>{label(event.action)}</strong><p>{event.message || [event.from_status, event.to_status].filter(Boolean).map(label).join(' → ')}</p><small>{event.actor} · {dateLabel(event.created_at)}</small></div></li>)}</ol> : <Empty message="No review actions have been recorded."/>}</section>
      </div>
      <aside className="review-action-column">
        <section className="officer-panel action-panel"><PanelHead eyebrow="DEPARTMENT DECISION" title={label(data.approval.status)}/>{canStartReview ? <button className="officer-button primary" disabled={busy} onClick={() => void postAction(`/api/approvals/${approvalId}/start-review`)}>Start review</button> : null}
          {editable ? <>
            <button className="officer-button success" disabled={busy} onClick={() => void postAction(`/api/approvals/${approvalId}/approve`)}>Approve application</button>
            <form className="officer-action-form" onSubmit={rejectSubmit}><label>Reject with reason<textarea value={reason} onChange={(event) => setReason(event.target.value)} minLength={1} required placeholder="Explain the reason for rejection"/></label><button className="officer-button danger" disabled={busy || !reason.trim()}>Reject</button></form>
            <form className="officer-action-form" onSubmit={correctionSubmit}><label>Request correction<textarea value={correction} onChange={(event) => setCorrection(event.target.value)} minLength={1} required placeholder="Describe what the applicant needs to correct"/></label><button className="officer-button secondary" disabled={busy || !correction.trim()}>Request correction</button></form>
            <form className="officer-action-form" onSubmit={inspectionSubmit}><label>Schedule inspection<span className="action-hint">Department inspections can be scheduled here. Use Joint Inspections in the sidebar to coordinate multiple departments.</span></label><label>Date and time<input type="datetime-local" value={inspectionDate} onChange={(event) => setInspectionDate(event.target.value)} required/></label><label>Location<input value={inspectionLocation} onChange={(event) => setInspectionLocation(event.target.value)} required minLength={3} placeholder="Inspection site address"/></label><label>Instructions<textarea value={inspectionInstructions} onChange={(event) => setInspectionInstructions(event.target.value)} placeholder="Optional inspection notes"/></label><button className="officer-button secondary" disabled={busy || !inspectionDate || !inspectionLocation.trim()}>Schedule inspection</button></form>
          </> : !canStartReview && <p className="action-hint">Actions are available once this department has started its review.</p>}
          <form className="officer-action-form remark-form" onSubmit={remarkSubmit}><label>Add internal remark<textarea value={remark} onChange={(event) => setRemark(event.target.value)} required placeholder="Visible to officers only"/></label><button className="officer-button secondary" disabled={busy || !remark.trim()}>Add remark</button></form>
        </section>
        <section className="officer-panel action-panel"><PanelHead eyebrow="PREVIOUS REMARKS" title="Officer notes"/>{data.previous_remarks.length ? data.previous_remarks.map((item) => <div className="previous-remark" key={item.id}><p>{item.message}</p><small>{item.author} · {dateLabel(item.created_at)}</small></div>) : <p className="action-hint">No officer remarks recorded.</p>}</section>
      </aside>
    </div>
  </>
}

function InspectionList({ type }: { type: 'SINGLE' | 'JOINT' }) {
  const [data, setData] = useState<{ total: number; items: Inspection[] } | null>(null)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  useEffect(() => { void api<{ total: number; items: Inspection[] }>(`/api/officer/inspections?inspection_type=${type}`).then(setData).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Unable to load inspections.')) }, [type, reload])
  return <><PageHeading title={type === 'JOINT' ? 'Joint inspections' : 'Inspections'} description="Schedule site visits, update findings, attach photos, and record recommendations."/>{error && <ErrorBox message={error}/ >}{errorMessage && <ErrorBox message={errorMessage}/ >}{type === 'JOINT' && <section className="officer-panel"><PanelHead eyebrow="COORDINATED SITE VISIT" title="Schedule a joint inspection"/><JointInspectionForm onError={setErrorMessage} onCreated={() => { setErrorMessage(''); setReload((value) => value + 1) }}/></section>}<section className="officer-panel"><PanelHead eyebrow="INSPECTION REGISTER" title={`${data?.total ?? 0} scheduled`}/>{data?.items.length ? <div className="officer-table-scroll"><table className="officer-table"><thead><tr><th>APPLICATION</th><th>DEPARTMENT</th><th>DATE & TIME</th><th>SITE</th><th>STATUS</th><th /></tr></thead><tbody>{data.items.map((item) => <tr key={item.id}><td><strong>{item.application_number}</strong></td><td>{item.department_name}<small>{item.participants?.map((p) => p.department_name).join(' · ') || label(item.inspection_type)}</small></td><td>{dateLabel(item.scheduled_at)}</td><td>{item.site || item.location}</td><td><StatusBadge value={item.status}/></td><td><button className="officer-review-link as-button" onClick={() => setSelected(item.id)}>Manage</button>{item.approval_id && <a className="officer-review-link" href={`/officer/approvals/${item.approval_id}`}> · Review →</a>}</td></tr>)}</tbody></table></div> : data && <Empty message="No inspections have been scheduled."/>}</section>{selected !== null && <InspectionEditor inspectionId={selected} kind={type} onClose={() => setSelected(null)} onSaved={() => { setSelected(null); setReload((value) => value + 1) }}/>}</>
}

function JointInspectionForm({ onCreated, onError }: { onCreated: () => void; onError: (message: string) => void }) {
  const [applicationId, setApplicationId] = useState('')
  const [approvals, setApprovals] = useState<Array<{ id: number; department_name: string; status: string; is_required: boolean }>>([])
  const [officers, setOfficers] = useState<Array<{ id: number; name: string; department_name: string | null }>>([])
  const [assignments, setAssignments] = useState<Record<number, number>>({})
  const [selected, setSelected] = useState<number[]>([])
  const [date, setDate] = useState('')
  const [site, setSite] = useState('')
  const [instructions, setInstructions] = useState('')
  const [busy, setBusy] = useState(false)
  async function loadApprovals() {
    onError('')
    try {
      const result = await api<{ approvals: Array<{ id: number; department_name: string; status: string; is_required: boolean }> }>(`/api/applications/${applicationId}/approvals`)
      setApprovals(result.approvals.filter((item) => item.is_required && ['PENDING', 'IN_REVIEW', 'INSPECTION_REQUIRED', 'ESCALATED'].includes(item.status)))
      const roster = await api<{ items: Array<{ id: number; name: string; department_name: string | null }> }>('/api/officer/inspection-officers')
      setOfficers(roster.items)
      setSelected([])
    } catch (caught) { onError(caught instanceof Error ? caught.message : 'Could not load department approvals.') }
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); onError('')
    try {
      await api('/api/officer/joint-inspections', { method: 'POST', body: JSON.stringify({ application_id: Number(applicationId), approval_ids: selected, scheduled_at: new Date(date).toISOString(), site, instructions: instructions || null, officer_assignments: assignments }) })
      setApplicationId(''); setApprovals([]); setOfficers([]); setSelected([]); setAssignments({}); setDate(''); setSite(''); setInstructions(''); onCreated()
    } catch (caught) { onError(caught instanceof Error ? caught.message : 'Could not schedule joint inspection.') }
    finally { setBusy(false) }
  }
  return <form className="inspection-editor-form" onSubmit={submit}><div className="joint-load-row"><label>Application ID<input type="number" min="1" required value={applicationId} onChange={(event) => setApplicationId(event.target.value)}/></label><button className="officer-button secondary" type="button" disabled={!applicationId} onClick={() => void loadApprovals()}>Load departments</button></div>{approvals.length > 0 && <div className="joint-departments">{approvals.map((approval) => <div className="joint-department-row" key={approval.id}><label><input type="checkbox" checked={selected.includes(approval.id)} onChange={(event) => { setSelected((current) => event.target.checked ? [...current, approval.id] : current.filter((id) => id !== approval.id)); if (!event.target.checked) setAssignments((current) => { const next = { ...current }; delete next[approval.id]; return next }) }}/><span><strong>{approval.department_name}</strong><small>{label(approval.status)}</small></span></label>{selected.includes(approval.id) && <select aria-label={`Officer for ${approval.department_name}`} value={assignments[approval.id] ?? ''} onChange={(event) => setAssignments((current) => { const next = { ...current }; if (event.target.value) next[approval.id] = Number(event.target.value); else delete next[approval.id]; return next })}><option value="">Leave officer unassigned</option>{officers.map((officer) => <option key={officer.id} value={officer.id}>{officer.name}{officer.department_name ? ` · ${officer.department_name}` : ''}</option>)}</select>}</div>)}</div>}<div className="inspection-editor-grid"><label>Date and time<input type="datetime-local" required value={date} onChange={(event) => setDate(event.target.value)}/></label><label>Site<input required minLength={3} value={site} onChange={(event) => setSite(event.target.value)}/></label></div><label>Instructions<textarea value={instructions} onChange={(event) => setInstructions(event.target.value)}/></label><button className="officer-button primary" disabled={busy || selected.length < 2 || !date || !site.trim()}>{busy ? 'Scheduling…' : `Schedule joint inspection · ${selected.length} departments`}</button></form>
}

function InspectionEditor({ inspectionId, kind, onClose, onSaved }: { inspectionId: number; kind: 'SINGLE' | 'JOINT'; onClose: () => void; onSaved: () => void }) {
  const [data, setData] = useState<Inspection | null>(null)
  const [status, setStatus] = useState('SCHEDULED')
  const [findings, setFindings] = useState('')
  const [remarks, setRemarks] = useState('')
  const [recommendation, setRecommendation] = useState('')
  const [checklist, setChecklist] = useState('[]')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const route = kind === 'JOINT' ? `/api/officer/joint-inspections/${inspectionId}` : `/api/officer/inspections/${inspectionId}`
  useEffect(() => { void api<Inspection>(route).then((record) => { setData(record); setStatus(record.status); setFindings(record.findings || ''); setRemarks(record.remarks || ''); setRecommendation(record.recommendation || ''); setChecklist(JSON.stringify(record.checklist || [], null, 2)) }).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Unable to load inspection.')) }, [route])
  async function save(event: FormEvent) {
    event.preventDefault(); setError(''); setBusy(true)
    try {
      const parsed = JSON.parse(checklist)
      if (!Array.isArray(parsed)) throw new Error('Checklist must be a JSON array.')
      await api(route, { method: 'PATCH', body: JSON.stringify({ status, findings, remarks, recommendation, checklist: parsed }) })
      onSaved()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to save inspection.') }
    finally { setBusy(false) }
  }
  async function upload(event: ChangeEvent<HTMLInputElement>) {
    if (!event.target.files?.length) return
    const token = localStorage.getItem('mahaclear_access_token')
    const form = new FormData(); Array.from(event.target.files).forEach((file) => form.append('files', file))
    const photoRoute = kind === 'JOINT' ? `/api/officer/joint-inspections/${inspectionId}/photos` : `/api/officer/inspections/${inspectionId}/photos`
    setBusy(true); setError('')
    try { const response = await fetch(photoRoute, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form }); const body = await response.json().catch(() => ({})); if (!response.ok) throw new Error(body.detail || 'Photo upload failed.'); const record = await api<Inspection>(route); setData(record) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Photo upload failed.') }
    finally { setBusy(false); event.target.value = '' }
  }
  return <section className="officer-panel inspection-editor"><PanelHead eyebrow={kind === 'JOINT' ? 'JOINT INSPECTION' : 'DEPARTMENT INSPECTION'} title={data ? `${data.application_number} · ${data.site || data.location}` : 'Inspection details'} action={<button className="officer-button secondary" onClick={onClose}>Close</button>}/>{error && <ErrorBox message={error}/ >}{data && <><div className="inspection-participants">{data.participants?.map((person) => <span key={person.approval_id}>{person.department_name} · {person.officer || 'Officer unassigned'}</span>)}</div><form className="inspection-editor-form" onSubmit={save}><div className="inspection-editor-grid"><label>Status<select value={status} onChange={(event) => setStatus(event.target.value)}>{['SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label><label>Checklist JSON<textarea value={checklist} onChange={(event) => setChecklist(event.target.value)} rows={3}/></label></div><label>Findings<textarea value={findings} onChange={(event) => setFindings(event.target.value)}/></label><label>Remarks<textarea value={remarks} onChange={(event) => setRemarks(event.target.value)}/></label><label>Recommendation {status === 'COMPLETED' && <span className="required-label">REQUIRED TO COMPLETE</span>}<textarea value={recommendation} onChange={(event) => setRecommendation(event.target.value)} required={status === 'COMPLETED'}/></label><button className="officer-button primary" disabled={busy}>{busy ? 'Saving…' : 'Save inspection record'}</button></form><label className="inspection-photo-upload">Upload photos<input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => void upload(event)}/><small>JPEG, PNG, or WebP · up to 10 files per upload</small></label><div className="inspection-photo-list">{data.photos?.map((photo, index) => <AuthenticatedDownload key={`${photo.file_name}-${index}`} href={photo.download_url || (kind === 'JOINT' ? `/api/officer/joint-inspections/${inspectionId}/photos/${index}` : `/api/officer/inspections/${inspectionId}/photos/${index}`)} fileName={photo.file_name}>{photo.file_name} ↗</AuthenticatedDownload>)}</div></>}</section>
}

function DocumentsPage() {
  const [data, setData] = useState<{ total: number; items: Array<Record<string, string | number>> } | null>(null)
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  useEffect(() => { const params = new URLSearchParams(); if (search.trim()) params.set('search', search.trim()); void api<{ total: number; items: Array<Record<string, string | number>> }>(`/api/officer/documents?${params}`).then(setData).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Unable to load documents.')) }, [search])
  return <><PageHeading title="Application documents" description="Uploaded files and their saved processing status."/><section className="officer-panel"><PanelHead eyebrow="DOCUMENT REGISTER" title={`${data?.total ?? 0} files`}/><div className="queue-filters document-search"><label className="queue-search">Search<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="File, company, application…"/></label></div>{error && <ErrorBox message={error}/ >}{data?.items.length ? <div className="officer-table-scroll"><table className="officer-table"><thead><tr><th>APPLICATION</th><th>DOCUMENT</th><th>TYPE</th><th>FILE STATUS</th><th>UPLOADED</th><th /></tr></thead><tbody>{data.items.map((item) => <tr key={Number(item.id)}><td>{String(item.application_number)}<small>{String(item.company_name ?? '')}</small></td><td>{String(item.file_name)}</td><td>{label(String(item.document_type))}</td><td><StatusBadge value={String(item.status)}/></td><td>{dateLabel(String(item.uploaded_at))}</td><td>{item.approval_id ? <a className="officer-review-link" href={`/officer/approvals/${String(item.approval_id)}`}>Open review →</a> : '—'}</td></tr>)}</tbody></table></div> : data && <Empty message="No application documents found."/>}</section></>
}

function ReportsPage() {
  const [data, setData] = useState<{ total_active_approvals: number; by_status: Record<string, number>; by_risk: Record<string, number>; sla_breached: number } | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { void api<typeof data>('/api/officer/reports').then((result) => setData(result)).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Unable to load reports.')) }, [])
  return <><PageHeading title="Review reports" description="Live counts calculated from current approval and risk records."/>{error && <ErrorBox message={error}/>}<section className="officer-metrics report-metrics"><Metric title="ACTIVE APPROVALS" value={data?.total_active_approvals ?? 0}/><Metric title="SLA BREACHED" value={data?.sla_breached ?? 0}/></section><div className="critical-detail-grid"><section className="officer-panel"><PanelHead eyebrow="WORKLOAD" title="Approvals by status"/>{Object.entries(data?.by_status ?? {}).map(([key, value]) => <div className="department-row" key={key}><strong>{label(key)}</strong><span>{value}</span></div>)}</section><section className="officer-panel"><PanelHead eyebrow="PORTFOLIO" title="Approvals by risk tier"/>{Object.entries(data?.by_risk ?? {}).map(([key, value]) => <div className="department-row" key={key}><strong>{label(key)}</strong><span>{value}</span></div>)}</section></div></>
}

function ProfilePage({ officer }: { officer: Officer }) {
  const [profile, setProfile] = useState<Record<string, string | number | null> | null>(null)
  useEffect(() => { void api<Record<string, string | number | null>>('/api/officer/profile').then(setProfile) }, [])
  return <><PageHeading title="Officer profile" description="Your authenticated department account."/><section className="officer-panel profile-panel"><span className="profile-avatar">{officer.full_name.slice(0, 1).toUpperCase()}</span><InfoGrid items={[["Name", profile?.name ?? officer.full_name], ["Email", profile?.email ?? officer.email], ["Role", profile?.role ?? officer.role], ["Department", profile?.department], ["Organization", profile?.company]]}/></section></>
}

function InfoGrid({ items }: { items: Array<[string, unknown]> }) {
  return <dl className="review-info-grid">{items.map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value === null || value === undefined || value === '' ? '—' : String(value)}</dd></div>)}</dl>
}
function PanelHead({ eyebrow, title, action }: { eyebrow: string; title: string; action?: ReactNode }) { return <div className="officer-panel-head"><div><span className="card-kicker">{eyebrow}</span><h2>{title}</h2></div>{action}</div> }
function StatusBadge({ value }: { value: string }) { return <span className={`officer-status ${value.toLowerCase()}`}>{label(value)}</span> }
function RiskBadge({ value }: { value: string | null }) { return <span className={`officer-risk ${String(value ?? 'UNASSESSED').toLowerCase()}`}>{label(value ?? 'UNASSESSED')}</span> }
function SlaBadge({ value, overdue = 0 }: { value: string; overdue?: number }) { return <span className={`officer-sla ${value.toLowerCase()}`}>{value === 'BREACHED' || value === 'ESCALATED' ? `${overdue}d overdue` : label(value)}</span> }
function Empty({ message }: { message: string }) { return <div className="officer-empty">{message}</div> }
function ErrorBox({ message }: { message: string }) { return <div className="applicant-error" role="alert">{message}</div> }
function Metric({ title, value }: { title: string; value: number }) { return <article className="officer-metric"><span className="card-kicker">{title}</span><strong>{value}</strong></article> }
