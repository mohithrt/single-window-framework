import { apiUrl } from './apiBase'
import { useEffect, useState } from 'react'

type Notification = { id: number; application_id: number | null; notification_type: string; message: string; is_read: boolean; created_at: string }
type ListResponse = { total: number; unread_count: number; items: Notification[] }

export default function NotificationCenterPage() {
  const [data, setData] = useState<ListResponse | null>(null)
  const [home, setHome] = useState('/applicant')
  const [error, setError] = useState('')
  const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('mahaclear_access_token') ?? ''}`, 'Content-Type': 'application/json' })
  const refresh = async () => {
    const response = await fetch(apiUrl('/api/notifications'), { headers: headers() })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.detail || 'Could not load notifications.')
    setData(body)
  }
  useEffect(() => {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    void Promise.all([
      fetch(apiUrl('/api/auth/me'), { headers: { Authorization: `Bearer ${token}` } }).then((response) => response.json()),
      refresh(),
    ]).then(([user]) => setHome(user.role === 'OFFICER' ? '/officer' : user.role === 'ADMIN' ? '/admin' : '/applicant'))
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Could not load notifications.'))
  }, [])
  async function markRead(id: number) {
    try {
      const response = await fetch(apiUrl(`/api/notifications/${id}/read`), { method: 'PATCH', headers: headers() })
      if (!response.ok) throw new Error('Could not update notification state.')
      await refresh()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not update notification state.') }
  }
  async function markAllRead() {
    try {
      const response = await fetch(apiUrl('/api/notifications/read-all'), { method: 'PATCH', headers: headers() })
      if (!response.ok) throw new Error('Could not update notification state.')
      await refresh()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not update notification state.') }
  }
  return <div className="activity-page">
    <header className="activity-top"><a className="brand" href={home}><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a><a className="activity-back" href={home}>Back to workspace ↗</a></header>
    <main className="activity-main"><div className="breadcrumb">WORKSPACE <span>/</span> NOTIFICATIONS</div>
      <div className="activity-heading"><div><span className="eyebrow"><i /> IN-APP UPDATES</span><h1>Notifications</h1><p>Your application and department activity alerts.</p></div><button className="officer-button secondary" onClick={() => void markAllRead()} disabled={!data?.unread_count}>Mark all read · {data?.unread_count ?? 0}</button></div>
      {error && <div className="applicant-error" role="alert">{error}</div>}
      <section className="activity-panel">{!data ? <div className="loading-panel">Loading notifications…</div> : data.items.length === 0 ? <div className="empty-applications"><h3>You’re all caught up.</h3><p>New approval, inspection, and escalation updates will appear here.</p></div> : data.items.map((item) => <article className={`notification-row ${item.is_read ? 'read' : 'unread'}`} key={item.id}><span className="notification-dot"/><div><strong>{item.message}</strong><small>{item.notification_type.replaceAll('_', ' ')} · {new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(item.created_at))}</small>{item.application_id && <a href={home === '/applicant' ? `/applicant/applications/${item.application_id}/activity` : home}>Open related workspace →</a>}</div>{item.is_read ? <span className="notification-read-label">Read</span> : <button className="officer-button secondary" onClick={() => void markRead(item.id)}>Mark read</button>}</article>)}</section>
    </main>
  </div>
}
