import { apiUrl } from './apiBase'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'

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
  const [assistantMode, setAssistantMode] = useState('AI ASSISTANT · READY')
  const [question, setQuestion] = useState('')
  const [retryQuestion, setRetryQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const messagesEnd = useRef<HTMLDivElement>(null)

  useEffect(() => { messagesEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages, busy])

  useEffect(() => {
    void Promise.all([
      api<{ application_number: string; company_name: string | null }>(apiUrl(`/api/applications/${applicationId}`)),
      api<{ items: Session[] }>(apiUrl(`/api/applications/${applicationId}/assistant/sessions`)),
    ]).then(async ([app, saved]) => {
      setApplication(app); setSessions(saved.items)
      if (saved.items[0]) {
        const history = await api<{ messages: Message[] }>(apiUrl(`/api/applications/${applicationId}/assistant/sessions/${saved.items[0].id}`))
        setSessionId(saved.items[0].id); setMessages(history.messages)
        const lastAssistant = [...history.messages].reverse().find((item) => item.role === 'ASSISTANT')
        if (lastAssistant?.structured_data?.assistant_mode) setAssistantMode(String(lastAssistant.structured_data.assistant_mode).replaceAll('_', ' '))
      }
    }).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Unable to load the assistant.'))
  }, [applicationId])

  async function sendQuestion(input: string) {
    const text = input.trim()
    if (!text || busy) return
    setError(''); setRetryQuestion(''); setBusy(true)
    const userMessage: Message = { id: Date.now(), role: 'USER', content: text, created_at: new Date().toISOString() }
    setMessages((items) => [...items, userMessage]); setQuestion('')
    try {
      const result = await api<{ session_id: number; mode: string; message: Message }>(apiUrl(`/api/applications/${applicationId}/assistant/chat`), {
        method: 'POST', body: JSON.stringify({ message: text, session_id: sessionId }),
      })
      setAssistantMode(result.mode === 'AI_ASSISTED' ? 'AI POWERED · APPLICATION-GROUNDED' : 'BUILT-IN FALLBACK · AI UNAVAILABLE')
      setSessionId(result.session_id); setMessages((items) => [...items, result.message])
      const saved = await api<{ items: Session[] }>(apiUrl(`/api/applications/${applicationId}/assistant/sessions`))
      setSessions(saved.items)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to send your question.')
      setMessages((items) => items.filter((item) => item.id !== userMessage.id))
      setRetryQuestion(text)
    } finally { setBusy(false) }
  }

  async function send(event: FormEvent) {
    event.preventDefault()
    await sendQuestion(question)
  }

  async function openSession(id: number) {
    try {
      const result = await api<{ messages: Message[] }>(apiUrl(`/api/applications/${applicationId}/assistant/sessions/${id}`))
      setSessionId(id); setMessages(result.messages); setError(''); setRetryQuestion('')
      const lastAssistant = [...result.messages].reverse().find((item) => item.role === 'ASSISTANT')
      setAssistantMode(lastAssistant?.structured_data?.assistant_mode === 'AI_ASSISTED' ? 'AI POWERED · APPLICATION-GROUNDED' : 'BUILT-IN FALLBACK · AI UNAVAILABLE')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to load this conversation.') }
  }

  function onComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit() }
  }

  return <div className="activity-page">
    <header className="activity-top"><a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a><a className="activity-back" href={`/applicant/applications/${applicationId}/activity`}>Application activity ↗</a></header>
    <main className="activity-main assistant-layout">
      <div className="breadcrumb">APPLICANT WORKSPACE <span>/</span> MAHACLEAR AI ASSISTANT</div>
      <div className="activity-heading"><div><span className="eyebrow"><i /> APPLICATION-SCOPED ASSISTANT</span><h1>MahaClear AI Assistant</h1><p>{application?.application_number ?? `Application ${applicationId}`} · {application?.company_name ?? 'Company details'}</p></div><span className={`assistant-mode ${assistantMode.startsWith('BUILT-IN') ? 'unavailable' : ''}`}>{assistantMode}</span></div>
      <div className="assistant-columns">
        <aside className="activity-section assistant-history"><header><span className="card-kicker">SAVED CONVERSATIONS</span><h2>History</h2></header>{sessions.length ? sessions.map((item) => <button className={item.id === sessionId ? 'selected' : ''} key={item.id} onClick={() => void openSession(item.id)} title={item.title}>{item.title}</button>) : <p className="activity-empty">Questions and answers are saved here.</p>}<button className="assistant-new" onClick={() => { setSessionId(null); setMessages([]); setError(''); setRetryQuestion(''); setQuestion('') }}>+ New conversation</button></aside>
        <section className="activity-section assistant-chat"><div className="assistant-context"><strong>Application context · {application?.application_number ?? `#${applicationId}`}</strong><span>Answers can retrieve saved status, approvals, risk, documents, SLA, inspections, and timeline. Scenario analysis uses the configured business rules.</span><small>Application records are the source of truth. General information is identified separately; this prototype does not connect to government systems.</small></div>
          <div className="assistant-messages" aria-live="polite">{messages.length ? messages.map((message) => <article key={message.id} className={`assistant-message ${message.role.toLowerCase()}`}><span>{message.role === 'USER' ? 'YOU' : message.structured_data?.assistant_mode === 'AI_ASSISTED' ? 'MAHACLEAR · AI ASSISTANT' : 'MAHACLEAR · BUILT-IN FALLBACK'}</span><p>{message.content}</p><time>{message.created_at ? new Date(message.created_at).toLocaleString() : ''}</time>{Boolean(message.structured_data?.tools_used) && <small className="assistant-grounding">Grounded using: {(message.structured_data?.tools_used as Array<{name: string}>).map((item) => item.name.replaceAll('_', ' ')).join(', ')}</small>}{message.structured_data && <WhatIfSummary value={message.structured_data}/>}</article>) : <div className="assistant-empty"><span className="assistant-star">✳</span><h2>What would you like to explore?</h2><p>Ask naturally. MahaClear AI checks this application’s saved records before answering.</p><div className="assistant-suggestions"><button onClick={() => setQuestion('Where is my application right now?')}>Where is my application now?</button><button onClick={() => setQuestion('What documents am I missing?')}>What documents are missing?</button><button onClick={() => setQuestion('What is causing the delay?')}>What is causing the delay?</button><button onClick={() => setQuestion('Explain my risk score.')}>Explain my risk score</button><button onClick={() => setQuestion('What happens next?')}>What happens next?</button><button onClick={() => setQuestion('What does MPCB do?')}>What does MPCB do?</button></div></div>}{busy && <div className="assistant-thinking"><span className="assistant-spinner"/> Checking authorized application records…</div>}<div ref={messagesEnd}/></div>
          {error && <div className="applicant-error" role="alert">{error}</div>}
          {retryQuestion && <button className="assistant-retry" disabled={busy} onClick={() => void sendQuestion(retryQuestion)}>Retry your last question</button>}
          <form className="assistant-compose" onSubmit={(event) => void send(event)}><textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={onComposerKeyDown} maxLength={2000} placeholder="Ask about this application… (Enter to send, Shift+Enter for a new line)" aria-label="Your question"/><button className="officer-button primary" disabled={busy || !question.trim()}>{busy ? 'Thinking…' : 'Send →'}</button></form>
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
