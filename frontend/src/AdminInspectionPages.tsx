import { apiUrl } from './apiBase'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

const tokenHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('mahaclear_access_token') ?? ''}` })

export function AdminApplicationPage({ applicationId }: { applicationId: number }) {
  const [data, setData] = useState<Record<string, any> | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    void fetch(apiUrl(`/api/admin/applications/${applicationId}`), { headers: tokenHeaders() }).then(async (response) => {
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.detail || 'Could not load application oversight record.')
      setData(body)
    }).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Could not load application.'))
  }, [applicationId])
  const app = data?.application
  return <div className="admin-detail-page"><header className="admin-detail-top"><a href="/admin">← Government dashboard</a><a className="brand" href="/admin"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a></header><main className="admin-detail-main">{error && <p className="applicant-error">{error}</p>}{!data ? <p className="admin-empty">Loading application records…</p> : <>
    <span className="eyebrow"><i/> APPLICATION OVERSIGHT</span><h1>{app.application_number}</h1><p className="admin-detail-subtitle">{app.company_name || 'Company not provided'} · {app.status.replaceAll('_', ' ')} · {app.industry_type || 'Industry not selected'}</p>
    <div className="admin-detail-grid"><section className="admin-panel"><Panel title="Application and applicant"/><dl className="admin-detail-facts">{Object.entries({ Applicant: app.applicant_name, Email: app.applicant_email, Company: app.company_name, Location: app.project_location, Risk: app.risk_tier, 'Submitted at': formatDate(app.submitted_at), 'Expected completion': formatDate(app.expected_completion_at) }).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value ?? '—')}</dd></div>)}</dl></section>
    <section className="admin-panel"><Panel title="Risk assessment"/><div className="admin-risk-summary"><strong>{data.risk ? `${data.risk.score}/100` : '—'}</strong><span>{data.risk?.tier || app.risk_tier || 'Not assessed'}</span></div><small>{data.risk ? `Last assessed ${formatDate(data.risk.assessed_at)}` : 'No saved assessment found.'}</small></section></div>
    <section className="admin-panel"><Panel title="Department approvals and SLA"/><div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>DEPARTMENT</th><th>STATUS</th><th>DEPENDENCIES</th><th>SLA DUE</th><th>MESSAGE</th></tr></thead><tbody>{data.approvals.filter((item: any) => item.required).map((item: any) => <tr key={item.id}><td>{item.department_name}</td><td><span className={`admin-risk ${String(item.status).toLowerCase()}`}>{item.status.replaceAll('_', ' ')}</span></td><td>{item.depends_on.join(', ') || 'None'}</td><td>{formatDate(item.sla_expected_completion)}</td><td>{item.decision_message || '—'}</td></tr>)}</tbody></table></div></section>
    <section className="admin-panel"><Panel title="Generated critical path"/><div className="admin-path-summary"><b>{data.critical_path.estimated_completion_days} days</b><span>Estimated completion · bottleneck {data.critical_path.bottleneck?.department_name || 'none'}</span><p>{data.critical_path.critical_path.join(' → ') || 'No required approvals'}</p></div><div className="admin-path-nodes">{data.critical_path.nodes.filter((node: any) => !node.is_milestone).map((node: any) => <article key={node.id} className={`${node.is_critical_path ? 'critical' : ''} ${node.is_blocked ? 'blocked' : ''}`}><i/ ><div><strong>{node.department}</strong><small>{node.current_status.replaceAll('_', ' ')} · {node.estimated_duration_days} configured days{node.dependencies.length ? ` · waits on ${node.dependencies.join(', ')}` : ''}</small></div></article>)}</div></section>
    <section className="admin-panel"><Panel title="Documents"/>{data.documents.length ? <div className="admin-document-grid">{data.documents.map((doc: any) => <article key={doc.id}><strong>{doc.name}</strong><small>{doc.type.replaceAll('_', ' ')} · {doc.status}</small></article>)}</div> : <p className="admin-empty">No documents saved.</p>}</section>
    <section className="admin-panel"><Panel title="Application audit history" action={<a href="/admin/audit">Full audit log →</a>}/>{data.audit.length ? <ol className="admin-event-list">{data.audit.map((event: any) => <li key={event.id}><time>{formatDate(event.created_at)}</time><div><strong>{event.action.replaceAll('_', ' ')}</strong><small>{event.department_code || 'Application'} · {event.actor} · {event.status || ''}</small>{event.message && <p>{event.message}</p>}</div></li>)}</ol> : <p className="admin-empty">No audit events recorded.</p>}</section>
  </>}</main></div>
}

export function AdminAuditPage() {
  const [items, setItems] = useState<Array<Record<string, any>>>([])
  const [error, setError] = useState('')
  useEffect(() => { void fetch(apiUrl('/api/admin/audit?limit=250'), { headers: tokenHeaders() }).then(async (response) => { const body = await response.json(); if (!response.ok) throw new Error(body.detail || 'Unable to load audit log.'); setItems(body.items) }).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Unable to load audit log.')) }, [])
  return <div className="admin-detail-page"><header className="admin-detail-top"><a href="/admin">← Government dashboard</a><a className="brand" href="/admin"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a></header><main className="admin-detail-main"><span className="eyebrow"><i/> APPEND-ONLY WORKFLOW RECORDS</span><h1>Government audit log</h1><p className="admin-detail-subtitle">Recorded application, approval, inspection, and SLA events.</p>{error && <div className="applicant-error">{error}</div>}<section className="admin-panel"><div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>TIME</th><th>APPLICATION</th><th>DEPARTMENT</th><th>ACTION / STATUS</th><th>ACTOR</th><th>DETAIL</th></tr></thead><tbody>{items.map((event) => <tr key={Number(event.id)}><td>{formatDate(event.created_at)}</td><td><a href={`/admin/applications/${event.application_id}`}>{event.application_number || event.application_id}</a></td><td>{event.department || '—'}</td><td><strong>{String(event.action).replaceAll('_', ' ')}</strong><small>{event.to_status || ''}</small></td><td>{event.actor}</td><td>{event.message || '—'}</td></tr>)}</tbody></table></div>{!items.length && <p className="admin-empty">No audit events found.</p>}</section></main></div>
}

function Panel({ title, action }: { title: string; action?: ReactNode }) { return <header className="admin-panel-heading"><div><span>DATABASE RECORD</span><h2>{title}</h2></div>{action}</header> }
function formatDate(value: string | null | undefined) { return value ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—' }
