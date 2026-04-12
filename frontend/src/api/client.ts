/**
 * Axios API client and WebSocket connection manager for SignalForge backend.
 */
import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const WS_BASE = BASE_URL.replace(/^http/, 'ws')

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// ── Types ──────────────────────────────────────────────────────────────────

export type PipelineStatus =
  | 'pending'
  | 'running'
  | 'awaiting_human'
  | 'completed'
  // session-level terminal state — some companies succeeded, some failed
  | 'partial'
  | 'failed'
  | 'skipped'

export type HumanReviewReason =
  | 'low_confidence'
  | 'signal_ambiguous'
  | 'persona_unresolved'
  | 'draft_quality'

export interface Persona {
  persona_id: string
  title: string
  targeting_reason: string
  role_type: string
  seniority_level: string
  priority_score: number
  is_custom: boolean
  is_edited: boolean
}

export interface Draft {
  draft_id: string
  company_id: string
  persona_id: string
  subject_line: string
  body: string
  confidence_score: number
  approved: boolean
  version: number
}

export interface RawSignal {
  source: string
  signal_type: string
  content: string
  url?: string
  published_at?: string
  tier: string
}

export interface QualifiedSignal {
  summary: string
  signal_type: string
  composite_score: number
  tier_used: string
  qualified: boolean
  raw_signals?: RawSignal[]
}

export interface SolutionMappingOutput {
  core_problem: string
  solution_areas: string[]
  inferred_areas: string[]
  confidence_score: number   // 0–100
  reasoning: string
}

export interface SynthesisOutput {
  core_pain_point: string
  technical_context: string
  solution_alignment: string
  persona_targeting: string
  buyer_relevance: string
  value_hypothesis: string
  risk_if_ignored: string
}

export interface CapabilityMapEntry {
  id: string
  label: string
  problem_signals: string[]
  solution_areas: string[]
}

export interface CompanyState {
  company_id: string
  company_name: string
  status: PipelineStatus
  current_stage: string
  qualified_signal?: QualifiedSignal
  solution_mapping?: SolutionMappingOutput
  generated_personas: Persona[]
  selected_personas: string[]
  persona_signal_category?: string
  synthesis_outputs: Record<string, SynthesisOutput>
  drafts: Record<string, Draft>
  human_review_required?: boolean
  human_review_reasons?: HumanReviewReason[]
  total_cost_usd: number
  error_message?: string
}

export interface Session {
  session_id: string
  status: PipelineStatus | string
  company_names: string[]
  company_states?: Record<string, CompanyState>
  total_cost_usd?: number
  awaiting_persona_selection?: boolean
  created_at?: string
  completed_at?: string
  error_message?: string
}

// ── Session API ────────────────────────────────────────────────────────────

export const sessionsApi = {
  list: () => api.get<Session[]>('/sessions').then(r => r.data),
  get: (id: string) => api.get<Session>(`/sessions/${id}`).then(r => r.data),
  create: (companyNames: string[], sellerProfile?: Record<string, unknown>) =>
    api.post<Session>('/sessions', { company_names: companyNames, seller_profile: sellerProfile }).then(r => r.data),
  resume: (id: string) => api.post(`/sessions/${id}/resume`).then(r => r.data),
}

export const personasApi = {
  confirm: (sessionId: string, companyId: string, selectedIds: string[], customPersonas?: Persona[]) =>
    api.post(`/sessions/${sessionId}/companies/${companyId}/personas/confirm`, {
      selected_persona_ids: selectedIds,
      custom_personas: customPersonas ?? [],
    }).then(r => r.data),
  edit: (sessionId: string, companyId: string, personaId: string, updates: Partial<Pick<Persona, 'title' | 'targeting_reason'>>) =>
    api.put(`/sessions/${sessionId}/companies/${companyId}/personas/${personaId}`, updates).then(r => r.data),
}

export const draftsApi = {
  approve: (sessionId: string, companyId: string, personaId: string) =>
    api.post(`/sessions/${sessionId}/companies/${companyId}/drafts/${personaId}/approve`).then(r => r.data),
  regenerate: (sessionId: string, companyId: string, personaId: string, opts?: { override_requested?: boolean; override_reason?: string }) =>
    api.post(`/sessions/${sessionId}/companies/${companyId}/drafts/${personaId}/regenerate`, opts ?? {}).then(r => r.data),
}

