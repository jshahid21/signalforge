/**
 * Zustand store for session state, pipeline status, and UI selections.
 */
import { create } from 'zustand'
import type { CompanyState, Persona, Session } from '../api/client'

interface SessionStore {
  // Data
  sessions: Session[]
  currentSession: Session | null
  selectedCompanyId: string | null
  selectedPersonaId: string | null
  wsConnected: boolean
  toastMessage: string | null

  // Actions
  setSessions: (sessions: Session[]) => void
  setCurrentSession: (session: Session | null) => void
  updateCompanyState: (companyId: string, state: Partial<CompanyState>) => void
  setSelectedCompany: (companyId: string | null) => void
  setSelectedPersona: (personaId: string | null) => void
  setWsConnected: (connected: boolean) => void
  setToast: (message: string | null) => void
  updatePersonaInState: (companyId: string, persona: Persona) => void
  setAwaitingPersonaSelection: (awaiting: boolean) => void
}

export const useSessionStore = create<SessionStore>((set) => ({
  sessions: [],
  currentSession: null,
  selectedCompanyId: null,
  selectedPersonaId: null,
  wsConnected: false,
  toastMessage: null,

  setSessions: (sessions) => set({ sessions }),

  setCurrentSession: (session) => set({ currentSession: session }),

  updateCompanyState: (companyId, stateUpdate) =>
    set((s) => {
      if (!s.currentSession) return s
      const existing = s.currentSession.company_states ?? {}
      const prev = existing[companyId] ?? ({} as CompanyState)
      return {
        currentSession: {
          ...s.currentSession,
          company_states: {
            ...existing,
            [companyId]: { ...prev, ...stateUpdate },
          },
        },
      }
    }),

  setSelectedCompany: (companyId) =>
    set({ selectedCompanyId: companyId, selectedPersonaId: null }),

  setSelectedPersona: (personaId) => set({ selectedPersonaId: personaId }),

  setWsConnected: (connected) => set({ wsConnected: connected }),

  setToast: (message) => set({ toastMessage: message }),

  updatePersonaInState: (companyId, persona) =>
    set((s) => {
      if (!s.currentSession?.company_states) return s
      const cs = s.currentSession.company_states[companyId]
      if (!cs) return s
      const personas = cs.generated_personas.map(p =>
        p.persona_id === persona.persona_id ? persona : p
      )
      return {
        currentSession: {
          ...s.currentSession,
          company_states: {
            ...s.currentSession.company_states,
            [companyId]: { ...cs, generated_personas: personas },
          },
        },
      }
    }),

  setAwaitingPersonaSelection: (awaiting) =>
    set((s) => ({
      currentSession: s.currentSession
        ? { ...s.currentSession, awaiting_persona_selection: awaiting }
        : null,
    })),
}))
