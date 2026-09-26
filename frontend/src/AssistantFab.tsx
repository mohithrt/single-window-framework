import { useState } from 'react'

type Message = { role: 'USER' | 'ASSISTANT'; content: string }

export default function AssistantFab({ applicationId }: { applicationId: number }) {
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [messages, setMessages] = useState<Message[]>([
    { role: 'ASSISTANT', content: 'Hi! I can explain this application, its documents, approvals, risk, and what-if changes.' },
  ])

  async function ask(value = question) {
    const text = value.trim()
    if (!text || busy) return
    setQuestion(''); setBusy(true)
    setMessages(items => [...items, { role: 'USER', content: text }])
    try {
      const token = localStorage.getItem('mahaclear_access_token')
      const response = await fetch(`/api/applications/${applicationId}/assistant/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message: text }),
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.detail || 'Unable to contact MahaClear AI.')
      setMessages(items => [...items, { role: 'ASSISTANT', content: body.message?.content || 'I could not generate an answer.' }])
    } catch (error) {
      setMessages(items => [...items, { role: 'ASSISTANT', content: error instanceof Error ? error.message : 'Unable to contact MahaClear AI.' }])
    } finally { setBusy(false) }
  }

  return <>
    {open && <section className="assistant-fab-panel" aria-label="MahaClear AI chatbot">
      <header><div><strong>MahaClear AI</strong><small>Application assistant</small></div><button onClick={() => setOpen(false)} aria-label="Close">×</button></header>
      <div className="assistant-fab-messages">{messages.slice(-6).map((message, index) => <div key={index} className={`assistant-fab-message ${message.role.toLowerCase()}`}>{message.content}</div>)}{busy && <div className="assistant-fab-message assistant">Checking your application…</div>}</div>
      <div className="assistant-fab-suggestions"><button onClick={() => void ask('Which approval is currently delaying my application?')}>Current delay</button><button onClick={() => void ask('What documents are still missing or need correction?')}>Documents</button></div>
      <form onSubmit={event => { event.preventDefault(); void ask() }}><input value={question} onChange={event => setQuestion(event.target.value)} placeholder="Ask MahaClear AI…" aria-label="Ask MahaClear AI" /><button disabled={busy || !question.trim()}>→</button></form>
    </section>}
    <button className={`assistant-fab ${open ? 'open' : ''}`} onClick={() => setOpen(value => !value)} aria-label="Open MahaClear AI assistant"><span>✦</span><b>AI</b></button>
  </>
}
