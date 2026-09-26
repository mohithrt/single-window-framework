import { FormEvent, useEffect, useMemo, useState } from 'react'

type Role = 'APPLICANT' | 'OFFICER' | 'ADMIN'
type Message = { role: 'user' | 'assistant'; content: string }

type Props = {
  applicationId?: number
}

export default function AssistantFab({ applicationId }: Props) {
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [role, setRole] = useState<Role | null>(null)
  const [messages, setMessages] = useState<Message[]>([])

  const page = useMemo(() => window.location.pathname.replace(/^\//, '') || 'workspace', [])

  useEffect(() => {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) return
    void fetch('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => response.ok ? response.json() : null)
      .then((user) => {
        if (!user?.role) return
        const nextRole = user.role as Role
        setRole(nextRole)
        setMessages([{
          role: 'assistant',
          content:
            nextRole === 'APPLICANT'
              ? "Hi! I'm MahaClear AI. I can help with applications, documents, delays, approvals and next steps."
              : nextRole === 'OFFICER'
                ? "Hi! I'm MahaClear AI Officer Copilot. I can help with queue review, documents, inspections, SLA and escalations."
                : "Hi! I'm MahaClear AI Admin Copilot. I can help with analytics, audit, integrations and system health.",
        }])
      })
      .catch(() => {})
  }, [])

  async function askAssistant(event?: FormEvent) {
    event?.preventDefault()
    const question = input.trim()
    if (!question || loading) return
    setMessages((prev) => [...prev, { role: 'user', content: question }])
    setInput('')
    setLoading(true)

    try {
      const token = localStorage.getItem('mahaclear_access_token')
      const endpoint = applicationId
        ? `/api/applications/${applicationId}/assistant/chat`
        : '/api/assistant/chat'
      const body = applicationId
        ? { message: question }
        : { message: question, page }
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Assistant request failed')
      const answer = data?.message?.content || data?.answer || data?.response || "I couldn't generate a response right now."
      setMessages((prev) => [...prev, { role: 'assistant', content: answer }])
    } catch (caught) {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: caught instanceof Error ? caught.message : 'Something went wrong. Please try again.',
      }])
    } finally {
      setLoading(false)
    }
  }

  const roleTitle = role === 'OFFICER' ? 'Officer Copilot' : role === 'ADMIN' ? 'Admin Copilot' : 'MahaClear AI'
  const suggestions = role === 'OFFICER'
    ? ['What is pending?', 'Any SLA delays?', 'How do inspections work?']
    : role === 'ADMIN'
      ? ['System health', 'Show analytics help', 'Explain audit log']
      : ['Application status', 'Check my documents', 'What is my next step?']

  return (
    <>
      <button className="assistant-fab" type="button" onClick={() => setOpen((value) => !value)} aria-label="Open MahaClear AI assistant">
        <span>✦</span><b>AI</b>
      </button>
      {open && (
        <section className="assistant-fab-panel" aria-label={roleTitle}>
          <header className="assistant-fab-header">
            <div><strong>{roleTitle}</strong><small>{applicationId ? 'Application Assistant' : role ? `${role} workspace assistant` : 'Workspace assistant'}</small></div>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close assistant">×</button>
          </header>
          <div className="assistant-fab-messages">
            {messages.slice(-8).map((message, index) => <div key={`${message.role}-${index}`} className={`assistant-fab-message ${message.role}`}>{message.content}</div>)}
            {!role && <div className="assistant-fab-message assistant">Loading your role assistant…</div>}
            {loading && <div className="assistant-fab-message assistant">Thinking…</div>}
          </div>
          <div className="assistant-fab-suggestions">
            {suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => setInput(suggestion)}>{suggestion}</button>)}
          </div>
          <form className="assistant-fab-form" onSubmit={askAssistant}>
            <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask MahaClear AI…" disabled={loading || !role} />
            <button type="submit" disabled={loading || !input.trim() || !role}>{loading ? '…' : 'Send'}</button>
          </form>
        </section>
      )}
    </>
  )
}
