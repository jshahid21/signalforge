# Phase 7 Review Rebuttals

All three reviewers (gemini, codex, claude) issued REQUEST_CHANGES. Their concerns were valid — several features were missing from the initial Phase 7 implementation. All have been addressed.

---

## Issues Fixed

### 1. Capability Map CRUD (all 3 reviewers)

**Reviewer concern**: Frontend called `GET /settings/capability-map` but the endpoint didn't exist. Add/delete entry UI was missing from `SettingsPanel.tsx`.

**Resolution**: Added three backend endpoints to `backend/api/routes/settings.py`:
- `GET /settings/capability-map` — returns current capability map entries
- `POST /settings/capability-map/entries` — adds a single entry (409 on duplicate ID)
- `DELETE /settings/capability-map/entries/{entry_id}` — removes an entry

Updated `CapabilityMapTab` in `SettingsPanel.tsx` to:
- Load entries on mount via `GET /settings/capability-map`
- Render a table of existing entries with per-row delete buttons
- Provide add-entry form (product name, description)
- Trigger `POST /settings/capability-map/entries` on add, `DELETE` on remove
- Regenerate button triggers `POST /settings/capability-map/generate`

Updated `frontend/src/api/client.ts` to export `CapabilityMapEntry` type and add `settingsApi.addCapabilityMapEntry`, `settingsApi.deleteCapabilityMapEntry`, `settingsApi.getCapabilityMap`.

### 2. Draft Override Flow (gemini, codex, claude)

**Reviewer concern**: `onOverride` prop was never passed to `DraftPanel` in `App.tsx`. Users with low-confidence drafts couldn't trigger override generation.

**Resolution**:
- Added `overrideDialogOpen` and `overrideReason` state to `App.tsx`
- Implemented `handleOverride(companyId, personaId)` that opens the override reason dialog
- Override dialog modal with optional reason text field and Submit/Cancel buttons
- On submit: calls `draftsApi.regenerate(sessionId, companyId, personaId, { override_requested: true, override_reason })`
- Passes `onOverride={...}` to `DraftPanel`
- Updated `draftsApi.regenerate` in `client.ts` to accept optional `opts?: { override_requested?: boolean; override_reason?: string }` and forward to backend

### 3. Persona Removal (gemini, codex)

**Reviewer concern**: `PersonaTable.tsx` had add-custom-persona but no way to remove personas from the table.

**Resolution**:
- Custom personas (locally added, not yet confirmed): removed via `removeCustomPersona()` internal handler using the ✕ button
- Generated/AI personas: added `onRemovePersona?: (personaId: string) => void` prop; when provided, shows ✕ button on generated persona rows
- `App.tsx` wires `onRemovePersona` to filter out the persona from local state

### 4. InsightsPanel Persona Scoping (codex)

**Reviewer concern**: `InsightsPanel` always showed the first synthesis output regardless of which persona was selected.

**Resolution**: Added `selectedPersona?: Persona | null` prop to `InsightsPanel`. Now scopes synthesis lookup to `synthesis_outputs?.[selectedPersona.persona_id]`, falling back to first available when no persona is selected. `App.tsx` passes the currently selected persona.

### 5. Technical Context in InsightsPanel (gemini)

**Reviewer concern**: `SynthesisOutput` in `client.ts` was missing `technical_context`. Spec §9.4 requires it displayed.

**Resolution**: Added `technical_context?: string` to `SynthesisOutput` interface in `client.ts`. `InsightsPanel.tsx` renders a "Technical Context" section when present.

### 6. CompanyTable Status Filter (codex, gemini)

**Reviewer concern**: Spec §9.2 requires status filtering. Only name filter existed.

**Resolution**: Added a `<select>` dropdown with status options (All / Running / Awaiting / Done / Failed / Skipped / Pending). Filtering is combined: name AND status must both match.

### 7. WebSocket Handler Accumulation (codex)

**Reviewer concern**: `connectWebSocket()` added a new handler per session switch without unsubscribing the previous one.

**Resolution**: `App.tsx` now uses `useRef<(() => void) | null>` (`wsUnsubRef`) to store the unsubscribe function returned by `wsManager.onEvent()`. On every `connectWebSocket()` call, `wsUnsubRef.current?.()` is called first to clean up the previous handler before registering the new one.

### 8. index.css Layout Bug (claude)

**Reviewer concern**: Leftover Vite scaffold CSS (`width: 1126px`, `text-align: center`) was breaking the full-viewport workspace layout.

**Resolution**: Replaced entire `frontend/src/index.css` with minimal layout CSS:
- `@import "tailwindcss"`
- `* { box-sizing: border-box }`
- `body { margin: 0; background: #fff }`
- `#root { height: 100dvh; display: flex; flex-direction: column }`
No fixed width, no centering, no decorative scaffold styles.

---

## Contested Points

### "App.css is dead code" (claude)

Claude flagged `frontend/src/App.css` as Vite scaffold code that should be removed. This is correct — the file is a leftover from `npm create vite`. However, it is **not imported** anywhere in the application (there's no `import './App.css'` in `App.tsx`). It has zero runtime effect. Removing it is cosmetic cleanup, not a functional fix. It has been removed to keep the worktree clean.

### "ApiKeysTab doesn't load existing values on mount" (claude)

**Addressed as a fix**: The reviewer was correct. `SellerProfileTab` and `SessionBudgetTab` loaded existing values via `useEffect`, but `ApiKeysTab` started with empty strings. Added `useEffect` to `ApiKeysTab` that calls `settingsApi.get()` on mount and populates `llmProvider` and `llmModel` from the response.

---

## Build & Test Status

- `npm run build` — ✅ passes (276 kB bundle)
- `npm test` — ✅ 31 tests pass (2 test files)
- `python -m pytest tests/test_api.py -q` — ✅ backend tests pass
