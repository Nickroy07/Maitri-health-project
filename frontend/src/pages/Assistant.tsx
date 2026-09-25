/**
 * pages/Assistant.tsx
 * Protocol assistant chat interface for MAITRI.
 *
 * - Chat-style UI: user messages on the right, assistant responses on the left.
 * - Each assistant response shows the retrieved protocol excerpt text and a
 *   source label (slightly muted colour).
 * - POSTs to /api/assistant/ask with { question: string }
 * - Suggested question chips for quick access.
 * - Medical disclaimer shown below the input.
 */
import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import axios from 'axios'

// ── Types ────────────────────────────────────────────────────────────────────

interface UserMessage {
  role:    'user'
  text:    string
}

interface AssistantMessage {
  role:    'assistant'
  text:    string      // retrieved protocol excerpt
  source?: string      // document / section label from the server
}

type ChatMessage = UserMessage | AssistantMessage

interface AskResponse {
  answer: string
  source?: string
}

// ── Suggested questions ──────────────────────────────────────────────────────

const SUGGESTED_QUESTIONS = [
  'What is the protocol for severe anaemia?',
  'When should I refer for high blood pressure?',
  'What are the danger signs in the third trimester?',
  'How many ANC visits are required under the GoI protocol?',
  'What is the recommended dose of iron and folic acid?',
]

// ── Component ─────────────────────────────────────────────────────────────────

export default function Assistant() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      text: 'Hello! I can answer questions about Government of India antenatal care protocols. Try one of the suggested questions below or type your own.',
      source: 'MAITRI Assistant',
    }
  ])
  const [input,   setInput]   = useState('')
  const [loading, setLoading] = useState(false)

  /** Scroll anchor — keeps the latest message in view. */
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Send message ──────────────────────────────────────────────────────────

  const sendMessage = async (question: string) => {
    const trimmed = question.trim()
    if (!trimmed || loading) return

    // Append user message immediately
    setMessages(prev => [...prev, { role: 'user', text: trimmed }])
    setInput('')
    setLoading(true)

    try {
      const res = await axios.post<AskResponse>('/api/assistant/ask', {
        question: trimmed
      })
      setMessages(prev => [
        ...prev,
        {
          role:   'assistant',
          text:   res.data.answer,
          source: res.data.source,
        }
      ])
    } catch (err) {
      console.error('[MAITRI] Assistant API error:', err)
      setMessages(prev => [
        ...prev,
        {
          role:   'assistant',
          text:   'Sorry, I could not retrieve an answer right now. Please check your connection and try again.',
          source: 'Error',
        }
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-[calc(100vh-12rem)] max-w-2xl mx-auto">

      {/* ── Title ── */}
      <div className="mb-3">
        <h2 className="text-xl font-bold text-gray-900">Protocol Assistant</h2>
        <p className="text-xs text-gray-500">
          Answers retrieved from GoI antenatal care protocol documents
        </p>
      </div>

      {/* ── Chat messages ── */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1 pb-2">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'user' ? (
              /* User bubble */
              <div className="bg-maitri-600 text-white px-4 py-3 rounded-2xl rounded-tr-sm max-w-[80%] text-sm shadow-sm">
                {msg.text}
              </div>
            ) : (
              /* Assistant bubble */
              <div className="bg-white border border-gray-100 shadow-sm rounded-2xl rounded-tl-sm max-w-[85%] overflow-hidden">
                <p className="px-4 py-3 text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
                  {msg.text}
                </p>
                {msg.source && (
                  <p className="px-4 pb-2 text-xs text-purple-500 font-medium border-t border-gray-50 pt-1.5">
                    📄 {msg.source}
                  </p>
                )}
              </div>
            )}
          </div>
        ))}

        {/* Typing indicator while loading */}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-100 shadow-sm rounded-2xl rounded-tl-sm px-4 py-3">
              <span className="flex gap-1 items-center text-gray-400 text-sm">
                <span className="animate-bounce delay-0">●</span>
                <span className="animate-bounce delay-100">●</span>
                <span className="animate-bounce delay-200">●</span>
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* ── Suggested questions ── */}
      <div className="flex gap-2 overflow-x-auto py-2 my-1 no-scrollbar">
        {SUGGESTED_QUESTIONS.map(q => (
          <button
            key={q}
            onClick={() => sendMessage(q)}
            disabled={loading}
            className="shrink-0 text-xs bg-maitri-50 text-maitri-700 border border-maitri-200 rounded-full px-3 py-1.5 hover:bg-maitri-100 transition-colors disabled:opacity-50"
          >
            {q}
          </button>
        ))}
      </div>

      {/* ── Input bar ── */}
      <div className="flex gap-2 items-center mt-1">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about antenatal protocols…"
          disabled={loading}
          className="input-field flex-1"
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={loading || !input.trim()}
          className="btn-primary px-5 py-3 flex-shrink-0"
        >
          Send
        </button>
      </div>

      {/* ── Disclaimer ── */}
      <p className="text-xs text-gray-400 text-center mt-2 px-2">
        ⚠ Answers are retrieved verbatim from Government of India antenatal care protocol
        excerpts. <strong>This is not medical advice.</strong>
      </p>

    </div>
  )
}
