/**
 * Chat assistant panel — collapsible, scoped to selected company.
 * Uses SSE streaming from POST /sessions/{id}/companies/{cid}/chat.
 */
import { useRef, useState } from 'react'
import { api } from '../api/client'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface Props {
  sessionId: string
  companyId: string
  companyName: string
}

export function ChatAssistant({ sessionId, companyId, companyName }: Props) {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  async function sendMessage() {
    const text = input.trim()
    if (!text || streaming) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setStreaming(true)

    // Append an empty assistant message to stream into
    setMessages(prev => [...prev, { role: 'assistant', content: '' }])

    try {
      const response = await fetch(`${api.defaults.baseURL}/sessions/${sessionId}/companies/${companyId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })

      if (!response.body) throw new Error('No response body')
      const reader = response.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') break
            setMessages(prev => {
              const msgs = [...prev]
              const last = msgs[msgs.length - 1]
              if (last?.role === 'assistant') {
                msgs[msgs.length - 1] = { ...last, content: last.content + data }
              }
              return msgs
            })
          }
        }
      }
    } catch (err) {
      setMessages(prev => {
        const msgs = [...prev]
        const last = msgs[msgs.length - 1]
        if (last?.role === 'assistant' && last.content === '') {
          msgs[msgs.length - 1] = { ...last, content: 'Error: Could not get response.' }
        }
        return msgs
      })
    } finally {
      setStreaming(false)
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <div className="border-t border-gray-200">
      {/* Toggle button */}
      <button
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center justify-between px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
        aria-expanded={open}
      >
        <span>Chat — {companyName}</span>
        <span className="text-gray-400">{open ? '▼' : '▲'}</span>
      </button>

      {open && (
        <div className="flex flex-col h-64">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {messages.length === 0 && (
              <p className="text-xs text-gray-400 text-center">
                Ask questions about {companyName}'s signals and drafts.
              </p>
            )}
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`text-sm rounded-lg px-3 py-2 max-w-[85%] ${
                  msg.role === 'user'
                    ? 'ml-auto bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-900'
                }`}
              >
                {msg.content}
                {streaming && i === messages.length - 1 && msg.role === 'assistant' && (
                  <span className="animate-pulse">▌</span>
                )}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="flex gap-2 border-t border-gray-200 p-2">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void sendMessage() } }}
              placeholder="Ask about signals, personas, or drafts…"
              className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={streaming}
              aria-label="Chat input"
            />
            <button
              onClick={() => void sendMessage()}
              disabled={streaming || !input.trim()}
              className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
