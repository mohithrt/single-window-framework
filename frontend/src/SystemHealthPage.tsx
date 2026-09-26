import { useEffect, useState } from 'react'

type Health = {
  status: string
  service: string
  checks: Record<string, { status: string; [key: string]: unknown }>
  features: { redis_enabled: boolean; external_notifications: boolean; configured_integrations: string[] }
}

export default function SystemHealthPage() {
  const [data, setData] = useState<Health | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    fetch('/api/admin/system-health', { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        const body = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(body.detail || 'Unable to load system health.')
        return body as Health
      })
      .then(setData)
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Unable to load system health.'))
  }, [])

  async function signOut() {
    localStorage.removeItem('mahaclear_access_token')
    window.location.assign('/login')
  }

  return <div className="admin-shell">
    <header className="admin-topbar">
      <a className="brand" href="/admin"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a>
      <span className="admin-authority-chip">APEX AUTHORITY · SYSTEM HEALTH</span>
      <nav><a href="/notifications">Notifications</a><button className="signout-button" onClick={() => void signOut()}>Sign out ↗</button></nav>
    </header>
    <aside className="admin-sidebar">
      <span className="workspace-nav-label">GOVERNMENT WORKSPACE</span>
      <a href="/admin">Overview</a>
      <a href="/admin#analytics">Analytics</a>
      <a href="/admin#departments">Departments</a>
      <a href="/admin#applications">Applications</a>
      <a href="/admin#audit">Audit log</a>
      <a href="/admin#integrations">Integrations</a>
      <a href="/admin/system-health">System health</a>
      <div><strong>North-Star</strong><small>SIH 2026 · Apex Authority</small></div>
    </aside>
    <main className="admin-main">
      <div className="breadcrumb">GOVERNMENT WORKSPACE <span>/</span> SYSTEM HEALTH</div>
      <div className="admin-heading"><div><span className="eyebrow"><i/> PLATFORM DIAGNOSTICS</span><h1>System health</h1><p>Checks database, cache, OCR, AI configuration and external integration readiness without sending test application data.</p></div></div>
      {error && <div className="applicant-error" role="alert">{error}</div>}
      {data && <>
        <section className="admin-kpis">
          <article><span>OVERALL STATUS</span><strong>{data.status.toUpperCase()}</strong></article>
          <article><span>REDIS</span><strong>{data.checks.cache?.mode?.toString().toUpperCase() || '—'}</strong></article>
          <article><span>OCR</span><strong>{data.checks.ocr?.status?.toString().toUpperCase() || '—'}</strong></article>
          <article><span>LLM</span><strong>{data.checks.llm?.status?.toString().toUpperCase() || '—'}</strong></article>
          <article><span>LIVE INTEGRATIONS</span><strong>{data.features.configured_integrations.length}</strong></article>
        </section>
        <section className="admin-panel">
          <header className="admin-panel-heading"><div><span>DEPENDENCY CHECKS</span><h2>Runtime readiness</h2></div><a href="/admin">Back to dashboard →</a></header>
          <div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>SERVICE</th><th>STATUS</th><th>DETAILS</th></tr></thead><tbody>
            {Object.entries(data.checks).map(([name, check]) => <tr key={name}><td><strong>{name.toUpperCase()}</strong></td><td><span className={`admin-risk ${check.status === 'ok' || check.status === 'configured' || check.status === 'mock' || check.status === 'rule_based' ? 'low' : 'high'}`}>{check.status}</span></td><td>{Object.entries(check).filter(([key]) => key !== 'status').map(([key, value]) => `${key}: ${String(value)}`).join(' · ') || 'No additional details'}</td></tr>)}
          </tbody></table></div>
        </section>
        <section className="admin-panel"><header className="admin-panel-heading"><div><span>SAFETY</span><h2>Configuration policy</h2></div></header>
          <p className="admin-notice">Mock integrations remain the default. External API calls, email, SMS and Redis are opt-in through environment configuration. A missing external dependency does not stop the core approval workflow.</p>
        </section>
      </>}
    </main>
  </div>
}
