/**
 * SignalForge workspace — main layout and session orchestration.
 *
 * Layout: company table (left 1/3) + insights/persona/draft panels (right 2/3) + chat (bottom)
 * Session rehydration: on mount, fetch most recent active/awaiting session and restore state.
 */
import { useEffect, useRef, useState } from 'react'
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

  // ── Fallback polling when WebSocket is disconnected ─────────────────
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    // Poll session status every 5s when WS is disconnected and session is active
    function startPolling() {
      if (pollRef.current) return
      pollRef.current = setInterval(async () => {
        if (!currentSession) return
        const isTerminal = ['completed', 'failed', 'partial'].includes(currentSession.status)
        if (wsManager.connected || isTerminal) {
          // WS reconnected or session finished — stop polling
          if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
          return
        }
        try {
          const full = await sessionsApi.get(currentSession.session_id)
          setCurrentSession(full)
          sessionsApi.list().then(setSessions).catch(() => {})
        } catch {
          // Backend unreachable — keep polling
        }
      }, 5_000)
    }

    // Check connection state periodically to decide whether to poll
    const checkInterval = setInterval(() => {
      if (!currentSession) return
      const isTerminal = ['completed', 'failed', 'partial'].includes(currentSession.status)
      if (!wsManager.connected && !isTerminal) {
        startPolling()
      }
    }, 2_000)

    return () => {
      clearInterval(checkInterval)
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    }
  }, [currentSession?.session_id, currentSession?.status])

  // ── WebSocket ──────────────────────────────────────────────────────────
  // Track unsubscribe callback to avoid handler accumulation across session switches
  const wsUnsubRef = useRef<(() => void) | null>(null)

  function connectWebSocket(sessionId: string) {
    // Unsubscribe previous handler before connecting to new session
    wsUnsubRef.current?.()
    wsManager.connect(sessionId)

    const unsub = wsManager.onEvent(event => {
      if (event.type === 'stage_update') {
        if (event.company_state) {
          // Full company state included — merge directly, no round-trip needed
          updateCompanyState(event.company_id, event.company_state)
        } else {
          updateCompanyState(event.company_id, {
            current_stage: event.stage,
            status: event.status as CompanyState['status'],
          })
        }
      } else if (event.type === 'budget_warning') {
        setToast(`Budget warning: ${event.pct_used}% of session budget used`)
        setTimeout(() => setToast(null), 6000)
      } else if (event.type === 'pipeline_complete' || event.type === 'hitl_required') {
        sessionsApi.get(sessionId).then(full => {
          setCurrentSession(full)
          // Refresh sessions list so sidebar status updates
          sessionsApi.list().then(setSessions).catch(() => {})
        }).catch(() => {})
      } else if (event.type === 'error') {
        setToast(`Error: ${event.message}`)
        setTimeout(() => setToast(null), 8000)
      }
    })
    wsUnsubRef.current = unsub
  }

  async function startSession(companyNames: string[]) {
    const session = await sessionsApi.create(companyNames)
    const sessionList = await sessionsApi.list()
    setSessions(sessionList)
    // Fetch full session to get company_states with company_name populated
    const full = await sessionsApi.get(session.session_id)
    setCurrentSession(full)
    connectWebSocket(session.session_id)
  }

  async function selectSession(sessionId: string) {
    // Show immediately from cached list entry while full state loads
    const cached = sessions.find(s => s.session_id === sessionId)
    if (cached) setCurrentSession(cached)
    connectWebSocket(sessionId)
    // Load full state (signals, personas, drafts) in background
    try {
      const full = await sessionsApi.get(sessionId)
      setCurrentSession(full)
    } catch {
      // cached stub is already shown
    }
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

  // ── HITL ───────────────────────────────────────────────────────────────
  const isHitlMode = !!(currentSession?.awaiting_persona_selection)
  const companiesAwaitingConfirmation = isHitlMode
    ? companies.filter(c => c.current_stage === 'awaiting_persona_selection')
    : []
  const companiesConfirmed = isHitlMode
    ? companies.filter(c => c.current_stage !== 'awaiting_persona_selection' && c.generated_personas.length > 0)
    : []

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

  async function handleRegenerateDraft(opts?: { override_requested?: boolean; override_reason?: string }) {
    if (!currentSession || !selectedCompanyId || !selectedPersona) return
    await draftsApi.regenerate(currentSession.session_id, selectedCompanyId, selectedPersona.persona_id, opts)
    const updated = await sessionsApi.get(currentSession.session_id)
    setCurrentSession(updated)
  }

  const [overrideDialogOpen, setOverrideDialogOpen] = useState(false)
  const [overrideReason, setOverrideReason] = useState('')

  async function handleOverride() {
    setOverrideDialogOpen(false)
    await handleRegenerateDraft({ override_requested: true, override_reason: overrideReason || undefined })
    setOverrideReason('')
  }

  // ── All-companies-skipped state ────────────────────────────────────────
  const allSkipped = companies.length > 0 && companies.every(c => c.status === 'skipped')

  // ── Render ─────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          <span className="text-sm font-medium text-gray-500">Loading SignalForge…</span>
        </div>
      </div>
    )
  }

  if (firstRun) {
    return <SetupWizard onComplete={() => setFirstRun(false)} />
  }

  return (
    <div className="flex flex-col h-screen bg-white">
      {/* Navbar */}
      <header className="flex items-center justify-between px-5 py-2.5 bg-white shadow-sm border-b border-gray-100">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded-md bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center">
              <span className="text-white text-xs font-bold">S</span>
            </div>
            <h1 className="text-lg font-extrabold tracking-tight text-gray-900">SignalForge</h1>
          </div>
          {currentSession && (
            <StatusBadge status={currentSession.status} />
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setCurrentSession(null); setSelectedCompany(null) }}
            className="rounded-lg border border-gray-200 px-3.5 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-colors"
          >
            + New Session
          </button>
          <button
            onClick={() => setShowSettings(true)}
            className="rounded-lg border border-gray-200 px-3.5 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-colors"
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
              {isHitlMode && companiesAwaitingConfirmation.length > 0 && (
                <div className="px-3 py-2 bg-yellow-50 border-b border-yellow-200 text-sm text-yellow-800">
                  <p className="font-medium">
                    {companiesConfirmed.length}/{companiesConfirmed.length + companiesAwaitingConfirmation.length} companies confirmed
                  </p>
                  <p className="text-xs text-yellow-700 mt-0.5">
                    Awaiting: {companiesAwaitingConfirmation.map(c => c.company_name).join(', ')}
                  </p>
                </div>
              )}
              <CompanyTable
                companies={companies}
                selectedCompanyId={selectedCompanyId}
                onSelectCompany={setSelectedCompany}
              />
              {allSkipped && (
                <div className="p-4 bg-yellow-50 border-t border-yellow-200 text-sm text-yellow-800 space-y-1">
                  <p className="font-medium">No actionable signals for any company (all skipped).</p>
                  <p className="text-yellow-900/90">
                    Common fixes: ensure <strong>JSearch</strong> and <strong>Tavily</strong> keys are set and returning results;
                    build a <strong>capability map</strong> whose <em>problem_signals</em> keywords appear in job text;
                    set <strong>LLM provider/model</strong> so qualification can score signals (OpenAI and Anthropic are supported).
                  </p>
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
                      <div className="px-4 pt-3 pb-1 flex items-center gap-2">
                        <span className="text-xs font-bold uppercase tracking-wider text-gray-400">Insights</span>
                        <span className="text-xs text-gray-300">—</span>
                        <span className="text-xs font-medium text-gray-600">{selectedCompany.company_name}</span>
                      </div>
                      <InsightsPanel company={selectedCompany} selectedPersona={selectedPersona} />
                    </div>

                    {/* Personas */}
                    <div className="w-1/2 overflow-y-auto">
                      <div className="px-4 pt-3 pb-1">
                        <span className="text-xs font-bold uppercase tracking-wider text-gray-400">Personas</span>
                      </div>
                      <div className="px-4 pb-4">
                        <PersonaTable
                          personas={personas}
                          signalCategory={selectedCompany?.persona_signal_category}
                          isHitlMode={isHitlMode}
                          sessionId={currentSession.session_id}
                          companyId={selectedCompanyId ?? ''}
                          onConfirmSelection={handleConfirmPersonas}
                          onEditPersona={handleEditPersona}
                          onRemovePersona={id => {
                            // Remove persona from local view (non-HITL removal)
                            if (selectedCompanyId && currentSession?.company_states) {
                              const cs = currentSession.company_states[selectedCompanyId]
                              if (cs) {
                                setCurrentSession({
                                  ...currentSession,
                                  company_states: {
                                    ...currentSession.company_states,
                                    [selectedCompanyId]: {
                                      ...cs,
                                      generated_personas: cs.generated_personas.filter(p => p.persona_id !== id),
                                    },
                                  },
                                })
                              }
                            }
                          }}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Bottom: draft panel */}
                  <div className="h-80 flex flex-col overflow-hidden">
                    <div className="flex items-center gap-2 px-4 pt-3 pb-1 border-b border-gray-100">
                      <span className="text-xs font-bold uppercase tracking-wider text-gray-400">Draft</span>
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
                        humanReviewRequired={selectedCompany?.human_review_required}
                        onApprove={handleApproveDraft}
                        onRegenerate={handleRegenerateDraft}
                        onOverride={() => setOverrideDialogOpen(true)}
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
                <div className="flex h-full items-center justify-center">
                  <div className="text-center">
                    <div className="mx-auto mb-3 h-12 w-12 rounded-full bg-gray-100 flex items-center justify-center">
                      <span className="text-xl text-gray-400">⟵</span>
                    </div>
                    <p className="text-sm font-medium text-gray-500">Select a company</p>
                    <p className="text-xs text-gray-400 mt-1">Choose a company from the list to view insights and drafts</p>
                  </div>
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

      {/* Override dialog */}
      {overrideDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm p-6 space-y-4">
            <h2 className="text-base font-semibold text-gray-900">Override & Generate Draft</h2>
            <p className="text-sm text-gray-600">
              This will generate a draft despite the low-confidence signal. You can optionally provide a reason.
            </p>
            <textarea
              value={overrideReason}
              onChange={e => setOverrideReason(e.target.value)}
              placeholder="Override reason (optional)"
              rows={3}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <div className="flex gap-2">
              <button onClick={() => setOverrideDialogOpen(false)}
                className="flex-1 rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">
                Cancel
              </button>
              <button onClick={() => void handleOverride()}
                className="flex-1 rounded-md bg-yellow-500 px-4 py-2 text-sm font-medium text-white hover:bg-yellow-600">
                Override & Generate
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
