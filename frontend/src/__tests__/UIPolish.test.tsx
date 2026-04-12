/**
 * Regression tests for issue #23 — UI polish: navbar, draft panel, empty states, visual hierarchy.
 * Verifies structural/styling elements introduced by the polish pass.
 */
import { render, screen } from '@testing-library/react'
import { DraftPanel } from '../components/DraftPanel'
import { InsightsPanel } from '../components/InsightsPanel'
import { PersonaTable } from '../components/PersonaTable'
import { ProgressBar } from '../components/ProgressBar'
import type { CompanyState, Draft, Persona } from '../api/client'

const noop = async () => {}

// ── DraftPanel ────────────────────────────────────────────────────────────────

describe('DraftPanel polish', () => {
  const mockDraft: Draft = {
    draft_id: 'd1',
    persona_id: 'p1',
    subject_line: 'Test Subject',
    body: 'Test body content',
    version: 1,
    confidence_score: 85,
    approved: false,
  }

  const mockPersona: Persona = {
    persona_id: 'p1',
    title: 'VP Engineering',
    targeting_reason: 'Owns infra',
    role_type: 'technical_buyer',
    seniority_level: 'vp',
    priority_score: 0.8,
    is_custom: false,
    is_edited: false,
  }

  it('renders draft in an email card container', () => {
    render(
      <DraftPanel draft={mockDraft} persona={mockPersona} onApprove={noop} onRegenerate={noop} />
    )
    expect(screen.getByTestId('draft-email-card')).toBeInTheDocument()
  })

  it('shows prominent approved badge when draft is approved', () => {
    const approved = { ...mockDraft, approved: true }
    render(
      <DraftPanel draft={approved} persona={mockPersona} onApprove={noop} onRegenerate={noop} />
    )
    const badge = screen.getByTestId('draft-approved-badge')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveTextContent('Approved')
  })

  it('shows informative empty state when no draft and persona selected', () => {
    render(
      <DraftPanel draft={null} persona={mockPersona} onApprove={noop} onRegenerate={noop} />
    )
    expect(screen.getByText('Draft not yet generated')).toBeInTheDocument()
    expect(screen.getByText(/pipeline completes/i)).toBeInTheDocument()
  })

  it('shows informative empty state when no draft and no persona', () => {
    render(
      <DraftPanel draft={null} persona={null} onApprove={noop} onRegenerate={noop} />
    )
    expect(screen.getByText('No persona selected')).toBeInTheDocument()
  })
})

// ── InsightsPanel ─────────────────────────────────────────────────────────────

describe('InsightsPanel polish', () => {
  const emptyCompany: CompanyState = {
    company_id: 'test',
    company_name: 'Test Co',
    status: 'completed',
    current_stage: 'signals',
    generated_personas: [],
    selected_personas: [],
    synthesis_outputs: {},
    drafts: {},
    total_cost_usd: 0,
  }

  it('shows descriptive empty state for no signals', () => {
    render(<InsightsPanel company={emptyCompany} />)
    expect(screen.getByText('No signals found')).toBeInTheDocument()
    expect(screen.getByText(/No buying signals were detected/i)).toBeInTheDocument()
  })

  it('shows spinner for running analysis', () => {
    const running = { ...emptyCompany, status: 'running' as const }
    render(<InsightsPanel company={running} />)
    expect(screen.getByText('Analyzing signals…')).toBeInTheDocument()
    expect(screen.getByText(/Searching for buying signals/i)).toBeInTheDocument()
  })
})

// ── PersonaTable ──────────────────────────────────────────────────────────────

describe('PersonaTable polish', () => {
  it('shows descriptive empty state', () => {
    render(
      <PersonaTable
        personas={[]}
        isHitlMode={false}
        sessionId="s1"
        companyId="c1"
        onConfirmSelection={noop}
        onEditPersona={noop}
      />
    )
    expect(screen.getByText('No personas yet')).toBeInTheDocument()
    expect(screen.getByText(/signal analysis completes/i)).toBeInTheDocument()
  })
})

// ── ProgressBar ───────────────────────────────────────────────────────────────

describe('ProgressBar polish', () => {
  it('renders stage labels underneath bars', () => {
    render(<ProgressBar currentStage="qualifying" status="running" />)
    expect(screen.getByText('Signals')).toBeInTheDocument()
    expect(screen.getByText('Qualifying')).toBeInTheDocument()
    expect(screen.getByText('Researching')).toBeInTheDocument()
    expect(screen.getByText('Mapping')).toBeInTheDocument()
    expect(screen.getByText('Generating')).toBeInTheDocument()
  })
})
