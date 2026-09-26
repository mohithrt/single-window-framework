import { apiUrl } from './apiBase'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

type Message = { id: number; role: 'USER' | 'ASSISTANT'; content: string; structured_data?: Record<string, unknown> | null; created_at?: string }
type Session = { id: number; title: string }

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem('mahaclear_access_token')
  if (!token) { window.location.assign('/login'); throw new Error('Sign in to continue.') }
  const response = await fetch(path, { ...init, headers: { Authorization: `Bearer ${token}`, ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...init?.headers } })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || 'The request could not be completed.')
  return body as T
}

export default function MahaClearAssistantPage({ applicationId }: { applicationId: number }) {
  const [application, setApplication] = useState<{ application_number: string; company_name: string | null } | null>(null)
  const [sessions, setSessions] = useState<Session[]>([])
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [assistantMode, setAssistantMode] = useState('DEMO AI · RULE-BASED')
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    void Promise.all([
      api<{ application_number: string; company_name: string | null }>(apiUrl(`/api/applications/${applicationId}`)),
      api<{ items: Session[] }>(apiUrl(`/api/applications/${applicationId}/assistant/sessions`)),
    ]).then(async ([app, saved]) => {
      setApplication(app); setSessions(saved.items)
      if (saved.items[0]) {
        const history = await api<{ messages: Message[] }>(apiUrl(`/api/applications/${applicationId}/assistant/sessions/${saved.items[0].id}`))
        setSessionId(saved.items[0].id); setMessages(history.messages)
      }
    }).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Unable to load the assistant.'))
  }, [applicationId])

  async function send(event: FormEvent) {
    event.preventDefault()
    const text = question.trim()
    if (!text || busy) return
    setError(''); setBusy(true)
    const userMessage: Message = { id: Date.now(), role: 'USER', content: text }
    setMessages((items) => [...items, userMessage]); setQuestion('')
    try {
      const result = await api<{ session_id: number; mode: string; message: Message }>(apiUrl(`/api/applications/${applicationId}/assistant/chat`), {
        method: 'POST', body: JSON.stringify({ message: text, session_id: sessionId }),
      })
      setAssistantMode(result.mode === 'LLM_ASSISTED' ? 'OPTIONAL LLM · RULE-GROUNDED' : 'DEMO AI · RULE-BASED')
      setSessionId(result.session_id); setMessages((items) => [...items, result.message])
      const saved = await api<{ items: Session[] }>(apiUrl(`/api/applications/${applicationId}/assistant/sessions`))
      setSessions(saved.items)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to send your question.')
      setMessages((items) => items.filter((item) => item.id !== userMessage.id))
      setQuestion(text)
    } finally { setBusy(false) }
  }

  async function openSession(id: number) {
    try {
      const result = await api<{ messages: Message[] }>(apiUrl(`/api/applications/${applicationId}/assistant/sessions/${id}`))
      setSessionId(id); setMessages(result.messages); setError('')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to load this conversation.') }
  }

  return <div className="activity-page">
    <header className="activity-top"><a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a><a className="activity-back" href={`/applicant/applications/${applicationId}/activity`}>Application activity ↗</a></header>
    <main className="activity-main assistant-layout">
      <div className="breadcrumb">APPLICANT WORKSPACE <span>/</span> MAHACLEAR AI ASSISTANT</div>
      <div className="activity-heading"><div><span className="eyebrow"><i /> APPLICATION-SCOPED ASSISTANT</span><h1>MahaClear AI Assistant</h1><p>{application?.application_number ?? `Application ${applicationId}`} · {application?.company_name ?? 'Company details'}</p></div><span className="assistant-mode">{assistantMode}</span></div>
      <div className="assistant-columns">
        <aside className="activity-section assistant-history"><header><span className="card-kicker">SAVED CONVERSATIONS</span><h2>History</h2></header>{sessions.length ? sessions.map((item) => <button className={item.id === sessionId ? 'selected' : ''} key={item.id} onClick={() => void openSession(item.id)}>{item.title}</button>) : <p className="activity-empty">Questions and answers are saved here.</p>}<button className="assistant-new" onClick={() => { setSessionId(null); setMessages([]); setError('') }}>+ New conversation</button></aside>
        <section className="activity-section assistant-chat"><div className="assistant-context"><strong>Context-aware for this application</strong><span>Risk, saved approvals and dependencies, required documents, recorded timeline, inspections, and configured rule durations.</span><small>Government requirements and fees are not invented. The demo has no configured fee schedule and does not submit anything to government systems.</small></div>
          <div className="assistant-messages" aria-live="polite">{messages.length ? messages.map((message) => <article key={message.id} className={`assistant-message ${message.role.toLowerCase()}`}><span>{message.role === 'USER' ? 'YOU' : message.content.startsWith('Demo AI / Rule-based') ? 'MAHACLEAR · DEMO RULE-BASED' : 'MAHACLEAR · OPTIONAL LLM'}</span><p>{message.content}</p>{message.structured_data && <WhatIfSummary value={message.structured_data}/>}</article>) : <div className="assistant-empty"><span className="assistant-star">✳</span><h2>What would you like to explore?</h2><p>Ask a question about changes to this application, or ask which approval is currently delaying it.</p><div className="assistant-suggestions"><button onClick={() => setQuestion('What happens if I increase my factory area from 10,000 sq ft to 30,000 sq ft?')}>What if I increase factory area?</button><button onClick={() => setQuestion('What if I remove hazardous chemicals?')}>What if I remove hazardous chemicals?</button><button onClick={() => setQuestion('Which approval is currently delaying my application?')}>Which approval is delaying me?</button></div></div>}{busy && <div className="assistant-thinking">Checking the configured rules and current application records…</div>}</div>
          {error && <div className="applicant-error" role="alert">{error}</div>}
          <form className="assistant-compose" onSubmit={(event) => void send(event)}><textarea value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={2000} placeholder="Ask about a proposed change or your current workflow…" aria-label="Your question"/><button className="officer-button primary" disabled={busy || !question.trim()}>{busy ? 'Checking…' : 'Ask assistant →'}</button></form>
        </section>
      </div>
    </main>
  </div>
}

function WhatIfSummary({ value }: { value: Record<string, unknown> }) {
  const risk = value.risk_change as Record<string, unknown> | undefined
  if (!risk) return null
  const affected = value.affected_departments as Array<{ department: string; effect: string }> | undefined
  const docs = value.additional_documents as Array<{ name: string }> | undefined
  return <div className="assistant-impact"><strong>Scenario estimate</strong><div><span>Risk</span><b>{String(risk.score_before)} → {String(risk.score_after)} · {String(risk.tier_before)} → {String(risk.tier_after)}</b></div><div><span>Workflow time</span><b>{Number(value.estimated_time_change_days) > 0 ? '+' : ''}{String(value.estimated_time_change_days)} days</b></div><div><span>Department changes</span><b>{affected?.length ? affected.map((row) => `${row.effect}: ${row.department}`).join(' · ') : 'No routing change from configured rules'}</b></div><div><span>Possible documents</span><b>{docs?.length ? docs.map((row) => row.name).join(' · ') : 'No new document types identified'}</b></div><small>Planning estimate based on configured rules. Inspection decisions remain with officers; fees are unconfigured.</small></div>
}
