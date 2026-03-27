/**
 * Company list with status badges, confidence scores, and row selection.
 * Left panel of the workspace.
 */
import { useState } from 'react'
import type { CompanyState, PipelineStatus } from '../api/client'
import { ProgressBar } from './ProgressBar'

// ── Status badge ───────────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-600',
  running: 'bg-blue-100 text-blue-700 animate-pulse',
  awaiting_human: 'bg-yellow-100 text-yellow-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  skipped: 'bg-gray-100 text-gray-500',
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pending',
  running: 'Running',
  awaiting_human: 'Awaiting',
  completed: 'Done',
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

  return (
    <tr
      className={[
        'cursor-pointer hover:bg-gray-50 transition-colors',
        isSelected ? 'bg-blue-50 border-l-2 border-blue-500' : '',
      ].join(' ')}
      onClick={onClick}
      data-testid={`company-row-${company.company_id}`}
    >
      <td className="px-4 py-3">
        <div className="font-medium text-gray-900">{company.company_name}</div>
        <div className="mt-1">
          <ProgressBar currentStage={company.current_stage} status={company.status} />
        </div>
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={company.status} />
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

export function CompanyTable({ companies, selectedCompanyId, onSelectCompany }: Props) {
  const [filter, setFilter] = useState('')

  const filtered = companies.filter(c =>
    c.company_name.toLowerCase().includes(filter.toLowerCase())
  )

  if (companies.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-gray-400 text-sm p-8">
        No companies in this session.
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-gray-200">
        <input
          type="text"
          placeholder="Filter companies…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          aria-label="Filter companies"
        />
      </div>
      <div className="overflow-y-auto flex-1">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Company</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Score</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.map(company => (
              <CompanyRow
                key={company.company_id}
                company={company}
                isSelected={selectedCompanyId === company.company_id}
                onClick={() => onSelectCompany(company.company_id)}
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
