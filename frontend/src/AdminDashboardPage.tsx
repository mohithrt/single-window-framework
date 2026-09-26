import { apiUrl } from './apiBase'
import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'

type Dept = { department_code: string; department: string; total: number; average_time_days: number | null; pending: number; sla_breaches: number; approval_rate: number | null; sla_breach_rate: number | null }
type AdminData = {
  generated_at: string
  kpis: { total_applications: number; active_applications: number; approved: number; average_clearance_time_days: number | null; sla_breaches: number; high_risk_applications: number; sla_breach_rate: number | null; approval_rate: number | null; rejection_rate: number | null; critical_path_delay_days: number | null; applications_with_critical_path_delay: number }
  applications_by_department: Array<{ department: string; count: number }>
  average_approval_time: Array<{ department: string; days: number | null }>
  approval_vs_rejection: { approved: number; rejected: number; active: number }
  sla_breach_by_department: Array<{ department: string; rate: number | null; count: number }>
  risk_distribution: Array<{ tier: string; count: number }>
  monthly_volume: Array<{ month: string; count: number }>
  bottlenecks: Array<{ department: string; average_time_days: number | null; pending: number; sla_breaches: number }>
  rejection_reasons: Array<{ reason: string; count: number }>
  departments: Dept[]
  applications: Array<{ id: number; application_number: string; company_name: string; applicant_name: string | null; industry_type: string | null; status: string; risk_tier: string | null; submitted_at: string | null; expected_completion_at: string | null; departments: string[] }>
  audit_events: Array<{ id: number; application_id: number; application_number: string | null; department: string | null; action: string; actor: string; status: string | null; message: string | null; created_at: string }>
  bottleneck_department: string | null
}
type Provider = { code: string; name: string; mode: string; connected_to_government: boolean }
type Integration = { id: number; provider_code: string; application_number: string | null; reference: string; status: string; response: { message?: string; connected_to_government?: boolean; demo?: boolean }; created_at: string }

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem('mahaclear_access_token')
  if (!token) { window.location.assign('/login'); throw new Error('Sign in to continue.') }
  const response = await fetch(path, { ...init, headers: { Authorization: `Bearer ${token}`, ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...init?.headers } })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || 'The request could not be completed.')
  return body as T
}

