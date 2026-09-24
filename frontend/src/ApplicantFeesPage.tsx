import { useEffect, useState } from 'react'

type Fee = {
  id: number
  application_id: number
  application_number: string | null
  company_name: string | null
  fee_code: string
  description: string
  amount: string
  currency: string
  status: 'ESTIMATED' | 'DUE' | 'PAID' | 'WAIVED'
  due_date: string | null
  paid_at: string | null
  receipt_reference: string | null
}
type FeeList = { items: Fee[]; total_due: string; total_paid: string }

function money(amount: string, currency: string) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(amount))
}
function date(value: string | null) {
  return value ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(value)) : '—'
}

export default function ApplicantFeesPage() {
  const [data, setData] = useState<FeeList | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    void fetch('/api/fees', { headers: { Authorization: 'Bearer ' + token } })
      .then(async response => {
        const body = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Unable to load fee records.')
        setData(body as FeeList)
      })
      .catch(caught => setError(caught instanceof Error ? caught.message : 'Unable to load fee records.'))
  }, [])
  const signOut = () => { localStorage.removeItem('mahaclear_access_token'); window.location.assign('/login') }
  return <div className="applicant-shell">
    <header className="applicant-topbar">
      <a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a>
      <nav className="applicant-top-nav" aria-label="Applicant navigation"><a href="/applicant">Dashboard</a><a href="/applicant#applications">Applications</a><a className="active" href="/applicant/fees">Fees</a><a href="/notifications">Notifications</a></nav>
      <button className="applicant-signout" onClick={signOut}>Sign out <span>↗</span></button>
    </header>
    <aside className="applicant-sidebar"><div className="workspace-nav-label">APPLICANT WORKSPACE</div>
      <a className="side-link" href="/applicant"><span>◫</span> Dashboard</a>
      <a className="side-link" href="/applicant#applications"><span>▤</span> My applications</a>
      <a className="side-link selected" href="/applicant/fees"><span>₹</span> Fee ledger</a>
      <a className="side-link" href="/notifications"><span>◉</span> Notifications</a>
      <div className="sidebar-note"><span className="sidebar-note-mark">✳</span><strong>One window.<br />Every approval.</strong><small>North-Star · SIH 2026</small></div>
      <div className="sidebar-bottom">MAHACLEAR-AI <span>·</span> APPLICANT</div>
    </aside>
    <main className="applicant-main">
      <div className="breadcrumb">APPLICANT WORKSPACE <span>/</span> FEE LEDGER</div>
      <div className="applicant-heading"><div><span className="eyebrow"><i /> TRANSPARENT RECORDS</span><h1>Fee ledger</h1><p>View estimated, due, and recorded demo fee entries for your applications.</p></div></div>
      <div className="fee-disclaimer" role="note">Prototype fee records are demonstration data only. They are not statutory government charges and do not accept payments.</div>
      {error ? <div className="applicant-error" role="alert">{error} <button onClick={() => window.location.reload()}>Retry</button></div>
        : !data ? <div className="loading-panel" role="status">Loading fee records…</div>
          : <>
            <section className="fee-summary" aria-label="Fee totals">
              <article><span>AMOUNT DUE</span><strong>{money(data.total_due, 'INR')}</strong><small>Across saved fee records</small></article>
              <article><span>RECORDED AS PAID</span><strong>{money(data.total_paid, 'INR')}</strong><small>Demo ledger entries</small></article>
              <article><span>FEE RECORDS</span><strong>{data.items.length}</strong><small>For your applications</small></article>
            </section>
            <section className="applications-panel fee-panel">
              <div className="applications-panel-heading"><div><span className="card-kicker">APPLICATION CHARGES</span><h2>Fee register</h2></div><span className="application-count">{data.items.length} RECORDS</span></div>
              {data.items.length ? <div className="application-table-wrap"><table className="application-table">
                <thead><tr><th>APPLICATION</th><th>COMPANY</th><th>DESCRIPTION</th><th>AMOUNT</th><th>STATUS</th><th>DUE / PAID</th><th>REFERENCE</th></tr></thead>
                <tbody>{data.items.map(item => <tr key={item.id}>
                  <td><a className="table-action" href={'/applicant/applications/' + item.application_id + '/view'}>{item.application_number ?? ('Application ' + item.application_id)}</a></td>
                  <td>{item.company_name ?? '—'}</td><td>{item.description}</td><td>{money(item.amount, item.currency)}</td>
                  <td><span className={'fee-status ' + item.status.toLowerCase()}>{item.status.replace('_', ' ')}</span></td>
                  <td>{item.status === 'PAID' ? date(item.paid_at) : date(item.due_date)}</td><td>{item.receipt_reference ?? '—'}</td>
                </tr>)}</tbody>
              </table></div> : <div className="empty-applications"><span className="empty-mark">₹</span><h3>No fee records yet</h3><p>Fee records appear here when they are attached to your applications.</p><a className="primary-button button-link" href="/applicant">View applications <span>→</span></a></div>}
            </section>
          </>}
    </main>
    <footer className="workspace-footer"><span>MAHACLEAR-AI <span>· Fee transparency</span></span><span>TEAM NORTH-STAR <i>·</i> SIH 2026</span></footer>
  </div>
}
