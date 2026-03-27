/**
 * Insights panel — signal summary, core pain point, solution areas, confidence badge.
 */
import type { CompanyState } from '../api/client'
import { HumanReviewBadge } from './HumanReviewBadge'

interface Props {
  company: CompanyState
}

export function InsightsPanel({ company }: Props) {
  const { qualified_signal: signal, synthesis_outputs } = company
  // Use the first synthesis output for insights (or aggregate if multiple)
  const synthesis = Object.values(synthesis_outputs ?? {})[0]

  if (!signal && !synthesis) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-gray-400 p-8">
        {company.status === 'running' ? 'Analyzing signals…' : 'No signals found.'}
      </div>
    )
  }

  const confidencePct = synthesis?.confidence_score ?? (signal ? Math.round(signal.composite_score * 100) : null)
  const confidenceColor =
    confidencePct == null ? 'gray'
    : confidencePct >= 75 ? 'green'
    : confidencePct >= 50 ? 'yellow'
    : 'red'

  const confidenceBadgeStyles: Record<string, string> = {
    green: 'bg-green-100 text-green-800',
    yellow: 'bg-yellow-100 text-yellow-800',
    red: 'bg-red-100 text-red-800',
    gray: 'bg-gray-100 text-gray-600',
  }

  return (
    <div className="space-y-4 p-4">
      {/* Signal Summary */}
      {signal && (
        <div>
          <h3 className="text-xs font-semibold uppercase text-gray-500 mb-1">Signal</h3>
          <p className="text-sm text-gray-800">{signal.summary}</p>
          <div className="mt-1 flex gap-2 items-center">
            <span className="text-xs text-gray-500">{signal.signal_type}</span>
            <span className="text-xs text-gray-400">·</span>
            <span className="text-xs text-gray-500">Tier: {signal.tier_used}</span>
          </div>
        </div>
      )}

      {/* Confidence badge */}
      {confidencePct != null && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Confidence</span>
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${confidenceBadgeStyles[confidenceColor]}`}>
            {confidencePct}%
          </span>
        </div>
      )}

      {/* Solution mapping */}
      {synthesis && (
        <>
          <div>
            <h3 className="text-xs font-semibold uppercase text-gray-500 mb-1">Core Problem</h3>
            <p className="text-sm text-gray-800">{synthesis.core_problem}</p>
          </div>
          <div>
            <h3 className="text-xs font-semibold uppercase text-gray-500 mb-2">Solution Areas</h3>
            <div className="flex flex-wrap gap-1.5">
              {synthesis.solution_areas.map(area => (
                <span
                  key={area}
                  className="rounded-full bg-blue-50 border border-blue-200 px-2.5 py-0.5 text-xs text-blue-700"
                >
                  {area}
                </span>
              ))}
            </div>
          </div>
          {synthesis.human_review_required && (
            <HumanReviewBadge reason={synthesis.human_review_reason} />
          )}
        </>
      )}
    </div>
  )
}