export default function AdminDashboardPage() {
  const [data, setData] = useState<AdminData | null>(null)
  const [providers, setProviders] = useState<Provider[]>([])
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [provider, setProvider] = useState('MPCB')
  const [applicationId, setApplicationId] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    void fetch(apiUrl('/api/auth/me'), { headers: { Authorization: `Bearer ${token}` } }).then((response) => response.json()).then((user) => {
      if (user.role !== 'ADMIN') window.location.assign(user.role === 'OFFICER' ? '/officer' : '/applicant')
    }).catch(() => window.location.assign('/login'))
    void Promise.all([
      api<AdminData>(apiUrl('/api/admin/analytics')),
      api<{ items: Provider[] }>(apiUrl('/api/admin/integrations/providers')),
      api<{ items: Integration[] }>(apiUrl('/api/admin/integrations')),
    ]).then(([report, catalog, history]) => { setData(report); setProviders(catalog.items); setIntegrations(history.items) })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Unable to load administration data.'))
  }, [])
  async function submitIntegration(event: FormEvent) {
    event.preventDefault(); setError(''); setMessage(''); setBusy(true)
    try {
      const result = await api<Integration>(apiUrl(`/api/admin/integrations/${provider}/submit`), {
        method: 'POST', body: JSON.stringify({ application_id: applicationId ? Number(applicationId) : null }),
      })
      setIntegrations((rows) => [result, ...rows]); setMessage(`${result.provider_code} transaction saved as ${result.reference}. Mode: ${result.response?.demo ? 'MOCK' : 'CONFIGURED HTTP'}.`)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Demo provider submission failed.') }
    finally { setBusy(false) }
  }
  async function signOut() { localStorage.removeItem('mahaclear_access_token'); window.location.assign('/login') }
  const kpis = data?.kpis
  const values = [
    ['TOTAL APPLICATIONS', kpis?.total_applications ?? '—'], ['ACTIVE APPLICATIONS', kpis?.active_applications ?? '—'],
    ['APPROVED', kpis?.approved ?? '—'], ['AVG CLEARANCE TIME', kpis?.average_clearance_time_days == null ? '—' : `${kpis.average_clearance_time_days} d`],
    ['SLA BREACHES', kpis?.sla_breaches ?? '—'], ['HIGH RISK', kpis?.high_risk_applications ?? '—'],
  ] as const
  return <div className="admin-shell">
    <header className="admin-topbar"><a className="brand" href="/admin"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a><span className="admin-authority-chip">APEX AUTHORITY · LIVE WORKSPACE</span><nav><a href="/notifications"><span className="workspace-nav-icon" aria-hidden="true">◉</span> Notifications</a><button className="signout-button" onClick={() => void signOut()}><span className="signout-icon" aria-hidden="true">↪</span><strong>Sign out</strong></button></nav></header>
    <aside className="admin-sidebar"><span className="workspace-nav-label">GOVERNMENT WORKSPACE</span><a href="#overview"><span>◫</span> Overview</a><a href="#analytics"><span>▥</span> Analytics</a><a href="#departments"><span>▤</span> Departments</a><a href="#applications"><span>▤</span> Applications</a><a href="#audit"><span>▧</span> Audit log</a><a href="#integrations"><span>⇄</span> Integrations</a><a href="/admin/system-health"><span>⚙</span> System health</a><div><strong>North-Star</strong><small>SIH 2026 · Apex Authority</small></div></aside>
    <main className="admin-main"><div className="breadcrumb">GOVERNMENT WORKSPACE <span>/</span> APEX AUTHORITY</div>
      <div className="admin-heading" id="overview"><div><span className="eyebrow"><i/> GOVERNMENT ADMINISTRATION</span><h1>Approval oversight</h1><p>Live measures calculated from saved applications, approval decisions, SLA snapshots, and audit events.</p></div><span className="admin-data-stamp">{data ? `UPDATED ${new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(data.generated_at))}` : 'LOADING LIVE DATA'}</span></div>
      {error && <div className="applicant-error" role="alert">{error}</div>}{message && <div className="admin-success" role="status">{message}</div>}
      <section className="admin-kpis">{values.map(([label, value]) => <article key={label}><span>{label}</span><strong>{value}</strong></article>)}</section>
      {data && <>
        <section className="admin-chart-grid" id="analytics">
          <ChartPanel title="Applications by department" subtitle="Required approval records in the database"><HorizontalBars items={data.applications_by_department.map((item) => ({ label: item.department, value: item.count }))} /></ChartPanel>
          <ChartPanel title="Average approval time" subtitle="Completed approval records · days"><HorizontalBars items={data.average_approval_time.map((item) => ({ label: item.department, value: item.days ?? 0, display: item.days == null ? 'No completed approvals' : `${item.days} days` }))} color="sand" /></ChartPanel>
          <ChartPanel title="Approval vs rejection" subtitle={`Approval rate ${kpis?.approval_rate ?? '—'}% · rejection ${kpis?.rejection_rate ?? '—'}%`}><DecisionBars value={data.approval_vs_rejection}/></ChartPanel>
          <ChartPanel title="SLA breach rate" subtitle={`Overall ${kpis?.sla_breach_rate ?? '—'}% of approval records`}><HorizontalBars items={data.sla_breach_by_department.map((item) => ({ label: item.department, value: item.rate ?? 0, display: `${item.rate ?? 0}% · ${item.count} breaches` }))} color="red" /></ChartPanel>
          <ChartPanel title="Risk distribution" subtitle="Submitted applications with current saved risk tier"><HorizontalBars items={data.risk_distribution.map((item) => ({ label: item.tier, value: item.count }))} color="risk" /></ChartPanel>
          <ChartPanel title="Monthly application volume" subtitle="Submitted applications · last 12 months"><MonthlyChart items={data.monthly_volume}/></ChartPanel>
          <ChartPanel title="Bottleneck departments" subtitle="Ranked by completed processing time, then active workload"><div className="admin-bottlenecks">{data.bottlenecks.length ? data.bottlenecks.map((item, index) => <article key={item.department}><b>{String(index + 1).padStart(2, '0')}</b><div><strong>{item.department}</strong><small>{item.average_time_days == null ? 'No completed time records' : `${item.average_time_days} days average`} · {item.pending} pending · {item.sla_breaches} SLA breaches</small></div></article>) : <EmptyText>No approval records yet.</EmptyText>}</div></ChartPanel>
          <ChartPanel title="Rejection reasons" subtitle="Counts from recorded rejection audit messages"><HorizontalBars items={data.rejection_reasons.map((item) => ({ label: item.reason, value: item.count }))} color="red" /></ChartPanel>
        </section>
        <section className="admin-panel" id="departments"><PanelHeader title="Department comparison" eyebrow="LIVE WORKLOAD AND PERFORMANCE"/><div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>DEPARTMENT</th><th>AVERAGE TIME</th><th>PENDING</th><th>SLA BREACHES</th><th>APPROVAL RATE</th></tr></thead><tbody>{data.departments.map((item) => <tr key={item.department_code}><td><strong>{item.department}</strong><small>{item.department_code} · {item.total} approvals</small></td><td>{item.average_time_days == null ? '—' : `${item.average_time_days} days`}</td><td>{item.pending}</td><td><span className={item.sla_breaches ? 'admin-breach' : ''}>{item.sla_breaches}</span></td><td>{item.approval_rate == null ? '—' : `${item.approval_rate}%`}</td></tr>)}</tbody></table></div>{!data.departments.length && <EmptyText>No department approvals have been created yet.</EmptyText>}</section>
        <section className="admin-panel" id="applications"><PanelHeader title="Applications" eyebrow="INSPECT THE LIVE REGISTER"/><div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>APPLICATION</th><th>COMPANY / APPLICANT</th><th>INDUSTRY</th><th>RISK</th><th>STATUS</th><th>DEPARTMENTS</th><th/></tr></thead><tbody>{data.applications.map((item) => <tr key={item.id}><td><strong>{item.application_number}</strong></td><td>{item.company_name}<small>{item.applicant_name || 'Applicant'}</small></td><td>{item.industry_type || '—'}</td><td><span className={`admin-risk ${String(item.risk_tier || 'unassessed').toLowerCase()}`}>{item.risk_tier || 'UNASSESSED'}</span></td><td>{item.status.replaceAll('_', ' ')}</td><td>{item.departments.join(', ') || '—'}</td><td><a href={`/admin/applications/${item.id}`}>Inspect →</a></td></tr>)}</tbody></table></div>{!data.applications.length && <EmptyText>No submitted applications to inspect yet.</EmptyText>}</section>
        <section className="admin-panel" id="audit"><PanelHeader title="Audit activity" eyebrow="SAVED WORKFLOW EVENTS" action={<a href="/admin/audit">Open full audit log →</a>}/>{data.audit_events.length ? <div className="admin-event-list">{data.audit_events.slice(0, 12).map((event) => <article key={event.id}><time>{new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(event.created_at))}</time><div><strong>{event.action.replaceAll('_', ' ')}</strong><small>{event.application_number || `Application ${event.application_id}`} · {event.department || 'Platform'} · {event.actor}</small>{event.message && <p>{event.message}</p>}</div><a href={`/admin/applications/${event.application_id}`}>View</a></article>)}</div> : <EmptyText>No audit events yet.</EmptyText>}</section>
        <section className="admin-panel" id="integrations"><PanelHeader title="Government integration sandbox" eyebrow="MOCK / CONFIGURED PROVIDERS"/><p className="admin-notice">Providers are mock by default. A configured provider uses its explicitly supplied HTTP endpoint. External email/SMS are also opt-in.</p><form className="admin-integration-form" onSubmit={(event) => void submitIntegration(event)}><label>Provider<select value={provider} onChange={(event) => setProvider(event.target.value)}>{providers.map((item) => <option key={item.code} value={item.code}>{item.name} · {item.mode}</option>)}</select></label><label>Application ID <span>(optional)</span><input type="number" min="1" value={applicationId} onChange={(event) => setApplicationId(event.target.value)} placeholder="Saved application ID"/></label><button className="officer-button primary" disabled={busy}>{busy ? 'Recording demo…' : 'Run mock submission'}</button></form>{integrations.length ? <div className="admin-integration-history">{integrations.map((item) => <article key={item.id}><div><strong>{item.provider_code} · {item.reference}</strong><small>{item.application_number || 'No application linked'} · {item.status} · {item.response.message}</small></div><span>MOCK</span></article>)}</div> : <EmptyText>No demo integration requests saved.</EmptyText>}</section>
        <div className="admin-footnote">Critical path delay: {kpis?.critical_path_delay_days == null ? 'No delayed active applications recorded' : `${kpis.critical_path_delay_days} average days past expected completion across ${kpis.applications_with_critical_path_delay} applications`}. {data.bottleneck_department ? `Current processing bottleneck by historical average: ${data.bottleneck_department}.` : ''}</div>
      </>}
    </main>
  </div>
}

