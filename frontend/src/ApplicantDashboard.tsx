import { useEffect, useState } from 'react'
import type { ApplicationsResponse } from './applicationTypes'
import { formatDate, statusLabel } from './applicationTypes'

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

  useEffect(() => {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    const headers = { Authorization: `Bearer ${token}` }
    async function load() {
      try {
        const me = await fetch('/api/auth/me', { headers })
        if (!me.ok) throw new Error('Your session has expired. Sign in again.')
        const user: ApplicantUser = await me.json()
        if (user.role !== 'APPLICANT') {
          const dashboard = user.role === 'OFFICER' ? '/officer' : '/admin'
          window.location.assign(dashboard)
          return
        }
        const [response, dashboardResponse] = await Promise.all([
          fetch('/api/applications', { headers }),
          fetch('/api/applicant/dashboard', { headers }),
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
      const response = await fetch('/api/applications', {
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

  return (
    <div className="applicant-shell">
      <header className="applicant-topbar">
        <a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a>
        <div className="applicant-topbar-spacer" aria-hidden="true" />
        <button className="applicant-signout" type="button" onClick={() => { localStorage.removeItem('mahaclear_access_token'); window.location.assign('/login') }}><span className="signout-icon" aria-hidden="true">↪</span><strong>Sign out</strong></button>
      </header>
      <aside className="applicant-sidebar">
        <div className="workspace-nav-label">APPLICANT WORKSPACE</div>
        <a className="side-link selected" href="/applicant"><span>◫</span> Dashboard</a>
        <a className="side-link" href="/applicant/applications"><span>▤</span> My applications</a>
        <a className="side-link" href="/applicant/fees"><span>₹</span> Fee ledger</a>
        <a className="side-link" href="/notifications"><span>◉</span> Notifications</a>
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
            <div className="applicant-register-meta" role="status">
              <span><strong>{dashboard?.summary.total ?? 0}</strong> applications</span>
              <span><strong>{dashboard?.summary.unread_notifications ?? 0}</strong> unread updates</span>
              {focusApplication?.latest_update?.message && <span className="latest-update">Latest update: {focusApplication.latest_update.message}</span>}
              <a className="context-link" href="/applicant/applications">Open full application register →</a>
            </div>
                    </>
        )}
      </main>
      {notificationsOpen && <NotificationDrawer onClose={() => window.history.replaceState({}, '', '/applicant')} />}
      <footer className="workspace-footer"><span>MAHACLEAR-AI <span>· Faster, Smarter Industrial Approvals</span></span><span>TEAM NORTH-STAR <i>·</i> SIH 2026</span></footer>
    </div>
  )
}

function StatusPill({ status }: { status: string }) {
  const tone = status === 'APPROVED' ? 'approved' : status === 'REJECTED' ? 'rejected' : status === 'ACTION_REQUIRED' ? 'action' : status === 'IN_REVIEW' ? 'in-review' : status === 'DRAFT' ? 'draft' : 'pending'
  return <span className={`status-pill ${tone}`}><i />{statusLabel(status as Parameters<typeof statusLabel>[0])}</span>
}
