import { useEffect, useState } from 'react'

type Notification = { id: number; application_id: number | null; notification_type: string; message: string; is_read: boolean; created_at: string }
type ListResponse = { total: number; unread_count: number; items: Notification[] }

export default function NotificationCenterPage() {
  const [data, setData] = useState<ListResponse | null>(null)
  const [home, setHome] = useState('/applicant')
  const [role, setRole] = useState('APPLICANT')
  const [error, setError] = useState('')
  const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('mahaclear_access_token') ?? ''}`, 'Content-Type': 'application/json' })

  const refresh = async () => {
    const response = await fetch('/api/notifications', { headers: headers() })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.detail || 'Could not load notifications.')
    setData(body)
  }

  useEffect(() => {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    void Promise.all([
      fetch('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } }).then(async response => {
        if (!response.ok) throw new Error('Your session has expired. Sign in again.')
        return response.json()
      }),
      refresh(),
    ]).then(([user]) => {
      setRole(user.role)
      setHome(user.role === 'OFFICER' ? '/officer' : user.role === 'ADMIN' ? '/admin' : '/applicant')
    }).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Could not load notifications.'))
  }, [])

  async function markRead(id: number) {
    try {
      const response = await fetch(`/api/notifications/${id}/read`, { method: 'PATCH', headers: headers() })
      if (!response.ok) throw new Error('Could not update notification state.')
      await refresh()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not update notification state.') }
  }

  async function markAllRead() {
    try {
      const response = await fetch('/api/notifications/read-all', { method: 'PATCH', headers: headers() })
      if (!response.ok) throw new Error('Could not update notification state.')
      await refresh()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not update notification state.') }
  }

  const signOut = () => { localStorage.removeItem('mahaclear_access_token'); window.location.assign('/login') }
  const applicant = role === 'APPLICANT'

  return applicant ? (
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
        <a className="side-link selected" href="/notifications"><span>◉</span> Notifications</a>
        <div className="sidebar-note"><span className="sidebar-note-mark">✳</span><strong>One window.<br />Every approval.</strong><small>North-Star · SIH 2026</small></div>
        <div className="sidebar-bottom">MAHACLEAR-AI <span>·</span> APPLICANT</div>
      </aside>
      <main className="applicant-main">
        <div className="breadcrumb">APPLICANT WORKSPACE <span>/</span> NOTIFICATIONS</div>
        <div className="applicant-heading"><div><span className="eyebrow"><i /> IN-APP UPDATES</span><h1>Notifications</h1><p>Your application and department activity alerts.</p></div><button className="primary-button" onClick={() => void markAllRead()} disabled={!data?.unread_count}>Mark all read <span>✓</span></button></div>
        {error && <div className="applicant-error" role="alert">{error}</div>}
        <section className="applications-panel notification-panel">{!data ? <div className="loading-panel">Loading notifications…</div> : data.items.length === 0 ? <div className="empty-applications"><span className="empty-mark">✓</span><h3>You’re all caught up.</h3><p>New approval, inspection, and escalation updates will appear here.</p></div> : data.items.map(item => <article className={`notification-row ${item.is_read ? 'read' : 'unread'}`} key={item.id}><span className="notification-dot"/><div><strong>{item.message}</strong><small>{item.notification_type.replaceAll('_', ' ')} · {new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(item.created_at))}</small>{item.application_id && <a href={`/applicant/applications/${item.application_id}/activity`}>Open related application →</a>}</div>{item.is_read ? <span className="notification-read-label">Read</span> : <button className="table-action notification-mark-read" onClick={() => void markRead(item.id)}>Mark read</button>}</article>)}</section>
      </main>
      <footer className="workspace-footer"><span>MAHACLEAR-AI <span>· Notifications</span></span><span>TEAM NORTH-STAR <i>·</i> SIH 2026</span></footer>
    </div>
  ) : (
    <div className="activity-page">
      <header className="activity-top"><a className="brand" href={home}><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a><a className="activity-back" href={home}>Back to workspace ↗</a></header>
      <main className="activity-main"><div className="breadcrumb">WORKSPACE <span>/</span> NOTIFICATIONS</div><div className="activity-heading"><div><span className="eyebrow"><i /> IN-APP UPDATES</span><h1>Notifications</h1><p>Your application and department activity alerts.</p></div><button className="officer-button secondary" onClick={() => void markAllRead()} disabled={!data?.unread_count}>Mark all read · {data?.unread_count ?? 0}</button></div>{error && <div className="applicant-error" role="alert">{error}</div>}<section className="activity-panel">{!data ? <div className="loading-panel">Loading notifications…</div> : data.items.length === 0 ? <div className="empty-applications"><h3>You’re all caught up.</h3><p>New approval, inspection, and escalation updates will appear here.</p></div> : data.items.map(item => <article className={`notification-row ${item.is_read ? 'read' : 'unread'}`} key={item.id}><span className="notification-dot"/><div><strong>{item.message}</strong><small>{item.notification_type.replaceAll('_', ' ')} · {new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(item.created_at))}</small>{item.application_id && <a href={`/applicant/applications/${item.application_id}/activity`}>Open related application →</a>}</div>{item.is_read ? <span className="notification-read-label">Read</span> : <button className="officer-button secondary" onClick={() => void markRead(item.id)}>Mark read</button>}</article>)}</section></main>
    </div>
  )
}
