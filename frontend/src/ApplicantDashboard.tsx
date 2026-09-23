import { useEffect, useState } from 'react'
import type { ApplicationsResponse } from './applicationTypes'
import { formatDate, statusLabel } from './applicationTypes'

type ApplicantUser = { role: string }

async function responseMessage(response: Response): Promise<string> {
  const body = await response.json().catch(() => ({}))
  if (typeof body.detail === 'string') return body.detail
  if (body.detail?.message) return body.detail.message
  return 'Unable to load your applications. Please try again.'
}

export default function ApplicantDashboard() {
  const [data, setData] = useState<ApplicationsResponse | null>(null)
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
        const response = await fetch('/api/applications', { headers })
        if (!response.ok) throw new Error(await responseMessage(response))
        setData(await response.json())
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

  const summary = data?.summary

  return (
    <div className="applicant-shell">
      <header className="applicant-topbar">
        <a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a>
        <nav className="applicant-top-nav" aria-label="Applicant navigation"><a className="active" href="/applicant">Dashboard</a><a href="#applications">Applications</a></nav>
        <button className="applicant-signout" onClick={() => { localStorage.removeItem('mahaclear_access_token'); window.location.assign('/login') }}>Sign out <span>↗</span></button>
      </header>
      <aside className="applicant-sidebar">
        <div className="workspace-nav-label">APPLICANT WORKSPACE</div>
        <a className="side-link selected" href="/applicant"><span>◫</span> Dashboard</a>
        <a className="side-link" href="#applications"><span>▤</span> My applications</a>
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
        {!data && !error ? <div className="loading-panel">Loading your applications…</div> : (
          <>
            <section className="application-stats" aria-label="Application totals">
              <Stat label="TOTAL APPLICATIONS" value={summary?.total_applications ?? 0} icon="▤" tone="green" />
              <Stat label="PENDING" value={summary?.pending ?? 0} icon="◷" tone="blue" />
              <Stat label="APPROVED" value={summary?.approved ?? 0} icon="✓" tone="green" />
              <Stat label="REJECTED" value={summary?.rejected ?? 0} icon="×" tone="red" />
              <Stat label="ACTION REQUIRED" value={summary?.action_required ?? 0} icon="!" tone="amber" />
            </section>
            <section className="applications-panel" id="applications">
              <div className="applications-panel-heading"><div><span className="card-kicker">YOUR APPLICATIONS</span><h2>Application register</h2></div><span className="application-count">{data?.applications.length ?? 0} RECORDS</span></div>
              {(data?.applications.length ?? 0) === 0 ? <div className="empty-applications"><span className="empty-mark">＋</span><h3>Your application list is clear.</h3><p>Start an application to save a draft and track its progress here.</p><button className="primary-button" onClick={startApplication} disabled={creating}>Start an application <span>→</span></button></div> : (
                <div className="application-table-wrap">
                  <table className="application-table">
                    <thead><tr><th>APPLICATION ID</th><th>COMPANY</th><th>INDUSTRY</th><th>RISK</th><th>OVERALL STATUS</th><th>PROGRESS</th><th>CURRENT DEPARTMENT</th><th>EXPECTED COMPLETION</th><th>ACTIONS</th></tr></thead>
                    <tbody>{data?.applications.map((application) => {
                      const isDraft = application.status === 'DRAFT'
                      const href = isDraft ? `/applicant/applications/${application.id}/edit` : `/applicant/applications/${application.id}/view`
                      return <tr key={application.id}>
                        <td className="application-number">{application.application_number}</td>
                        <td>{application.company_name || 'Company not entered'}</td>
                        <td>{application.industry_type || 'Not selected'}</td>
                        <td><span className="not-assessed">{application.risk_tier || 'Not assessed'}</span></td>
                        <td><StatusPill status={application.status} /></td>
                        <td><div className="progress-cell"><div className="progress-track"><i style={{ width: `${application.progress_percent}%` }} /></div><span>{application.progress_percent}%</span></div></td>
                        <td>{application.current_department_name || (isDraft ? 'Not assigned' : 'Awaiting assignment')}</td>
                        <td>{formatDate(application.expected_completion_at)}</td>
                        <td><a className="table-action" href={href}>{isDraft ? 'Edit draft' : 'View'} <span>→</span></a><a className="table-action risk-table-action" href={`/applicant/applications/${application.id}/risk`}>Risk assessment <span>→</span></a><a className="table-action risk-table-action" href={`/applicant/applications/${application.id}/approvals`}>Approvals <span>→</span></a><a className="table-action risk-table-action" href={`/applicant/applications/${application.id}/critical-path`}>Critical path <span>→</span></a></td>
                      </tr>
                    })}</tbody>
                  </table>
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

function Stat({ label, value, icon, tone }: { label: string; value: number; icon: string; tone: string }) {
  return <article className="application-stat"><span className={`stat-icon ${tone}`}>{icon}</span><span className="card-kicker">{label}</span><strong>{value}</strong><span className="stat-caption">Applications in your workspace</span></article>
}

function StatusPill({ status }: { status: string }) {
  const tone = status === 'APPROVED' ? 'approved' : status === 'REJECTED' ? 'rejected' : status === 'ACTION_REQUIRED' ? 'action' : status === 'DRAFT' ? 'draft' : 'pending'
  return <span className={`status-pill ${tone}`}><i />{statusLabel(status as Parameters<typeof statusLabel>[0])}</span>
}
