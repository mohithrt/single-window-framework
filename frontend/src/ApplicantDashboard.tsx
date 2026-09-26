import { apiUrl } from './apiBase'
import { useEffect, useState } from 'react'
import type { ApplicationsResponse } from './applicationTypes'
import { formatDate } from './applicationTypes'

type ApplicantUser = { role: string }
type DashboardApplication = {
  id: number; application_number: string; company_name: string | null; industry_type: string | null
  status: string; current_department_name: string | null; sla_overdue: boolean
  expected_completion_at: string | null; action_title: string; action_detail: string; action_href: string
  approvals_total: number; approvals_approved: number; pending_departments: string[]
  latest_update: { action: string; message: string | null; created_at: string } | null
}
type ApplicantDashboardData = {
  applications: DashboardApplication[]
  summary: { total: number; active: number; unread_notifications: number; status_counts: Record<string, number> }
  focus_application_id: number | null
}
type RequirementSnapshot = {
  approvals: Array<{ department: string; approval_name: string; applicable: boolean; status: string; reason: string }>
  required_documents: Array<{ document_type: string; document_name: string; status: string; reason: string; status_reason: string }>
  documents: Array<{ document_type: string; document_name: string; required: boolean; requirement_type: string; status: string; reason: string }>
  counts: { required: number; uploaded: number; valid: number; missing: number; needs_correction: number }
  completion_percentage: number; submission_ready: boolean; disclaimer: string
}

async function responseMessage(response: Response): Promise<string> {
  const body = await response.json().catch(() => ({}))
  if (typeof body.detail === 'string') return body.detail
  if (body.detail?.message) return body.detail.message
  return 'Unable to load your applications. Please try again.'
}

