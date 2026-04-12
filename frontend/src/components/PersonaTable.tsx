/**
 * Persona table with inline editing, HITL checkbox selection, and custom persona add.
 */
import { useState } from 'react'
import type { Persona } from '../api/client'
import { InfoTooltip } from './InfoTooltip'

const CATEGORY_RATIONALE: Record<string, string> = {
  ml_ai: 'ML/AI investment signals detected — targeting the buying group most likely to own AI infrastructure decisions.',
  infra_scaling: 'Infrastructure scaling signals detected — targeting platform and reliability owners.',
  cost_optimization: 'Cloud cost signals detected — targeting FinOps and infrastructure budget owners.',
  security_compliance: 'Security/compliance signals detected — blocker alignment required before any evaluation can proceed.',
  hiring_engineering: 'Engineering hiring signals detected — targeting the technical leadership driving the headcount push.',
  default: 'General technology signals detected — balanced buying group selected.',
}

interface Props {
  personas: Persona[]
  signalCategory?: string
  isHitlMode: boolean
  sessionId: string
  companyId: string
  onConfirmSelection: (selectedIds: string[], customPersonas: Persona[]) => Promise<void>
  onEditPersona: (personaId: string, updates: Partial<Pick<Persona, 'title' | 'targeting_reason'>>) => Promise<void>
  onRemovePersona?: (personaId: string) => void
}

const ROLE_TYPE_LABELS: Record<string, string> = {
  economic_buyer: 'Economic',
  technical_buyer: 'Technical',
  influencer: 'Influencer',
  blocker: 'Blocker',
}

