/**
 * Company list with status badges, confidence scores, and row selection.
 * Left panel of the workspace.
 */
import { useState } from 'react'
import type { CompanyState, PipelineStatus } from '../api/client'
import { InfoTooltip } from './InfoTooltip'
import { ProgressBar } from './ProgressBar'

// ── Status badge ───────────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-600',
  running: 'bg-blue-100 text-blue-700 animate-pulse',
  awaiting_human: 'bg-yellow-100 text-yellow-700',
  completed: 'bg-green-100 text-green-700',
  // Mixed session outcome — some companies succeeded, some failed.
  partial: 'bg-amber-100 text-amber-700',
  failed: 'bg-red-100 text-red-700',
  skipped: 'bg-gray-100 text-gray-500',
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pending',
  running: 'Running',
  awaiting_human: 'Awaiting',
  completed: 'Done',
  partial: 'Partial',
  failed: 'Failed',
  skipped: 'Skipped',
}

interface StatusBadgeProps {
  status: PipelineStatus | string
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const style = STATUS_STYLES[status] ?? 'bg-gray-100 text-gray-600'
  const label = STATUS_LABELS[status] ?? status
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${style}`}
      data-testid={`status-badge-${status}`}
    >
      {label}
    </span>
  )
}

// ── Company row ────────────────────────────────────────────────────────────

interface RowProps {
  company: CompanyState
  isSelected: boolean
  onClick: () => void
}

function CompanyRow({ company, isSelected, onClick }: RowProps) {
  const confidence = company.qualified_signal?.composite_score
  const confidencePct = confidence != null ? Math.round(confidence * 100) : null
  const rowId = company.company_id || 'unknown'

  return (
    <tr
      className={[
        'cursor-pointer hover:bg-blue-50/50 transition-colors',
        isSelected ? 'bg-blue-50 border-l-3 border-l-blue-600' : 'border-l-3 border-l-transparent',
      ].join(' ')}
      onClick={onClick}
      data-testid={`company-row-${rowId}`}
    >
      <td className="px-4 py-3">
        <div className="font-medium text-gray-900">{company.company_name ?? '—'}</div>
        <div className="mt-1">
          <ProgressBar currentStage={company.current_stage} status={company.status ?? 'pending'} />
        </div>
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={company.status ?? 'pending'} />
      </td>
      <td className="px-4 py-3 text-right text-sm text-gray-600">
        {confidencePct != null ? (
          <span title="Signal confidence score">{confidencePct}%</span>
        ) : (
          <span className="text-gray-300">—</span>
        )}
      </td>
    </tr>
  )
}

// ── CompanyTable ───────────────────────────────────────────────────────────

interface Props {
  companies: CompanyState[]
  selectedCompanyId: string | null
  onSelectCompany: (id: string) => void
}

// NOTE: 'partial' is intentionally NOT in this list. It is a session-level
// terminal status only — per-company states are always completed or failed,
// so filtering the company table by 'partial' would always return empty.
// 'partial' stays in STATUS_STYLES / STATUS_LABELS because App.tsx reuses
// the badge for session-level status display.
const STATUS_FILTER_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'All' },
  { value: 'running', label: 'Running' },
  { value: 'awaiting_human', label: 'Awaiting' },
  { value: 'completed', label: 'Done' },
  { value: 'failed', label: 'Failed' },
  { value: 'skipped', label: 'Skipped' },
  { value: 'pending', label: 'Pending' },
]

export function CompanyTable({ companies, selectedCompanyId, onSelectCompany }: Props) {
  const [filter, setFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const filtered = companies.filter(c => {
    const name = (c.company_name ?? '').toLowerCase()
    const nameMatch = name.includes(filter.toLowerCase())
    const statusMatch = !statusFilter || c.status === statusFilter
    return nameMatch && statusMatch
  })

  if (companies.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="text-center">
          <div className="mx-auto mb-2 h-10 w-10 rounded-full bg-gray-100 flex items-center justify-center">
            <span className="text-lg text-gray-400">🏢</span>
          </div>
          <p className="text-sm font-medium text-gray-500">No companies yet</p>
          <p className="text-xs text-gray-400 mt-1">Start a new session to analyze companies</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-gray-200 space-y-2">
        <input
          type="text"
          placeholder="Filter companies…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          aria-label="Filter companies"
        />
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
          aria-label="Filter by status"
        >
          {STATUS_FILTER_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>
      <div className="overflow-y-auto flex-1">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Company</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">
                <span className="inline-flex items-center">
                  Score
                  <InfoTooltip text="Signal confidence score (0–100%). Higher means stronger buying signals detected." />
                </span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.map((company, index) => (
              <CompanyRow
                key={company.company_id ?? `company-${index}`}
                company={company}
                isSelected={selectedCompanyId === company.company_id}
                onClick={() => company.company_id && onSelectCompany(company.company_id)}
              />
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="p-4 text-center text-sm text-gray-400">No companies match filter.</div>
        )}
      </div>
    </div>
  )
}
