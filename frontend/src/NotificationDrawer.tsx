import { useEffect, useState } from 'react'

type Notification = { id:number; application_id:number|null; notification_type:string; message:string; is_read:boolean; created_at:string }
type ResponseData = { unread_count:number; items:Notification[] }

export default function NotificationDrawer({onClose}:{onClose:()=>void}) {
  const [data,setData]=useState<ResponseData|null>(null)
  const [error,setError]=useState('')
  const token=localStorage.getItem('mahaclear_access_token')||''
  const headers={Authorization:`Bearer ${token}`,'Content-Type':'application/json'}
  async function refresh(){ const r=await fetch('/api/notifications',{headers}); const b=await r.json().catch(()=>({})); if(!r.ok) throw new Error(b.detail||'Could not load notifications.'); setData(b) }
  useEffect(()=>{ void refresh().catch(e=>setError(e instanceof Error?e.message:'Could not load notifications.')) },[])
  async function markRead(id:number){ const r=await fetch(`/api/notifications/${id}/read`,{method:'PATCH',headers}); if(!r.ok){setError('Could not update notification.');return} void refresh() }
  async function markAll(){ const r=await fetch('/api/notifications/read-all',{method:'PATCH',headers}); if(!r.ok){setError('Could not update notifications.');return} void refresh() }
  return <div className="notification-drawer-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}>
    <aside className="notification-drawer" aria-label="Notifications">
      <header><div><span className="card-kicker">IN-APP UPDATES</span><h2>Notifications</h2><p>{data?.unread_count??0} unread updates</p></div><button onClick={onClose} aria-label="Close notifications">×</button></header>
      <div className="notification-drawer-actions"><button onClick={()=>void markAll()} disabled={!data?.unread_count}>Mark all read</button></div>
      {error&&<div className="notification-drawer-error">{error}</div>}
      <div className="notification-drawer-list">{!data?<div className="loading-panel">Loading notifications…</div>:data.items.length===0?<div className="empty-applications"><h3>You're all caught up.</h3><p>New approval and department updates will appear here.</p></div>:data.items.map(n=><article className={n.is_read?'drawer-notification read':'drawer-notification'} key={n.id}><i/><div><strong>{n.message}</strong><small>{n.notification_type.replaceAll('_',' ')} · {new Intl.DateTimeFormat('en-IN',{dateStyle:'medium',timeStyle:'short'}).format(new Date(n.created_at))}</small>{n.application_id&&<a href={`/applicant/applications/${n.application_id}/activity`}>Open application →</a>}</div>{!n.is_read&&<button onClick={()=>void markRead(n.id)}>Read</button>}</article>)}</div>
    </aside>
  </div>
}
