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
      .then(async r => { if (!r.ok) throw new Error('Unable to load your application register.'); return r.json() })
      .then(setData).catch(e => setError(e instanceof Error ? e.message : 'Unable to load your application register.'))
  }, [])
  return <div className="applicant-shell">
    <header className="applicant-topbar"><a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a><div className="applicant-topbar-spacer" /><a className="applicant-signout" href="/applicant">← Dashboard</a></header>
    <aside className="applicant-sidebar">
      <div className="workspace-nav-label">APPLICANT WORKSPACE</div>
      <a className="side-link" href="/applicant"><span>◫</span> Dashboard</a>
      <a className="side-link selected" href="/applicant/applications"><span>▤</span> My applications</a>
      <a className="side-link" href="/applicant/fees"><span>₹</span> Fee ledger</a>
      <a className="side-link" href="/applicant?notifications=1"><span>◉</span> Notifications</a>
    </aside>
    <main className="applicant-main">
      <div className="breadcrumb">APPLICANT WORKSPACE <span>/</span> MY APPLICATIONS</div>
      <div className="applicant-heading"><div><span className="eyebrow"><i /> APPLICATION REGISTER</span><h1>My applications</h1><p>Full record of drafts, submissions, review progress, risks and approvals.</p></div><a className="primary-button new-application-button" href="/applicant/applications/new">New application <span>＋</span></a></div>
      {error && <div className="applicant-error" role="alert">{error}</div>}
      {!data ? (!error ? <div className="loading-panel">Loading your applications…</div> : null) : <section className="applications-panel">
        <div className="applications-panel-heading"><div><span className="card-kicker">ALL APPLICATIONS</span><h2>Application register</h2></div><span className="application-count">{data.applications.length} RECORDS</span></div>
        {data.applications.length === 0 ? <div className="empty-applications"><span className="empty-mark">＋</span><h3>No applications yet.</h3><p>Create your first application to begin the approval workflow.</p><a className="primary-button" href="/applicant/applications/new">Start an application <span>→</span></a></div> :
        <div className="application-table-wrap"><table className="application-table"><thead><tr><th>APPLICATION ID</th><th>COMPANY</th><th>INDUSTRY</th><th>RISK</th><th>STATUS</th><th>PROGRESS</th><th>DEPARTMENT</th><th>EXPECTED COMPLETION</th><th>ACTIONS</th></tr></thead><tbody>{data.applications.map(a => <ApplicationRow key={a.id} application={a} />)}</tbody></table></div>}
      </section>}
    </main>
    <footer className="workspace-footer"><span>MAHACLEAR-AI <span>· Faster, Smarter Industrial Approvals</span></span><span>TEAM NORTH-STAR <i>·</i> SIH 2026</span></footer>
  </div>
}
function ApplicationRow({application:a}:{application:ApplicationRecord}) {
  const isDraft=a.status==='DRAFT'
  const href=isDraft?'/applicant/applications/'+a.id+'/edit':'/applicant/applications/'+a.id+'/view'
  const tone=a.risk_tier?'officer-risk '+a.risk_tier.toLowerCase():'not-assessed'
  const statusTone=a.status==='APPROVED'?'approved':a.status==='REJECTED'?'rejected':a.status==='ACTION_REQUIRED'?'action':a.status==='IN_REVIEW'?'in-review':a.status==='DRAFT'?'draft':'pending'
  return <tr><td className="application-number">{a.application_number}</td><td>{a.company_name||'Company not entered'}</td><td>{a.industry_type||'Not selected'}</td><td><span className={tone}>{a.risk_tier||'Not assessed'}</span></td><td><span className={`status-pill ${statusTone}`}><i />{statusLabel(a.status)}</span></td><td><div className="progress-cell"><div className="progress-track"><i style={{width:`${a.progress_percent}%`}} /></div><span>{a.progress_percent}%</span></div></td><td>{a.current_department_name||(isDraft?'Not assigned':'Awaiting assignment')}</td><td>{formatDate(a.expected_completion_at)}</td><td><a className="table-action" href={href}>{isDraft?'Edit draft':'View'} <span>→</span></a><a className="table-action risk-table-action" href={`/applicant/applications/${a.id}/risk`}>Risk <span>→</span></a><a className="table-action risk-table-action" href={`/applicant/applications/${a.id}/approvals`}>Approvals <span>→</span></a><a className="table-action risk-table-action" href={`/applicant/applications/${a.id}/critical-path`}>Critical path <span>→</span></a><a className="table-action risk-table-action" href={`/applicant/applications/${a.id}/assistant`}>Ask AI <span>→</span></a>{!isDraft&&<a className="table-action risk-table-action" href={`/applicant/applications/${a.id}/activity`}>Timeline <span>→</span></a>}</td></tr>
}
