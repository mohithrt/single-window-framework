import { useEffect, useState } from 'react'

type WorkflowStatus = 'NOT_STARTED' | 'PENDING' | 'IN_REVIEW' | 'DOCUMENT_CORRECTION' | 'INSPECTION_REQUIRED' | 'APPROVED' | 'REJECTED' | 'ESCALATED'
type DepartmentApproval = { id: number; department_code: string; department_name: string; is_required: boolean; status: WorkflowStatus; depends_on: string[]; decision_message: string | null; correction_can_submit: boolean; updated_at: string }
type WorkflowEvent = { id: number; actor_name: string; action: string; from_status: string | null; to_status: string | null; message: string | null; created_at: string }
type WorkflowData = { application_id: number; application_number: string; application_status: string; initialized: boolean; approvals: DepartmentApproval[]; audit_events: WorkflowEvent[] }

const labels: Record<WorkflowStatus, string> = {
  NOT_STARTED: 'Not started', PENDING: 'Pending', IN_REVIEW: 'In review',
  DOCUMENT_CORRECTION: 'Correction requested', INSPECTION_REQUIRED: 'Inspection required',
  APPROVED: 'Approved', REJECTED: 'Rejected', ESCALATED: 'Escalated',
}

export default function ApprovalStatusPage({ applicationId }: { applicationId: number }) {
  const [data, setData] = useState<WorkflowData | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    void fetch(`/api/applications/${applicationId}/approvals`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        const body = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(body.detail || 'Unable to load approval statuses.')
        setData(body)
      }).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Unable to load approval statuses.'))
  }, [applicationId])

  const status = (value: string) => labels[value as WorkflowStatus] ?? value.replaceAll('_', ' ')
  return <div className="approval-page">
    <header className="approval-page-top"><a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a><a className="wizard-exit" href="/applicant">Dashboard <span>↗</span></a></header>
    <main className="approval-page-main">
      <div className="breadcrumb">APPLICANT WORKSPACE <span>/</span> APPROVAL STATUS</div>
      {error ? <div className="applicant-error" role="alert">{error}</div> : !data ? <div className="loading-panel">Loading department approvals…</div> : <>
        <div className="approval-heading"><div><span className="eyebrow"><i /> APPLICATION WORKFLOW</span><h1>Department approvals</h1><p>See which departments are reviewing your application and what they need next.</p></div><div className="approval-app-number">{data.application_number}<strong>{status(data.application_status)}</strong></div></div>
        {!data.initialized ? <div className="loading-panel">Approval routing is created when your application is submitted.</div> : <>
          <section className="approval-list" aria-label="Department approval statuses">
            {data.approvals.map((approval) => <article className={`approval-card ${approval.status.toLowerCase()}`} key={approval.id}>
              <span className="approval-state-mark" aria-hidden="true">{approval.status === 'APPROVED' ? '✓' : approval.status === 'REJECTED' ? '×' : approval.status === 'NOT_STARTED' ? '·' : '◷'}</span>
              <div className="approval-card-main"><div className="approval-card-title"><h2>{approval.department_name}</h2><span className={`approval-status-chip ${approval.status.toLowerCase()}`}>{status(approval.status)}</span></div>
                <p>{approval.is_required ? 'Required department' : 'Not required for this application'}</p>
                {approval.depends_on.length > 0 && <small>Starts after: {approval.depends_on.join(', ')}</small>}
                {approval.decision_message && <div className="approval-message"><strong>{approval.status === 'DOCUMENT_CORRECTION' ? 'Action needed' : 'Department note'}</strong><p>{approval.decision_message}</p></div>}
                {approval.status === 'DOCUMENT_CORRECTION' && data.application_status === 'ACTION_REQUIRED' && <div className="correction-links"><strong>{approval.correction_can_submit ? 'Your response is saved and ready to send.' : 'Update a requested detail or supporting document before sending your response.'}</strong><div><a href={`/applicant/applications/${applicationId}/edit?step=0`}>Review application details →</a><a href={`/applicant/applications/${applicationId}/edit?step=5`}>Update supporting documents →</a></div></div>}
              </div>
            </article>)}
          </section>
          <section className="workflow-history"><div className="applications-panel-heading"><div><span className="card-kicker">WORKFLOW HISTORY</span><h2>Recent activity</h2></div></div>
            {data.audit_events.length === 0 ? <p className="history-empty">No workflow activity yet.</p> : <ol>{[...data.audit_events].reverse().map((event) => <li key={event.id}><span className="history-dot"/><div><strong>{event.action.replaceAll('_', ' ')}</strong><p>{event.message || `${event.from_status ? `${status(event.from_status)} → ` : ''}${status(event.to_status || '')}`}</p><small>{event.actor_name} · {new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(event.created_at))}</small></div></li>)}</ol>}
          </section>
        </>}
      </>}
    </main>
  </div>
}
