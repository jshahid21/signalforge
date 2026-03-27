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
      <div className="flex h-full items-center justify-center text-sm text-gray-400 p-8">
        {persona ? 'Draft not yet generated.' : 'Select a persona to view draft.'}
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="text-xs text-gray-500">
          {persona && <span className="font-medium">{persona.title}</span>}
          {draft.version > 1 && (
            <span className="ml-2 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
              v{draft.version}
            </span>
          )}
          {draft.approved && (
            <span className="ml-2 rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700">
              Approved
            </span>
          )}
        </div>
        <div className="text-xs text-gray-400">
          {Math.round(draft.confidence_score)}% confidence
        </div>
      </div>

      {/* Subject line */}
      <div>
        <label className="text-xs font-medium text-gray-500 uppercase">Subject</label>
        <input
          value={subject}
          onChange={e => setSubject(e.target.value)}
          className="mt-1 w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          aria-label="Draft subject line"
        />
      </div>

      {/* Body */}
      <div className="flex-1">
        <label className="text-xs font-medium text-gray-500 uppercase">Body</label>
        <textarea
          value={body}
          onChange={e => setBody(e.target.value)}
          className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm resize-none h-48 focus:outline-none focus:ring-2 focus:ring-blue-500"
          aria-label="Draft body"
        />
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <button
          onClick={copyToClipboard}
          className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
          aria-label="Copy draft to clipboard"
        >
          {copied ? 'Copied!' : 'Copy'}
        </button>
        <button
          onClick={handleRegenerate}
          disabled={regenerating}
          className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
          aria-label="Regenerate draft"
        >
          {regenerating ? 'Regenerating…' : 'Regenerate'}
        </button>
        <button
          onClick={handleApprove}
          disabled={approving || draft.approved}
          className="flex-1 rounded-md bg-green-600 px-3 py-1.5 text-sm text-white hover:bg-green-700 disabled:opacity-50"
          aria-label="Approve draft"
        >
          {approving ? 'Approving…' : draft.approved ? 'Approved' : 'Approve'}
        </button>
      </div>
    </div>
  )
}
