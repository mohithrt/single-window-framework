import { FormEvent, useState } from 'react'

type Message = {
  role: 'user' | 'assistant'
  content: string
}

type Props = {
  applicationId: number
}

export default function AssistantFab({ applicationId }: Props) {
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content:
        "Hi! I'm MahaClear AI. I can help with your application status, documents, delays and next steps.",
    },
  ])

  async function askAssistant(event?: FormEvent) {
    event?.preventDefault()
    const question = input.trim()
    if (!question || loading) return

    setMessages((prev) => [...prev, { role: 'user', content: question }])
    setInput('')
    setLoading(true)

    try {
      const token = localStorage.getItem('mahaclear_access_token')
      const response = await fetch(
        `/api/applications/${applicationId}/assistant/chat`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ message: question }),
        },
      )

      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || 'Assistant request failed')
      }

      const answer =
        data?.answer ||
        data?.response ||
        data?.message ||
        "I couldn't generate a response right now."

      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: answer },
      ])
    } catch (caught) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            caught instanceof Error
              ? caught.message
              : 'Something went wrong. Please try again.',
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <button
        className="assistant-fab"
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label="Open MahaClear AI assistant"
      >
        ✦
      </button>

      {open && (
        <section className="assistant-fab-panel">
          <header className="assistant-fab-header">
            <div>
              <strong>MahaClear AI</strong>
              <small>Application Assistant</small>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close assistant"
            >
              ×
            </button>
          </header>

          <div className="assistant-fab-messages">
            {messages.slice(-6).map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`assistant-fab-message ${message.role}`}
              >
                {message.content}
              </div>
            ))}
            {loading && (
              <div className="assistant-fab-message assistant">
                Thinking...
              </div>
            )}
          </div>

          <div className="assistant-fab-suggestions">
            <button
              type="button"
              onClick={() => setInput('Why is my application delayed?')}
            >
              Current delay
            </button>
            <button
              type="button"
              onClick={() => setInput('Are all my documents valid?')}
            >
              Documents
            </button>
          </div>

          <form className="assistant-fab-form" onSubmit={askAssistant}>
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask MahaClear AI..."
              disabled={loading}
            />
            <button type="submit" disabled={loading || !input.trim()}>
              {loading ? '...' : 'Send'}
            </button>
          </form>
        </section>
      )}
    </>
  )
}
