/**
 * Yellow warning badge shown when a draft requires human review.
 * Displays the review reason and an optional Override button.
 */
import type { HumanReviewReason } from '../api/client'

const REASON_LABELS: Record<HumanReviewReason, string> = {
  low_confidence: 'Confidence too low',
  signal_ambiguous: 'Signal ambiguous',
  persona_unresolved: 'Persona unresolved',
  draft_quality: 'Draft quality',
}

interface Props {
  reason?: HumanReviewReason
  onOverride?: () => void
}

export function HumanReviewBadge({ reason, onOverride }: Props) {
  const label = reason ? REASON_LABELS[reason] : 'Human review required'

  return (
    <div className="flex items-center gap-2 rounded-md border border-yellow-400 bg-yellow-50 px-3 py-2">
      <span className="text-yellow-600" aria-hidden="true">⚠</span>
      <span className="text-sm text-yellow-800">
        Draft not generated — {label}
      </span>
      {onOverride && (
        <button
          onClick={onOverride}
          className="ml-auto rounded px-2 py-0.5 text-xs font-medium text-yellow-700 hover:bg-yellow-100 border border-yellow-300"
        >
          Override
        </button>
      )}
    </div>
  )
}
