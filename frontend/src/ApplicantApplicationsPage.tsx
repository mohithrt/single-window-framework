import { useEffect, useState } from 'react'
import type { ApplicationsResponse, ApplicationRecord } from './applicationTypes'
import { formatDate, statusLabel } from './applicationTypes'

export default function ApplicantApplicationsPage() {
  const [data, setData] = useState<ApplicationsResponse | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    fetch('/api/applications', { headers: { Authorization: `Bearer ${token}` } })
      .then(async response => {
        const body = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Unable to load your applications.')
        setData(body as ApplicationsResponse)
      })
      .catch(caught => setError(caught instanceof Error ? caught.message : 'Unable to load your applications.'))
  }, [])

  const signOut = () => {
    localStorage.removeItem('mahaclear_access_token')
    window.location.assign('/login')
  }

  return (
    <div className="applicant-shell">
      <header className="applicant-topbar">
        <a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a>
        <div className="applicant-topbar-spacer" aria-hidden="true" />
        <button className="applicant-signout" type="button" onClick={signOut}><span className="signout-icon" aria-hidden="true">↪</span><strong>Sign out</strong></button>
      </header>

      <aside className="applicant-sidebar">
        <div className="workspace-nav-label">APPLICANT WORKSPACE</div>
        <a className="side-link" href="/applicant"><span>◫</span> Dashboard</a>
        <a className="side-link" href="/applicant/permissions"><span>◎</span> Permissions &amp; fees</a>
        <a className="side-link" href="/applicant/applications"><span>▤</span> My applications</a>
        <a className="side-link" href="/notifications"><span>◉</span> Notifications</a>
        <div className="sidebar-note"><span className="sidebar-note-mark">✳</span><strong>One window.<br />Every approval.</strong><small>North-Star · SIH 2026</small></div>
        <div className="sidebar-bottom">MAHACLEAR-AI <span>·</span> APPLICANT</div>
      </aside>

      <main className="applicant-main">
        <div className="breadcrumb">APPLICANT WORKSPACE <span>/</span> MY APPLICATIONS</div>
        <div className="applicant-heading">
          <div><span className="eyebrow"><i /> APPLICATION REGISTER</span><h1>My applications</h1><p>Track every draft, submission, review, risk and approval from one place.</p></div>
          <a className="primary-button new-application-button" href="/applicant/applications/new">New application <span>＋</span></a>
        </div>

        {error && <div className="applicant-error" role="alert">{error} <button onClick={() => window.location.reload()}>Retry</button></div>}
        {!data ? (!error ? <div className="loading-panel" role="status">Loading your applications…</div> : null) : (
          <>
            <section className="applications-summary" aria-label="Application summary">
              <article><span>TOTAL APPLICATIONS</span><strong>{data.summary.total_applications}</strong><small>All saved records</small></article>
              <article><span>PENDING / IN REVIEW</span><strong>{data.summary.pending}</strong><small>Currently moving through review</small></article>
              <article><span>ACTION REQUIRED</span><strong>{data.summary.action_required}</strong><small>Needs your attention</small></article>
              <article><span>APPROVED</span><strong>{data.summary.approved}</strong><small>Completed approvals</small></article>
            </section>

            <section className="applications-panel">
              <div className="applications-panel-heading">
                <div><span className="card-kicker">YOUR APPLICATION REGISTER</span><h2>Application history</h2></div>
                <span className="application-count">{data.applications.length} RECORDS</span>
              </div>

              {data.applications.length === 0 ? (
                <div className="empty-applications">
                  <span className="empty-mark">＋</span><h3>No applications yet</h3>
                  <p>Create your first application to begin the approval workflow.</p>
                  <a className="primary-button" href="/applicant/applications/new">Start an application <span>→</span></a>
                </div>
              ) : (
                <div className="application-table-wrap">
                  <table className="application-table">
                    <thead><tr><th>APPLICATION</th><th>COMPANY / INDUSTRY</th><th>STATUS</th><th>RISK</th><th>PROGRESS</th><th>CURRENT STAGE</th><th>EXPECTED COMPLETION</th><th>ACTION</th></tr></thead>
                    <tbody>{data.applications.map(application => <ApplicationRow key={application.id} application={application} />)}</tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}
      </main>

      <footer className="workspace-footer"><span>MAHACLEAR-AI <span>· Application register</span></span><span>TEAM NORTH-STAR <i>·</i> SIH 2026</span></footer>
    </div>
  )
}

function ApplicationRow({ application: a }: { application: ApplicationRecord }) {
  const isDraft = a.status === 'DRAFT'
  const href = isDraft ? `/applicant/applications/${a.id}/edit` : `/applicant/applications/${a.id}/view`
  const riskTone = a.risk_tier ? 'officer-risk ' + a.risk_tier.toLowerCase() : 'not-assessed'
  const statusTone = a.status === 'APPROVED' ? 'approved' : a.status === 'REJECTED' ? 'rejected' : a.status === 'ACTION_REQUIRED' ? 'action' : a.status === 'IN_REVIEW' ? 'in-review' : a.status === 'DRAFT' ? 'draft' : 'pending'

  return (
    <tr>
      <td className="application-number"><a className="table-action" href={href}>{a.application_number}</a><small>{a.status === 'DRAFT' ? 'Draft application' : a.submitted_at ? `Submitted ${formatDate(a.submitted_at)}` : 'Saved application'}</small></td>
      <td><strong>{a.company_name || 'Company details pending'}</strong><small>{a.industry_type || 'Industry not selected'}</small></td>
      <td><span className={`status-pill ${statusTone}`}><i />{statusLabel(a.status)}</span></td>
      <td><span className={riskTone}>{a.risk_tier || 'Not assessed'}</span></td>
      <td><div className="progress-cell"><div className="progress-track"><i style={{ width: `${a.progress_percent}%` }} /></div><span>{a.progress_percent}%</span></div></td>
      <td><strong>{a.current_department_name || (isDraft ? 'Draft stage' : 'Awaiting assignment')}</strong><small>{isDraft ? 'Continue your application' : 'Workflow stage'}</small></td>
      <td>{formatDate(a.expected_completion_at)}</td>
      <td>
        <a className="table-action" href={href}>{isDraft ? 'Continue' : 'View'} <span>→</span></a>
        {!isDraft && <><a className="table-action risk-table-action" href={`/applicant/applications/${a.id}/risk`}>Risk <span>→</span></a><a className="table-action risk-table-action" href={`/applicant/applications/${a.id}/approvals`}>Approvals <span>→</span></a></>}
      </td>
    </tr>
  )
}