export const settingsApi = {
  getSellerProfile: () => api.get('/settings/seller-profile').then(r => r.data),
  putSellerProfile: (data: Record<string, unknown>) => api.put('/settings/seller-profile', data).then(r => r.data),
  getApiKeys: () => api.get<Record<string, unknown>>('/settings/api-keys').then(r => r.data),
  putApiKeys: (data: Record<string, unknown>) => api.put('/settings/api-keys', data).then(r => r.data),
  getSessionBudget: () => api.get('/settings/session-budget').then(r => r.data),
  putSessionBudget: (data: Record<string, unknown>) => api.put('/settings/session-budget', data).then(r => r.data),
  getCapabilityMap: () => api.get<CapabilityMapEntry[]>('/settings/capability-map').then(r => r.data),
  addCapabilityMapEntry: (entry: CapabilityMapEntry) => api.post<CapabilityMapEntry>('/settings/capability-map/entries', entry).then(r => r.data),
  deleteCapabilityMapEntry: (id: string) => api.delete(`/settings/capability-map/entries/${id}`).then(r => r.data),
  generateCapabilityMap: (data: Record<string, unknown>) => api.post('/settings/capability-map/generate', data).then(r => r.data),
  extractSellerIntelligence: (data?: { website_url?: string }) => api.post('/settings/seller-intelligence/extract', data ?? {}).then(r => r.data),
}

export const memoryApi = {
  list: () => api.get('/memory').then(r => r.data),
  delete: (id: string) => api.delete(`/memory/${id}`).then(r => r.data),
  exportCsv: () => `${BASE_URL}/memory/export`,
}

export const setupApi = {
  status: () => api.get<{ first_run: boolean }>('/setup').then(r => r.data),
  getConfig: () => api.get('/config').then(r => r.data),
  saveConfig: (data: Record<string, unknown>) => api.post('/config', data).then(r => r.data),
}

// ── WebSocket ──────────────────────────────────────────────────────────────

export type WsEvent =
  | { type: 'pipeline_started'; session_id: string }
  | { type: 'pipeline_resumed'; session_id: string }
  | { type: 'stage_update'; company_id: string; stage: string; status: string; company_state?: CompanyState }
  | { type: 'hitl_required'; awaiting_persona_selection: Record<string, Persona[]> }
  | { type: 'budget_warning'; pct_used: number }
  | { type: 'pipeline_complete' }
  | { type: 'error'; message: string }

export class WsManager {
  private ws: WebSocket | null = null
  private sessionId: string | null = null
  private handlers: Array<(event: WsEvent) => void> = []
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectAttempt = 0
  private intentionalDisconnect = false
  private _connected = false

  private static MAX_RECONNECT_DELAY = 30_000
  private static BASE_DELAY = 1_000

  connect(sessionId: string) {
    this.disconnect()
    this.sessionId = sessionId
    this.intentionalDisconnect = false
    this.reconnectAttempt = 0
    this._openSocket()
  }

  private _openSocket() {
    if (!this.sessionId) return
    this.ws = new WebSocket(`${WS_BASE}/ws/${this.sessionId}`)

    this.ws.onopen = () => {
      this._connected = true
      this.reconnectAttempt = 0
    }

    this.ws.onmessage = (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data as string) as WsEvent
        this.handlers.forEach(h => h(data))
      } catch {
        // Ignore non-JSON messages
      }
    }

    this.ws.onclose = () => {
      this._connected = false
      if (!this.intentionalDisconnect) {
        this._scheduleReconnect()
      }
    }

    this.ws.onerror = () => {
      // onclose fires after onerror, so reconnection is handled there
    }
  }

  private _scheduleReconnect() {
    if (this.reconnectTimer) return
    const delay = Math.min(
      WsManager.BASE_DELAY * 2 ** this.reconnectAttempt,
      WsManager.MAX_RECONNECT_DELAY,
    )
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.reconnectAttempt++
      this._openSocket()
    }, delay)
  }

  disconnect() {
    this.intentionalDisconnect = true
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.ws?.close()
    this.ws = null
    this.sessionId = null
    this._connected = false
  }

  onEvent(handler: (event: WsEvent) => void) {
    this.handlers.push(handler)
    return () => {
      this.handlers = this.handlers.filter(h => h !== handler)
    }
  }

  get connected() {
    return this._connected
  }

  get connectedSessionId() {
    return this.sessionId
  }
}

export const wsManager = new WsManager()
