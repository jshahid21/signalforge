/**
 * Draft panel — editable subject/body, version indicator, Copy/Regenerate/Approve buttons.
 * Inline editing is local state only (no API calls until explicit actions).
 */
import { useEffect, useState } from 'react'
import type { Draft, Persona } from '../api/client'
import { HumanReviewBadge } from './HumanReviewBadge'

interface Props {
  draft: Draft | null
  persona: Persona | null
  humanReviewRequired?: boolean
  onApprove: () => Promise<void>
  onRegenerate: () => Promise<void>
  onOverride?: () => void
}

export function DraftPanel({ draft, persona, humanReviewRequired, onApprove, onRegenerate, onOverride }: Props) {
  const [subject, setSubject] = useState(draft?.subject_line ?? '')
  const [body, setBody] = useState(draft?.body ?? '')
  const [copied, setCopied] = useState(false)
  const [approving, setApproving] = useState(false)
  const [regenerating, setRegenerating] = useState(false)

  // Sync local state when draft changes
  useEffect(() => {
    setSubject(draft?.subject_line ?? '')
    setBody(draft?.body ?? '')
  }, [draft?.draft_id])

  async function copyToClipboard() {
    const text = `Subject: ${subject}\n\n${body}`
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function handleApprove() {
    setApproving(true)
    try { await onApprove() } finally { setApproving(false) }
  }

  async function handleRegenerate() {
    setRegenerating(true)
    try { await onRegenerate() } finally { setRegenerating(false) }
  }

  if (!draft && humanReviewRequired) {
    return (
      <div className="p-4">
        <HumanReviewBadge onOverride={onOverride} />
      </div>
    )
  }

  if (!draft) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="text-center">
          <div className="mx-auto mb-3 h-10 w-10 rounded-full bg-gray-100 flex items-center justify-center">
            <span className="text-lg text-gray-400">{persona ? '✉' : '👤'}</span>
          </div>
          <p className="text-sm font-medium text-gray-500">
            {persona ? 'Draft not yet generated' : 'No persona selected'}
          </p>
          <p className="text-xs text-gray-400 mt-1">
            {persona ? 'The draft will appear here once the pipeline completes.' : 'Select a persona above to view their draft.'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={`flex flex-col h-full p-4 space-y-3 ${draft.approved ? 'bg-green-50/40' : ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          {persona && <span className="font-medium text-gray-700">{persona.title}</span>}
          {draft.version > 1 && (
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
              v{draft.version}
            </span>
          )}
          {draft.approved && (
            <span className="rounded-full bg-green-600 px-2.5 py-0.5 text-xs font-medium text-white" data-testid="draft-approved-badge">
              ✓ Approved
            </span>
          )}
        </div>
        <div className="text-xs text-gray-400">
          {Math.round(draft.confidence_score)}% confidence
        </div>
      </div>

      {/* Email card */}
      <div className="flex-1 rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden flex flex-col" data-testid="draft-email-card">
        {/* Subject line */}
        <div className="border-b border-gray-100 px-4 py-2">
          <label className="text-[10px] font-medium text-gray-400 uppercase">Subject</label>
          <input
            value={subject}
            onChange={e => setSubject(e.target.value)}
            className="w-full text-sm font-medium text-gray-900 bg-transparent border-none p-0 mt-0.5 focus:outline-none focus:ring-0"
            aria-label="Draft subject line"
          />
        </div>

        {/* Body */}
        <div className="flex-1 px-4 py-3">
          <textarea
            value={body}
            onChange={e => setBody(e.target.value)}
            className="w-full h-full text-sm text-gray-700 bg-transparent border-none resize-none p-0 focus:outline-none focus:ring-0 leading-relaxed"
            aria-label="Draft body"
          />
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <button
          onClick={copyToClipboard}
          className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-colors"
          aria-label="Copy draft to clipboard"
        >
          {copied ? '✓ Copied!' : '📋 Copy'}
        </button>
        <button
          onClick={handleRegenerate}
          disabled={regenerating}
          className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-colors disabled:opacity-50"
          aria-label="Regenerate draft"
        >
          {regenerating ? '↻ Regenerating…' : '↻ Regenerate'}
        </button>
        <button
          onClick={handleApprove}
          disabled={approving || draft.approved}
          className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
            draft.approved
              ? 'bg-green-600 text-white cursor-default'
              : 'bg-green-600 text-white hover:bg-green-700 disabled:opacity-50'
          }`}
          aria-label="Approve draft"
        >
          {approving ? 'Approving…' : draft.approved ? '✓ Approved' : '✓ Approve'}
        </button>
      </div>
    </div>
  )
}