export function PersonaTable({
  personas,
  signalCategory,
  isHitlMode,
  onConfirmSelection,
  onEditPersona,
  onRemovePersona,
}: Props) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    new Set(personas.map(p => p.persona_id))
  )
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editReason, setEditReason] = useState('')
  const [customPersonas, setCustomPersonas] = useState<Persona[]>([])
  const [addingCustom, setAddingCustom] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newReason, setNewReason] = useState('')
  const [confirming, setConfirming] = useState(false)

  const allPersonas = [...personas, ...customPersonas]

  function removeCustomPersona(id: string) {
    setCustomPersonas(prev => prev.filter(p => p.persona_id !== id))
    setSelectedIds(prev => { const s = new Set(prev); s.delete(id); return s })
  }

  function toggleSelect(id: string) {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function startEdit(persona: Persona) {
    setEditingId(persona.persona_id)
    setEditTitle(persona.title)
    setEditReason(persona.targeting_reason)
  }

  async function saveEdit(personaId: string) {
    await onEditPersona(personaId, { title: editTitle, targeting_reason: editReason })
    setEditingId(null)
  }

  function addCustomPersona() {
    if (!newTitle.trim()) return
    const persona: Persona = {
      persona_id: `custom-${Date.now()}`,
      title: newTitle.trim(),
      targeting_reason: newReason.trim(),
      role_type: 'influencer',
      seniority_level: 'manager',
      priority_score: 0.5,
      is_custom: true,
      is_edited: false,
    }
    setCustomPersonas(prev => [...prev, persona])
    setSelectedIds(prev => new Set([...prev, persona.persona_id]))
    setNewTitle('')
    setNewReason('')
    setAddingCustom(false)
  }

  async function handleConfirm() {
    setConfirming(true)
    try {
      await onConfirmSelection(Array.from(selectedIds), customPersonas)
    } finally {
      setConfirming(false)
    }
  }

  if (allPersonas.length === 0) {
    return (
      <div className="text-sm text-gray-400 py-4 text-center">
        No personas generated yet.
      </div>
    )
  }

  const rationale = signalCategory ? CATEGORY_RATIONALE[signalCategory] : null

  return (
    <div className="space-y-2">
      {rationale && (
        <div className="rounded-md bg-gray-50 border border-gray-200 px-3 py-2 text-xs text-gray-600">
          <span className="font-medium text-gray-700">Why these personas: </span>{rationale}
        </div>
      )}
      {isHitlMode && (
        <div className="rounded-md bg-yellow-50 border border-yellow-300 px-3 py-2 text-sm text-yellow-800">
          Select personas for outreach and click <strong>Confirm</strong>.
        </div>
      )}

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200">
            {isHitlMode && <th className="py-2 w-8" />}
            <th className="py-2 text-left text-xs font-medium text-gray-500 uppercase">Persona</th>
            <th className="py-2 text-left text-xs font-medium text-gray-500 uppercase">
              <span className="inline-flex items-center">
                Role
                <InfoTooltip text="Buyer role in the decision process: Economic (budget), Technical (evaluation), Influencer, or Blocker." />
              </span>
            </th>
            <th className="py-2 text-right text-xs font-medium text-gray-500 uppercase">
              <span className="inline-flex items-center">
                Score
                <InfoTooltip text="Priority score (0–100%). Higher means this persona is more likely to engage." />
              </span>
            </th>
            <th className="py-2 w-16" />
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {allPersonas.map(persona => (
            <tr key={persona.persona_id} data-testid={`persona-row-${persona.persona_id}`}>
              {isHitlMode && (
                <td className="py-2 pr-2">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(persona.persona_id)}
                    onChange={() => toggleSelect(persona.persona_id)}
                    aria-label={`Select ${persona.title}`}
                    className="rounded"
                  />
                </td>
              )}
              <td className="py-2 pr-4">
                {editingId === persona.persona_id ? (
                  <div className="space-y-1">
                    <input
                      value={editTitle}
                      onChange={e => setEditTitle(e.target.value)}
                      className="w-full rounded border border-gray-300 px-2 py-0.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                      aria-label="Edit persona title"
                    />
                    <textarea
                      value={editReason}
                      onChange={e => setEditReason(e.target.value)}
                      rows={2}
                      className="w-full rounded border border-gray-300 px-2 py-0.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                      aria-label="Edit targeting reason"
                    />
                  </div>
                ) : (
                  <div>
                    <div className="font-medium text-gray-900">
                      {persona.title}
                      {persona.is_custom && (
                        <span className="ml-1 text-xs text-gray-400">(custom)</span>
                      )}
                      {persona.is_edited && (
                        <span className="ml-1 text-xs text-gray-400">(edited)</span>
                      )}
                    </div>
                    {persona.targeting_reason && (
                      <button
                        onClick={() => setExpandedId(expandedId === persona.persona_id ? null : persona.persona_id)}
                        className="text-left w-full"
                      >
                        <div className={`text-xs text-gray-500 mt-0.5 ${expandedId === persona.persona_id ? '' : 'line-clamp-2'}`}>
                          {persona.targeting_reason}
                        </div>
                        {persona.targeting_reason.length > 80 && (
                          <span className="text-xs text-blue-500 hover:underline">
                            {expandedId === persona.persona_id ? 'less' : 'more'}
                          </span>
                        )}
                      </button>
                    )}
                  </div>
                )}
              </td>
              <td className="py-2 pr-4">
                <span className="text-xs text-gray-600">
                  {ROLE_TYPE_LABELS[persona.role_type] ?? persona.role_type}
                </span>
              </td>
              <td className="py-2 text-right text-xs text-gray-600">
                {Math.round(persona.priority_score * 100)}%
              </td>
              <td className="py-2 text-right">
                <div className="flex justify-end gap-2">
                  {editingId === persona.persona_id ? (
                    <button
                      onClick={() => saveEdit(persona.persona_id)}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      Save
                    </button>
                  ) : (
                    <button
                      onClick={() => startEdit(persona)}
                      className="text-xs text-gray-400 hover:text-gray-600"
                      aria-label={`Edit ${persona.title}`}
                    >
                      Edit
                    </button>
                  )}
                  {persona.is_custom ? (
                    <button
                      onClick={() => removeCustomPersona(persona.persona_id)}
                      className="text-xs text-red-400 hover:text-red-600"
                      aria-label={`Remove ${persona.title}`}
                    >
                      ✕
                    </button>
                  ) : onRemovePersona ? (
                    <button
                      onClick={() => onRemovePersona(persona.persona_id)}
                      className="text-xs text-red-400 hover:text-red-600"
                      aria-label={`Remove ${persona.title}`}
                    >
                      ✕
                    </button>
                  ) : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {isHitlMode && (
        <div className="space-y-2">
          {addingCustom ? (
            <div className="rounded-md border border-gray-200 p-3 space-y-2">
              <input
                value={newTitle}
                onChange={e => setNewTitle(e.target.value)}
                placeholder="Persona title"
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                aria-label="New persona title"
              />
              <input
                value={newReason}
                onChange={e => setNewReason(e.target.value)}
                placeholder="Targeting reason (optional)"
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                aria-label="New persona targeting reason"
              />
              <div className="flex gap-2">
                <button
                  onClick={addCustomPersona}
                  className="px-3 py-1 text-sm bg-gray-800 text-white rounded hover:bg-gray-700"
                >
                  Add
                </button>
                <button
                  onClick={() => setAddingCustom(false)}
                  className="px-3 py-1 text-sm text-gray-600 hover:text-gray-800"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setAddingCustom(true)}
              className="text-sm text-blue-600 hover:underline"
            >
              + Add custom persona
            </button>
          )}

          <button
            onClick={handleConfirm}
            disabled={confirming || selectedIds.size === 0}
            className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {confirming ? 'Confirming…' : `Confirm ${selectedIds.size} persona${selectedIds.size !== 1 ? 's' : ''}`}
          </button>
        </div>
      )}
    </div>
  )
}
