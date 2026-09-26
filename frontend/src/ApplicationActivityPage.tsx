import { apiUrl } from './apiBase'
import { useEffect, useState } from 'react'
import AuthenticatedDownload from './AuthenticatedDownload'

type ActivityEvent = { id: number; occurred_at: string; department_code: string | null; action: string; officer: string; status: string | null; message: string | null }
type Inspection = { id: number; kind: string; department_name: string; scheduled_at: string; site: string; status: string; instructions: string | null; participants?: Array<{ department_name: string; officer: string | null; status: string }>; findings: string | null; photos: Array<{ file_name: string; download_url: string }>; remarks: string | null; recommendation: string | null }
type Sla = { approval_id: number; department_name: string; approval_status: string; status: string; remaining_days: number | null; expected_completion: string | null }
type PageData = { application_number: string; events: ActivityEvent[] }

export default function ApplicationActivityPage({ applicationId }: { applicationId: number }) {
  const [timeline, setTimeline] = useState<PageData | null>(null)
  const [inspections, setInspections] = useState<Inspection[]>([])
  const [slas, setSlas] = useState<Sla[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    const headers = { Authorization: `Bearer ${token}` }
    void Promise.all([
      fetch(apiUrl(`/api/applications/${applicationId}/timeline`), { headers }).then(async (res) => { const body = await res.json(); if (!res.ok) throw new Error(body.detail); return body }),
      fetch(apiUrl(`/api/applications/${applicationId}/inspections`), { headers }).then(async (res) => { const body = await res.json(); if (!res.ok) throw new Error(body.detail); return body }),
      fetch(apiUrl(`/api/applications/${applicationId}/sla`), { headers }).then(async (res) => { const body = await res.json(); if (!res.ok) throw new Error(body.detail); return body }),
    ]).then(([events, checks, service]) => { setTimeline(events); setInspections(checks.items); setSlas(service.items) })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Could not load application activity.'))
  }, [applicationId])
  const date = (value: string) => new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
  return <div className="activity-page">
    <header className="activity-top"><a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a><a className="activity-back" href={`/applicant/applications/${applicationId}/approvals`}>Approval status ↗</a></header>
    <main className="activity-main"><div className="breadcrumb">APPLICANT WORKSPACE <span>/</span> APPLICATION ACTIVITY</div>
      <div className="activity-heading"><div><span className="eyebrow"><i /> APPLICATION TIMELINE</span><h1>{timeline?.application_number ?? 'Application activity'}</h1><p>Inspections, service targets, and recorded workflow events.</p></div><a className="officer-button secondary" href="/notifications">Notifications ↗</a></div>
      {error && <div className="applicant-error" role="alert">{error}</div>}
      <section className="activity-section"><header><span className="card-kicker">SERVICE TARGETS</span><h2>Department SLAs</h2></header><div className="sla-grid">{slas.map((item) => <article className="sla-card" key={item.approval_id}><span className={`activity-status ${item.status.toLowerCase()}`}>{item.status.replaceAll('_', ' ')}</span><strong>{item.department_name}</strong><small>{item.approval_status.replaceAll('_', ' ')} · {item.remaining_days == null ? 'Waiting on dependencies' : item.remaining_days === 0 ? 'Past expected time' : `${item.remaining_days} day${item.remaining_days === 1 ? '' : 's'} remaining`}</small>{item.expected_completion && <small>Expected {date(item.expected_completion)}</small>}</article>)}</div></section>
      <section className="activity-section"><header><span className="card-kicker">INSPECTIONS</span><h2>Site visits and results</h2></header>{inspections.length === 0 ? <p className="activity-empty">No inspections are scheduled.</p> : inspections.map((item) => <article className="applicant-inspection" key={`${item.kind}-${item.id}`}><div className="applicant-inspection-heading"><div><strong>{item.department_name} · {item.kind === 'JOINT' ? 'Joint inspection' : 'Inspection'}</strong><small>{date(item.scheduled_at)} · {item.site}</small></div><span className={`activity-status ${item.status.toLowerCase()}`}>{item.status.replaceAll('_', ' ')}</span></div>{item.instructions && <p>{item.instructions}</p>}{item.participants?.length ? <div className="participant-chips">{item.participants.map((person) => <span key={person.department_name}>{person.department_name}{person.officer ? ` · ${person.officer}` : ''}</span>)}</div> : null}{item.findings && <p><b>Findings:</b> {item.findings}</p>}{item.remarks && <p><b>Remarks:</b> {item.remarks}</p>}{item.recommendation && <p><b>Recommendation:</b> {item.recommendation}</p>}{item.photos.map((photo) => <AuthenticatedDownload key={photo.download_url} href={photo.download_url} fileName={photo.file_name}>{photo.file_name} ↓</AuthenticatedDownload>)}</article>)}</section>
      <section className="activity-section"><header><span className="card-kicker">AUDITABLE WORKFLOW EVENTS</span><h2>Application timeline</h2></header>{!timeline ? <div className="loading-panel">Loading application events…</div> : timeline.events.length === 0 ? <p className="activity-empty">No events recorded yet.</p> : <ol className="application-timeline">{timeline.events.map((event) => <li key={event.id}><span className="timeline-mark"/><div><div className="timeline-event-heading"><strong>{event.action.replaceAll('_', ' ')}</strong><small>{date(event.occurred_at)}</small></div><p>{event.message || event.status?.replaceAll('_', ' ')}</p><small>{event.department_code ? `${event.department_code} · ` : ''}{event.officer}</small></div></li>)}</ol>}</section>
    </main>
  </div>
}
