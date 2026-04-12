/**
 * Regression tests for InfoTooltip — ensures info icons render with accessible tooltips.
 * Added for GitHub Issue #13.
 */
import { render, screen } from '@testing-library/react'
import { InfoTooltip } from '../components/InfoTooltip'
import { CompanyTable } from '../components/CompanyTable'
import { PersonaTable } from '../components/PersonaTable'
import type { CompanyState, Persona } from '../api/client'

describe('InfoTooltip', () => {
  it('renders with accessible label', () => {
    render(<InfoTooltip text="Test tooltip text" />)
    expect(screen.getByRole('button', { name: 'Test tooltip text' })).toBeInTheDocument()
  })

  it('renders tooltip content', () => {
    render(<InfoTooltip text="Test tooltip text" />)
    expect(screen.getByRole('tooltip')).toHaveTextContent('Test tooltip text')
  })

  it('has data-testid for querying', () => {
    render(<InfoTooltip text="Test" />)
    expect(screen.getByTestId('info-tooltip')).toBeInTheDocument()
  })
})

describe('CompanyTable score tooltip', () => {
  it('renders info tooltip next to Score header', () => {
    const companies: CompanyState[] = [{
      company_id: 'c1',
      company_name: 'Acme',
      status: 'completed',
      current_stage: 'generating',
      generated_personas: [],
      selected_personas: [],
      synthesis_outputs: {},
      drafts: {},
      total_cost_usd: 0,
    }]
    render(<CompanyTable companies={companies} selectedCompanyId={null} onSelectCompany={() => {}} />)
    expect(screen.getByRole('button', { name: /signal confidence/i })).toBeInTheDocument()
  })
})

describe('PersonaTable tooltips', () => {
  const persona: Persona = {
    persona_id: 'p1',
    title: 'VP Eng',
    targeting_reason: 'Leads team',
    role_type: 'technical_buyer',
    seniority_level: 'vp',
    priority_score: 0.8,
    is_custom: false,
    is_edited: false,
  }

  it('renders info tooltip next to Role header', () => {
    render(
      <PersonaTable
        personas={[persona]}
        isHitlMode={false}
        sessionId="s1"
        companyId="c1"
        onConfirmSelection={vi.fn()}
        onEditPersona={vi.fn()}
      />
    )
    expect(screen.getByRole('button', { name: /buyer role/i })).toBeInTheDocument()
  })

  it('renders info tooltip next to Score header', () => {
    render(
      <PersonaTable
        personas={[persona]}
        isHitlMode={false}
        sessionId="s1"
        companyId="c1"
        onConfirmSelection={vi.fn()}
        onEditPersona={vi.fn()}
      />
    )
    expect(screen.getByRole('button', { name: /priority score/i })).toBeInTheDocument()
  })
})
