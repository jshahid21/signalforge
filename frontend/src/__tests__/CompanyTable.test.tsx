/**
 * Unit tests for CompanyTable — status badges and row rendering.
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { CompanyTable, StatusBadge } from '../components/CompanyTable'
import type { CompanyState } from '../api/client'

// ── StatusBadge tests ──────────────────────────────────────────────────────

describe('StatusBadge', () => {
  it.each([
    ['pending', 'Pending'],
    ['running', 'Running'],
    ['awaiting_human', 'Awaiting'],
    ['completed', 'Done'],
    ['failed', 'Failed'],
    ['skipped', 'Skipped'],
  ])('renders correct label for status "%s"', (status, label) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('applies correct color class for completed status', () => {
    const { container } = render(<StatusBadge status="completed" />)
    expect(container.firstChild).toHaveClass('bg-green-100')
  })

  it('applies correct color class for failed status', () => {
    const { container } = render(<StatusBadge status="failed" />)
    expect(container.firstChild).toHaveClass('bg-red-100')
  })

  it('applies correct color class for awaiting_human status', () => {
    const { container } = render(<StatusBadge status="awaiting_human" />)
    expect(container.firstChild).toHaveClass('bg-yellow-100')
  })

  it('applies animate-pulse for running status', () => {
    const { container } = render(<StatusBadge status="running" />)
    expect(container.firstChild).toHaveClass('animate-pulse')
  })

  it('includes testid attribute', () => {
    render(<StatusBadge status="completed" />)
    expect(screen.getByTestId('status-badge-completed')).toBeInTheDocument()
  })
})

// ── CompanyTable tests ─────────────────────────────────────────────────────

const makeCompany = (overrides: Partial<CompanyState> = {}): CompanyState => ({
  company_id: 'stripe',
  company_name: 'Stripe',
  status: 'completed',
  current_stage: 'generating',
  generated_personas: [],
  selected_personas: [],
  synthesis_outputs: {},
  drafts: {},
  total_cost_usd: 0.01,
  ...overrides,
})

describe('CompanyTable', () => {
  it('renders company name', () => {
    const companies = [makeCompany({ company_name: 'Stripe', company_id: 'stripe' })]
    render(
      <CompanyTable companies={companies} selectedCompanyId={null} onSelectCompany={() => {}} />
    )
    expect(screen.getByText('Stripe')).toBeInTheDocument()
  })

  it('shows empty state when no companies', () => {
    render(
      <CompanyTable companies={[]} selectedCompanyId={null} onSelectCompany={() => {}} />
    )
    expect(screen.getByText(/No companies/i)).toBeInTheDocument()
  })

  it('calls onSelectCompany with correct id on row click', () => {
    const onSelect = vi.fn()
    const companies = [makeCompany({ company_id: 'stripe', company_name: 'Stripe' })]
    render(
      <CompanyTable companies={companies} selectedCompanyId={null} onSelectCompany={onSelect} />
    )
    fireEvent.click(screen.getByTestId('company-row-stripe'))
    expect(onSelect).toHaveBeenCalledWith('stripe')
  })

  it('highlights selected company row', () => {
    const companies = [makeCompany({ company_id: 'stripe', company_name: 'Stripe' })]
    render(
      <CompanyTable companies={companies} selectedCompanyId="stripe" onSelectCompany={() => {}} />
    )
    const row = screen.getByTestId('company-row-stripe')
    expect(row.className).toContain('bg-blue-50')
  })

  it('filters companies by name', () => {
    const companies = [
      makeCompany({ company_id: 'stripe', company_name: 'Stripe' }),
      makeCompany({ company_id: 'datadog', company_name: 'Datadog' }),
    ]
    render(
      <CompanyTable companies={companies} selectedCompanyId={null} onSelectCompany={() => {}} />
    )
    const filterInput = screen.getByPlaceholderText(/filter/i)
    fireEvent.change(filterInput, { target: { value: 'stripe' } })

    expect(screen.getByText('Stripe')).toBeInTheDocument()
    expect(screen.queryByText('Datadog')).not.toBeInTheDocument()
  })

  it('shows status badges for each company', () => {
    const companies = [
      makeCompany({ company_id: 'stripe', status: 'completed' }),
      makeCompany({ company_id: 'datadog', company_name: 'Datadog', status: 'running' }),
    ]
    render(
      <CompanyTable companies={companies} selectedCompanyId={null} onSelectCompany={() => {}} />
    )
    expect(screen.getByTestId('status-badge-completed')).toBeInTheDocument()
    expect(screen.getByTestId('status-badge-running')).toBeInTheDocument()
  })

  it('shows confidence score when qualified signal is present', () => {
    const companies = [makeCompany({
      qualified_signal: {
        summary: 'Test signal',
        signal_type: 'job_posting',
        composite_score: 0.75,
        tier_used: 'tier_1',
        qualified: true,
      },
    })]
    render(
      <CompanyTable companies={companies} selectedCompanyId={null} onSelectCompany={() => {}} />
    )
    expect(screen.getByText('75%')).toBeInTheDocument()
  })
})