function ChartPanel({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) { return <section className="admin-chart-panel"><header><div><h2>{title}</h2><p>{subtitle}</p></div></header>{children}</section> }
function PanelHeader({ title, eyebrow, action }: { title: string; eyebrow: string; action?: ReactNode }) { return <header className="admin-panel-heading"><div><span>{eyebrow}</span><h2>{title}</h2></div>{action}</header> }
function EmptyText({ children }: { children: ReactNode }) { return <p className="admin-empty">{children}</p> }
function HorizontalBars({ items, color = 'green' }: { items: Array<{ label: string; value: number; display?: string }>; color?: string }) {
  if (!items.length) return <EmptyText>No saved records for this chart.</EmptyText>
  const maximum = Math.max(...items.map((item) => item.value), 1)
  return <div className={`admin-bars ${color}`}>{items.map((item) => <div className="admin-bar-row" key={item.label}><span title={item.label}>{item.label}</span><div><i style={{ width: `${Math.max(item.value > 0 ? 3 : 0, item.value / maximum * 100)}%` }}/></div><b>{item.display ?? item.value}</b></div>)}</div>
}
function DecisionBars({ value }: { value: AdminData['approval_vs_rejection'] }) {
  const total = value.approved + value.rejected + value.active
  if (!total) return <EmptyText>No application outcomes have been recorded yet.</EmptyText>
  return <div className="decision-chart"><div><i className="approved" style={{ width: `${value.approved / total * 100}%` }}/><i className="rejected" style={{ width: `${value.rejected / total * 100}%` }}/><i className="active" style={{ width: `${value.active / total * 100}%` }}/></div><p><span>Approved <b>{value.approved}</b></span><span>Rejected <b>{value.rejected}</b></span><span>Active <b>{value.active}</b></span></p></div>
}
function MonthlyChart({ items }: { items: AdminData['monthly_volume'] }) {
  const max = Math.max(...items.map((item) => item.count), 1)
  const points = items.map((item, index) => `${(index / Math.max(items.length - 1, 1)) * 100},${90 - item.count / max * 76}`).join(' ')
  return <div className="admin-monthly"><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Monthly application volume line chart"><polyline points={points} fill="none" stroke="#397c56" strokeWidth="2" vectorEffect="non-scaling-stroke"/>{items.map((item, index) => <circle key={item.month} cx={(index / Math.max(items.length - 1, 1)) * 100} cy={90 - item.count / max * 76} r="1.7" fill="#397c56" vectorEffect="non-scaling-stroke"><title>{item.month}: {item.count}</title></circle>)}</svg><div>{items.filter((_, index) => index % 3 === 0 || index === items.length - 1).map((item) => <span key={item.month}>{item.month.slice(2)}</span>)}</div><small>{items.reduce((sum, item) => sum + item.count, 0)} submitted in the displayed period</small></div>
}
