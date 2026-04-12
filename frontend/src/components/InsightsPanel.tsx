/**
 * Insights panel — signals, solution mapping, synthesis output per persona.
 */
import type { CompanyState, Persona, RawSignal } from '../api/client'
import { HumanReviewBadge } from './HumanReviewBadge'
import { InfoTooltip } from './InfoTooltip'

interface Props {
  company: CompanyState
  selectedPersona?: Persona | null
}

export function InsightsPanel({ company, selectedPersona }: Props) {
  const { qualified_signal: signal, solution_mapping, synthesis_outputs, human_review_required, human_review_reasons } = company

  const synthesis = selectedPersona
    ? (synthesis_outputs?.[selectedPersona.persona_id] ?? Object.values(synthesis_outputs ?? {})[0])
    : Object.values(synthesis_outputs ?? {})[0]

  if (!signal && !solution_mapping && !synthesis) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="text-center">
          {company.status === 'running' ? (
            <>
              <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
              <p className="text-sm font-medium text-gray-500">Analyzing signals…</p>
              <p className="text-xs text-gray-400 mt-1">Searching for buying signals across data sources</p>
            </>
          ) : (
            <>
              <div className="mx-auto mb-3 h-10 w-10 rounded-full bg-gray-100 flex items-center justify-center">
                <span className="text-lg text-gray-400">📡</span>
              </div>
              <p className="text-sm font-medium text-gray-500">No signals found</p>
              <p className="text-xs text-gray-400 mt-1">No buying signals were detected for this company</p>
            </>
          )}
        </div>
      </div>
    )
  }

  // Confidence from solution_mapping (0–100 int) or fall back to composite score
  const confidencePct = solution_mapping?.confidence_score
    ?? (signal ? Math.round(signal.composite_score * 100) : null)

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

      {/* Signals */}
      {signal && (
        <div>
          <h3 className="text-xs font-semibold uppercase text-gray-500 mb-2">
            Signals{signal.raw_signals && signal.raw_signals.length > 1 ? ` (${signal.raw_signals.length})` : ''}
          </h3>
          {signal.raw_signals && signal.raw_signals.length > 0 ? (
            <div className="space-y-2">
              {signal.raw_signals.map((raw: RawSignal, i: number) => (
                <div key={i} className="rounded-lg border border-gray-200 bg-white shadow-sm p-3">
                  <p className="text-xs text-gray-800 line-clamp-3">{raw.content}</p>
                  <div className="mt-1.5 flex flex-wrap gap-x-2 gap-y-1 items-center">
                    <span className="text-xs text-gray-500">{raw.signal_type}</span>
                    <span className="text-xs text-gray-400">·</span>
                    <span className="text-xs text-gray-500 inline-flex items-center">
                      Tier: {raw.tier}
                      <InfoTooltip text="Signal tier (1–3). Tier 1 = strongest, most actionable signals." />
                    </span>
                    {raw.url && (
                      <>
                        <span className="text-xs text-gray-400">·</span>
                        <a
                          href={raw.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-blue-600 hover:underline truncate max-w-[200px]"
                          title={raw.url}
                        >
                          Source ↗
                        </a>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <>
              <p className="text-sm text-gray-800">{signal.summary}</p>
              <div className="mt-1 flex gap-2 items-center">
                <span className="text-xs text-gray-500">{signal.signal_type}</span>
                <span className="text-xs text-gray-400">·</span>
                <span className="text-xs text-gray-500 inline-flex items-center">
                  Tier: {signal.tier_used}
                  <InfoTooltip text="Signal tier (1–3). Tier 1 = strongest, most actionable signals." />
                </span>
              </div>
            </>
          )}
        </div>
      )}

      {/* Confidence */}
      {confidencePct != null && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 inline-flex items-center">
            Confidence
            <InfoTooltip text="Composite score combining signal strength, recency, and source reliability." />
          </span>
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${confidenceBadgeStyles[confidenceColor]}`}>
            {confidencePct}%
          </span>
        </div>
      )}

      {/* Solution mapping */}
      {solution_mapping && (
        <>
          <div>
            <h3 className="text-xs font-semibold uppercase text-gray-500 mb-1">Core Problem</h3>
            <p className="text-sm text-gray-800">{solution_mapping.core_problem}</p>
          </div>
          {solution_mapping.solution_areas.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase text-gray-500 mb-2">Solution Areas</h3>
              <div className="flex flex-wrap gap-1.5">
                {solution_mapping.solution_areas.map(area => (
                  <span
                    key={area}
                    className="rounded-full bg-blue-50 border border-blue-200 px-2.5 py-0.5 text-xs text-blue-700"
                  >
                    {area}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Synthesis — persona-scoped */}
      {synthesis && (
        <>
          {synthesis.core_pain_point && (
            <div>
              <h3 className="text-xs font-semibold uppercase text-gray-500 mb-1">Pain Point</h3>
              <p className="text-sm text-gray-800">{synthesis.core_pain_point}</p>
            </div>
          )}
          {synthesis.technical_context && (
            <div>
              <h3 className="text-xs font-semibold uppercase text-gray-500 mb-1">Technical Context</h3>
              <p className="text-sm text-gray-700">{synthesis.technical_context}</p>
            </div>
          )}
          {synthesis.buyer_relevance && (
            <div>
              <h3 className="text-xs font-semibold uppercase text-gray-500 mb-1">Buyer Relevance</h3>
              <p className="text-sm text-gray-700">{synthesis.buyer_relevance}</p>
            </div>
          )}
        </>
      )}

      {/* Human review */}
      {human_review_required && (
        <HumanReviewBadge reason={human_review_reasons?.[0]} />
      )}
    </div>
  )
}
