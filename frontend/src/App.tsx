/**
 * SignalForge workspace — main layout and session orchestration.
 *
 * Layout: company table (left 1/3) + insights/persona/draft panels (right 2/3) + chat (bottom)
 * Session rehydration: on mount, fetch most recent active/awaiting session and restore state.
 */
import { useEffect, useState } from 'react'
import { draftsApi, personasApi, sessionsApi, setupApi, wsManager } from './api/client'
import type { CompanyState, Session } from './api/client'
import { ChatAssistant } from './components/ChatAssistant'
import { CompanyTable } from './components/CompanyTable'
import { DraftPanel } from './components/DraftPanel'
import { InsightsPanel } from './components/InsightsPanel'
import { PersonaTable } from './components/PersonaTable'
import { SettingsPanel } from './components/SettingsPanel'
import { SetupWizard } from './components/SetupWizard'
import { StatusBadge } from './components/CompanyTable'
import { useSessionStore } from './store/sessionStore'

function SessionHistorySidebar({
  sessions,
  currentSessionId,
  onSelect,
}: {
  sessions: Session[]
  currentSessionId: string | null
  onSelect: (id: string) => void
}) {
  return (
    <div className="w-48 border-r border-gray-200 flex flex-col bg-gray-50">
      <div className="px-3 py-3 text-xs font-semibold text-gray-500 uppercase border-b border-gray-200">
        Sessions
      </div>
      <div className="flex-1 overflow-y-auto">
        {sessions.map(s => (
          <button
            key={s.session_id}
            onClick={() => onSelect(s.session_id)}
            className={[
              'w-full text-left px-3 py-2 text-sm hover:bg-gray-100 border-b border-gray-100',
              currentSessionId === s.session_id ? 'bg-blue-50 text-blue-700' : 'text-gray-700',
            ].join(' ')}
          >
            <div className="truncate text-xs font-medium">
              {s.company_names.slice(0, 2).join(', ')}
              {s.company_names.length > 2 && ` +${s.company_names.length - 2}`}
            </div>
            <StatusBadge status={s.status} />
          </button>
        ))}
      </div>
    </div>
  )
}

function NewSessionForm({
  onStart,
}: {
  onStart: (companyNames: string[]) => Promise<void>
}) {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit() {
    const names = input.split('\n').map(s => s.trim()).filter(Boolean)
    if (names.length === 0) return
    setLoading(true)
    try { await onStart(names) } finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col items-center justify-center h-full p-12 max-w-lg mx-auto">
      <h2 className="text-xl font-semibold text-gray-900 mb-2">New Session</h2>
      <p className="text-sm text-gray-500 mb-6 text-center">
        Enter company names to analyze (one per line). SignalForge will research buying signals and generate persona-targeted outreach drafts.
      </p>
      <textarea
        value={input}
        onChange={e => setInput(e.target.value)}
        placeholder="Stripe&#10;Datadog&#10;HashiCorp"
        rows={6}
        className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none mb-4"
        aria-label="Company names"
      />
      <button
        onClick={() => void handleSubmit()}
        disabled={loading || !input.trim()}
        className="w-full rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? 'Starting…' : 'Start Analysis'}
      </button>
    </div>
  )
}