export default function ApplicantDashboard() {
  const [data, setData] = useState<ApplicationsResponse | null>(null)
  const [dashboard, setDashboard] = useState<ApplicantDashboardData | null>(null)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const [requirements, setRequirements] = useState<RequirementSnapshot | null>(null)
  const [requirementsError, setRequirementsError] = useState('')

  useEffect(() => {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    const headers = { Authorization: `Bearer ${token}` }
    async function load() {
      try {
        const me = await fetch(apiUrl('/api/auth/me'), { headers })
        if (!me.ok) throw new Error('Your session has expired. Sign in again.')
        const user: ApplicantUser = await me.json()
        if (user.role !== 'APPLICANT') {
          const dashboard = user.role === 'OFFICER' ? '/officer' : '/admin'
          window.location.assign(dashboard)
          return
        }
        const [response, dashboardResponse] = await Promise.all([
          fetch(apiUrl('/api/applications'), { headers }),
          fetch(apiUrl('/api/applicant/dashboard'), { headers }),
        ])
        if (!response.ok) throw new Error(await responseMessage(response))
        if (!dashboardResponse.ok) throw new Error(await responseMessage(dashboardResponse))
        const [applications, attention] = await Promise.all([response.json(), dashboardResponse.json()])
        setData(applications)
        setDashboard(attention)
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : 'Unable to load your applications.')
        if (caught instanceof Error && caught.message.includes('session has expired')) {
          localStorage.removeItem('mahaclear_access_token')
        }
      }
    }
    void load()
  }, [])

  async function startApplication() {
    setCreating(true)
    try {
      const token = localStorage.getItem('mahaclear_access_token')
      const response = await fetch(apiUrl('/api/applications'), {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!response.ok) throw new Error(await responseMessage(response))
      const application = await response.json()
      window.location.assign(`/applicant/applications/${application.id}/edit`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not start a new application.')
      setCreating(false)
    }
  }

  const focusApplication = dashboard?.applications.find(application => application.id === dashboard.focus_application_id)

  useEffect(() => {
    if (!focusApplication) { setRequirements(null); return }
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) return
    let cancelled = false
    setRequirements(null)
    setRequirementsError('')
    fetch(apiUrl(`/api/applications/${focusApplication.id}/requirements`), { headers: { Authorization: `Bearer ${token}` } })
      .then(async response => { if (!response.ok) throw new Error(await responseMessage(response)); return response.json() })
      .then(payload => { if (!cancelled) setRequirements(payload as RequirementSnapshot) })
      .catch(caught => { if (!cancelled) setRequirementsError(caught instanceof Error ? caught.message : 'Could not load requirements.') })
    return () => { cancelled = true }
  }, [focusApplication?.id])

  return (
    <div className="applicant-shell">
      <header className="applicant-topbar">
        <a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a>
        <div className="applicant-topbar-spacer" aria-hidden="true" />
        <button className="applicant-signout" type="button" onClick={() => { localStorage.removeItem('mahaclear_access_token'); window.location.assign('/login') }}><span className="signout-icon" aria-hidden="true">↪</span><strong>Sign out</strong></button>
      </header>
      <aside className="applicant-sidebar">
        <div className="workspace-nav-label">APPLICANT WORKSPACE</div>
        <a className="side-link" href="/applicant/documents"><span>▣</span> Documents</a>
        <a className="side-link" href="/applicant/permissions"><span>◎</span> Permissions &amp; fees</a>
        <a className="side-link" href="/notifications"><span>◉</span> Verification &amp; updates</a>
        <a className="side-link" href="/applicant/applications"><span>▤</span> My applications</a>
        <div className="sidebar-note"><span className="sidebar-note-mark">✳</span><strong>One window.<br />Every approval.</strong><small>North-Star · SIH 2026</small></div>
        <div className="sidebar-bottom">MAHACLEAR-AI <span>·</span> APPLICANT</div>
      </aside>
      <main className="applicant-main">
        <div className="breadcrumb">APPLICANT WORKSPACE <span>/</span> DASHBOARD</div>
        <div className="applicant-heading">
          <div><span className="eyebrow"><i /> YOUR APPROVAL WORKSPACE</span><h1>Applicant dashboard</h1><p>Track your applications and continue where you left off.</p></div>
          <button className="primary-button new-application-button" onClick={startApplication} disabled={creating}>{creating ? 'Preparing draft…' : 'New application'} <span>＋</span></button>
        </div>
        {error && <div className="applicant-error" role="alert">{error} <button onClick={() => window.location.reload()}>Retry</button></div>}
        {!data ? (!error ? <div className="loading-panel" role="status">Loading your applications…</div> : null) : (
          <>
            <section className="applicant-focus-grid applicant-context-grid" aria-label="What needs attention">
              <article className={focusApplication?.status === 'ACTION_REQUIRED' ? 'attention' : ''}>
                <span>APPLICATION NEEDING ATTENTION</span>
                <strong>{focusApplication ? `${focusApplication.application_number} · ${focusApplication.company_name || 'Company details pending'}` : 'Nothing needs your attention'}</strong>
                <small>{dashboard?.summary.total ?? 0} applications in your register · {dashboard?.summary.active ?? 0} active</small>
              </article>
              <article className={focusApplication?.sla_overdue ? 'delayed' : focusApplication?.status === 'ACTION_REQUIRED' ? 'attention' : ''}>
                <span>YOUR NEXT ACTION</span>
                <strong>{focusApplication?.action_title || 'Start an application when ready'}</strong>
                <small>{focusApplication?.action_detail || 'Applications you create will appear in your register.'}</small>
                {focusApplication && <a className="context-link" href={focusApplication.action_href}>Open this application →</a>}
              </article>
              <article className={focusApplication?.sla_overdue ? 'delayed' : ''}>
                <span>{focusApplication?.sla_overdue ? 'DEPARTMENT PAST TARGET' : 'CURRENT REVIEW / BLOCKER'}</span>
                <strong>{focusApplication?.current_department_name || 'No department review active'}</strong>
                <small>{focusApplication?.pending_departments.length ? `${focusApplication.pending_departments.join(' · ')} in the approval path` : 'No pending department approvals.'}</small>
              </article>
              <article>
                <span>ESTIMATED COMPLETION</span>
                <strong>{focusApplication?.expected_completion_at ? formatDate(focusApplication.expected_completion_at) : 'Not scheduled yet'}</strong>
                <small>{focusApplication ? `${focusApplication.approvals_approved} of ${focusApplication.approvals_total} required approvals complete · ${focusApplication.application_number}` : 'A completion estimate is set after the workflow is scheduled.'}</small>
              </article>
            </section>
            {focusApplication && <section className="requirements-dashboard" aria-labelledby="requirements-heading">
              <div className="requirements-dashboard-head"><div><span className="card-kicker">APPLICATION READINESS · {focusApplication.application_number}</span><h2 id="requirements-heading">Your Required Approvals &amp; Documents</h2><p>Indicative requirements based on the information entered for this application.</p></div><a className="secondary-button button-link" href={`/applicant/applications/${focusApplication.id}/prevalidation`}>Manage documents →</a></div>
              {!requirements && !requirementsError && <p role="status" className="requirements-loading">Loading current requirements…</p>}
              {requirementsError && <p role="alert" className="requirements-error">{requirementsError}</p>}
              {requirements && <>
                <div className="requirements-readiness"><div><strong>Documents</strong><span>{requirements.counts.valid} / {requirements.counts.required} valid</span></div><progress max="100" value={requirements.completion_percentage} aria-label={`Document completion ${requirements.completion_percentage}%`}/><small>{requirements.counts.missing} missing · {requirements.counts.needs_correction} need correction · {requirements.completion_percentage}% complete</small></div>
                <div className="requirements-dashboard-grid"><div><h3>Required documents</h3><ul>{requirements.required_documents.map(item => <li key={item.document_type} className={`requirement-status requirement-${item.status.toLowerCase()}`}><span aria-hidden="true">{item.status === 'VALID' ? '✓' : item.status === 'MISSING' ? '!' : '↻'}</span><div><strong>{item.document_name}</strong><small>{item.status.replaceAll('_', ' ')} · {item.reason}</small>{item.status_reason && item.status !== 'VALID' && <small>{item.status_reason}</small>}</div></li>)}</ul><details className="optional-requirements"><summary>Other document categories ({requirements.documents.filter(item => !item.required).length})</summary><ul>{requirements.documents.filter(item => !item.required).map(item => <li key={item.document_type}><strong>{item.document_name}</strong><small>{item.status.replaceAll('_', ' ')} · {item.reason}</small></li>)}</ul></details></div><div><h3>Applicable approvals</h3><ul>{requirements.approvals.filter(item => item.applicable).map(item => <li className="approval-requirement" key={item.department}><span className={`requirement-dept-state status-${item.status.toLowerCase()}`}>{item.status.replaceAll('_', ' ')}</span><div><strong>{item.approval_name}</strong><small>{item.reason}</small></div></li>)}{requirements.approvals.every(item => !item.applicable) && <li className="requirements-empty">No department approvals match the current configured rules.</li>}</ul></div></div>
                <div className={`submission-readiness ${requirements.submission_ready ? 'ready' : 'blocked'}`}><strong>{requirements.submission_ready ? 'Document requirements are satisfied' : 'Action required before submission'}</strong><span>{requirements.submission_ready ? 'Your required checklist is currently complete.' : `${requirements.counts.missing + requirements.counts.needs_correction} required document(s) need attention.`}</span></div>
                <small className="requirements-disclaimer">{requirements.disclaimer}</small>
              </>}
            </section>}
            <div className="applicant-register-meta" role="status">
              <span><strong>{dashboard?.summary.total ?? 0}</strong> applications</span>
              <span><strong>{dashboard?.summary.unread_notifications ?? 0}</strong> unread updates</span>
              {focusApplication?.latest_update?.message && <span className="latest-update">Latest update: {focusApplication.latest_update.message}</span>}
              <a className="context-link" href="/applicant/applications">Open full application register →</a>
            </div>
            <section className="dashboard-application-list">
              <div className="dashboard-list-heading">
                <div><span className="card-kicker">YOUR APPLICATIONS</span><h2>Application workspace</h2><p>Every application you have created, with its live workflow status.</p></div>
                <span className="application-count">{data.applications.length} RECORDS</span>
              </div>
              {data.applications.length === 0 ? (
                <div className="dashboard-empty"><h3>No applications yet</h3><p>Start a new application and it will appear here.</p></div>
              ) : (
                <div className="dashboard-application-cards">
                  {data.applications.map(application => {
                    const draft = application.status === 'DRAFT'
                    const statusTone = application.status === 'APPROVED' ? 'approved' : application.status === 'REJECTED' ? 'rejected' : application.status === 'ACTION_REQUIRED' ? 'action' : application.status === 'IN_REVIEW' || application.status === 'SUBMITTED' ? 'pending' : 'draft'
                    return (
                      <article className="dashboard-application-card" key={application.id}>
                        <div className="dashboard-application-main">
                          <span className="application-number">{application.application_number}</span>
                          <h3>{application.company_name || 'Company details pending'}</h3>
                          <p><strong>Industry:</strong> {application.industry_type || 'Industry not specified'}</p>
                        </div>
                        <div className="dashboard-application-meta">
                          <span className={`status-pill ${statusTone}`}><i />{application.status.replaceAll('_', ' ')}</span>
                          <small>{application.current_department_name || (draft ? 'Draft stage' : 'Awaiting department assignment')}</small>
                          <small>{application.progress_percent}% workflow complete</small>
                        </div>
                        <a className="dashboard-application-action" href={draft ? `/applicant/applications/${application.id}/edit` : `/applicant/applications/${application.id}/view`}>{draft ? 'Continue' : 'Open'} <span>→</span></a>
                      </article>
                    )
                  })}
                </div>
              )}
            </section>
          </>
        )}
      </main>
      <footer className="workspace-footer"><span>MAHACLEAR-AI <span>· Faster, Smarter Industrial Approvals</span></span><span>TEAM NORTH-STAR <i>·</i> SIH 2026</span></footer>
    </div>
  )
}