export default function App() {
  const {
    sessions, currentSession, selectedCompanyId, toastMessage,
    setSessions, setCurrentSession, setSelectedCompany, setToast,
    updateCompanyState,
  } = useSessionStore()

  const [loading, setLoading] = useState(true)
  const [firstRun, setFirstRun] = useState(false)
  const [showSettings, setShowSettings] = useState(false)

  // ── On mount: check first-run, load sessions ───────────────────────────
  useEffect(() => {
    async function init() {
      try {
        const { first_run } = await setupApi.status()
        if (first_run) { setFirstRun(true); setLoading(false); return }

        const sessionList = await sessionsApi.list()
        setSessions(sessionList)

        // Restore most recent active session
        const active = sessionList.find(
          s => s.status === 'running' || s.status === 'awaiting_human'
        )
        if (active) {
          const full = await sessionsApi.get(active.session_id)
          setCurrentSession(full)
          connectWebSocket(full.session_id)
        }
      } catch {
        // Backend not available — proceed to empty state
      } finally {
        setLoading(false)
      }
    }
    void init()
  }, [])

  // ── WebSocket ──────────────────────────────────────────────────────────
  function connectWebSocket(sessionId: string) {
    wsManager.connect(sessionId)
    wsManager.onEvent(event => {
      if (event.type === 'stage_update') {
        updateCompanyState(event.company_id, {
          current_stage: event.stage,
          status: event.status as CompanyState['status'],
        })
      } else if (event.type === 'budget_warning') {
        setToast(`Budget warning: ${event.pct_used}% of session budget used`)
        setTimeout(() => setToast(null), 6000)
      } else if (event.type === 'pipeline_complete' || event.type === 'hitl_required') {
        // Refresh full session state
        if (currentSession) {
          sessionsApi.get(currentSession.session_id).then(setCurrentSession).catch(() => {})
        }
      } else if (event.type === 'error') {
        setToast(`Error: ${event.message}`)
        setTimeout(() => setToast(null), 8000)
      }
    })
  }

  async function startSession(companyNames: string[]) {
    const session = await sessionsApi.create(companyNames)
    const sessionList = await sessionsApi.list()
    setSessions(sessionList)
    setCurrentSession(session)
    connectWebSocket(session.session_id)
  }

  async function selectSession(sessionId: string) {
    const full = await sessionsApi.get(sessionId)
    setCurrentSession(full)
    connectWebSocket(sessionId)
  }

  // ── Selected company ───────────────────────────────────────────────────
  const companyStates = currentSession?.company_states ?? {}
  const companies = Object.values(companyStates)
  const selectedCompany = selectedCompanyId ? companyStates[selectedCompanyId] : null

  // Auto-select first company if none selected
  useEffect(() => {
    if (!selectedCompanyId && companies.length > 0) {
      setSelectedCompany(companies[0]!.company_id)
    }
  }, [currentSession?.session_id, companies.length])

  // ── Selected persona & draft ───────────────────────────────────────────
  const [selectedPersonaId, setSelectedPersonaId] = useState<string | null>(null)

  const personas = selectedCompany?.generated_personas ?? []
  const selectedPersona = selectedPersonaId ? personas.find(p => p.persona_id === selectedPersonaId) ?? null : personas[0] ?? null

  const draft = selectedPersona && selectedCompany
    ? selectedCompany.drafts?.[selectedPersona.persona_id] ?? null
    : null

  const synthesis = selectedPersona && selectedCompany
    ? selectedCompany.synthesis_outputs?.[selectedPersona.persona_id] ?? null
    : null

  // ── HITL ───────────────────────────────────────────────────────────────
  const isHitlMode = !!(currentSession?.awaiting_persona_selection)

  async function handleConfirmPersonas(selectedIds: string[], customPersonas: typeof personas) {
    if (!currentSession || !selectedCompanyId) return
    await personasApi.confirm(currentSession.session_id, selectedCompanyId, selectedIds, customPersonas)
    const updated = await sessionsApi.get(currentSession.session_id)
    setCurrentSession(updated)
  }

  async function handleEditPersona(personaId: string, updates: { title?: string; targeting_reason?: string }) {
    if (!currentSession || !selectedCompanyId) return
    await personasApi.edit(currentSession.session_id, selectedCompanyId, personaId, updates)
    const updated = await sessionsApi.get(currentSession.session_id)
    setCurrentSession(updated)
  }

  async function handleApproveDraft() {
    if (!currentSession || !selectedCompanyId || !selectedPersona) return
    await draftsApi.approve(currentSession.session_id, selectedCompanyId, selectedPersona.persona_id)
    const updated = await sessionsApi.get(currentSession.session_id)
    setCurrentSession(updated)
  }

  async function handleRegenerateDraft() {
    if (!currentSession || !selectedCompanyId || !selectedPersona) return
    await draftsApi.regenerate(currentSession.session_id, selectedCompanyId, selectedPersona.persona_id)
    const updated = await sessionsApi.get(currentSession.session_id)
    setCurrentSession(updated)
  }

  // ── All-companies-skipped state ────────────────────────────────────────
  const allSkipped = companies.length > 0 && companies.every(c => c.status === 'skipped')

  // ── Render ─────────────────────────────────────────────────────────────

  if (loading) {
    return <div className="flex h-screen items-center justify-center text-gray-500">Loading…</div>
  }

  if (firstRun) {
    return <SetupWizard onComplete={() => setFirstRun(false)} />
  }

  return (
    <div className="flex flex-col h-screen bg-white">
      {/* Navbar */}
      <header className="flex items-center justify-between border-b border-gray-200 px-4 py-2 bg-white">
        <div className="flex items-center gap-3">
          <h1 className="text-base font-bold text-gray-900">SignalForge</h1>
          {currentSession && (
            <StatusBadge status={currentSession.status} />
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setCurrentSession(null); setSelectedCompany(null) }}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
          >
            New Session
          </button>
          <button
            onClick={() => setShowSettings(true)}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
            aria-label="Open settings"
          >
            ⚙ Settings
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Session history sidebar */}
        <SessionHistorySidebar
          sessions={sessions}
          currentSessionId={currentSession?.session_id ?? null}
          onSelect={id => void selectSession(id)}
        />

        {/* Main content */}
        {!currentSession ? (
          <div className="flex-1">
            <NewSessionForm onStart={startSession} />
          </div>
        ) : (
          <div className="flex flex-1 overflow-hidden">
            {/* Company table - left 1/3 */}
            <div className="w-1/3 border-r border-gray-200 overflow-hidden flex flex-col">
              <CompanyTable
                companies={companies}
                selectedCompanyId={selectedCompanyId}
                onSelectCompany={setSelectedCompany}
              />
              {allSkipped && (
                <div className="p-4 bg-yellow-50 border-t border-yellow-200 text-sm text-yellow-800">
                  No actionable signals found for any company. Try adding different companies or adjusting your capability map.
                </div>
              )}
            </div>

            {/* Right panels - 2/3 */}
            <div className="flex-1 flex flex-col overflow-hidden">
              {selectedCompany ? (
                <>
                  {/* Top half: insights + personas */}
                  <div className="flex flex-1 overflow-hidden border-b border-gray-200">
                    {/* Insights */}
                    <div className="w-1/2 border-r border-gray-200 overflow-y-auto">
                      <div className="px-4 pt-3 pb-1 text-xs font-semibold uppercase text-gray-500">
                        Insights — {selectedCompany.company_name}
                      </div>
                      <InsightsPanel company={selectedCompany} />
                    </div>

                    {/* Personas */}
                    <div className="w-1/2 overflow-y-auto">
                      <div className="px-4 pt-3 pb-1 text-xs font-semibold uppercase text-gray-500">
                        Personas
                      </div>
                      <div className="px-4 pb-4">
                        <PersonaTable
                          personas={personas}
                          isHitlMode={isHitlMode}
                          sessionId={currentSession.session_id}
                          companyId={selectedCompanyId ?? ''}
                          onConfirmSelection={handleConfirmPersonas}
                          onEditPersona={handleEditPersona}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Bottom: draft panel */}
                  <div className="h-80 flex flex-col overflow-hidden">
                    <div className="flex items-center gap-2 px-4 pt-3 pb-1 border-b border-gray-100">
                      <span className="text-xs font-semibold uppercase text-gray-500">Draft</span>
                      {personas.length > 0 && (
                        <div className="flex gap-1">
                          {personas.map(p => (
                            <button
                              key={p.persona_id}
                              onClick={() => setSelectedPersonaId(p.persona_id)}
                              className={[
                                'px-2 py-0.5 text-xs rounded-full',
                                (selectedPersona?.persona_id === p.persona_id)
                                  ? 'bg-blue-600 text-white'
                                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
                              ].join(' ')}
                            >
                              {p.title}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex-1 overflow-y-auto">
                      <DraftPanel
                        draft={draft}
                        persona={selectedPersona}
                        humanReviewRequired={synthesis?.human_review_required}
                        onApprove={handleApproveDraft}
                        onRegenerate={handleRegenerateDraft}
                      />
                    </div>
                  </div>

                  {/* Chat assistant */}
                  <ChatAssistant
                    sessionId={currentSession.session_id}
                    companyId={selectedCompany.company_id}
                    companyName={selectedCompany.company_name}
                  />
                </>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-gray-400">
                  Select a company to view insights and drafts.
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Toast notification */}
      {toastMessage && (
        <div className="fixed bottom-4 right-4 z-50 rounded-lg bg-gray-900 px-4 py-3 text-sm text-white shadow-lg max-w-sm">
          {toastMessage}
          <button onClick={() => setToast(null)} className="ml-3 text-gray-400 hover:text-white">✕</button>
        </div>
      )}

      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}
    </div>
  )
}
