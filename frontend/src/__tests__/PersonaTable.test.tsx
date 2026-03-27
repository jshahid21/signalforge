/**
 * Unit tests for PersonaTable — inline editing and custom persona add.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { PersonaTable } from '../components/PersonaTable'
import type { Persona } from '../api/client'

const makePersona = (overrides: Partial<Persona> = {}): Persona => ({
  persona_id: 'p1',
  title: 'VP Engineering',
  targeting_reason: 'Leads platform team',
  role_type: 'technical_buyer',
  seniority_level: 'vp',
  priority_score: 0.85,
  is_custom: false,
  is_edited: false,
  ...overrides,
})

const defaultProps = {
  personas: [makePersona()],
  isHitlMode: false,
  sessionId: 'sess-1',
  companyId: 'stripe',
  onConfirmSelection: vi.fn(),
  onEditPersona: vi.fn(),
}

describe('PersonaTable', () => {
  it('renders persona title', () => {
    render(<PersonaTable {...defaultProps} />)
    expect(screen.getByText('VP Engineering')).toBeInTheDocument()
  })

  it('shows empty state when no personas', () => {
    render(<PersonaTable {...defaultProps} personas={[]} />)
    expect(screen.getByText(/No personas/i)).toBeInTheDocument()
  })

  it('renders persona priority score as percentage', () => {
    render(<PersonaTable {...defaultProps} />)
    expect(screen.getByText('85%')).toBeInTheDocument()
  })

  it('renders role type label', () => {
    render(<PersonaTable {...defaultProps} />)
    expect(screen.getByText('Technical')).toBeInTheDocument()
  })

  describe('inline editing', () => {
    it('shows title input when Edit is clicked', () => {
      render(<PersonaTable {...defaultProps} />)
      fireEvent.click(screen.getByRole('button', { name: /Edit VP Engineering/i }))
      expect(screen.getByRole('textbox', { name: /Edit persona title/i })).toBeInTheDocument()
    })

    it('calls onEditPersona with updated title on Save', async () => {
      const onEditPersona = vi.fn().mockResolvedValue(undefined)
      render(<PersonaTable {...defaultProps} onEditPersona={onEditPersona} />)

      fireEvent.click(screen.getByRole('button', { name: /Edit VP Engineering/i }))
      const titleInput = screen.getByRole('textbox', { name: /Edit persona title/i })
      fireEvent.change(titleInput, { target: { value: 'CTO' } })
      fireEvent.click(screen.getByRole('button', { name: /Save/i }))

      await waitFor(() => {
        expect(onEditPersona).toHaveBeenCalledWith('p1', expect.objectContaining({ title: 'CTO' }))
      })
    })
  })

  describe('HITL mode', () => {
    it('shows checkboxes in HITL mode', () => {
      render(<PersonaTable {...defaultProps} isHitlMode={true} />)
      expect(screen.getByRole('checkbox', { name: /Select VP Engineering/i })).toBeInTheDocument()
    })

    it('shows Confirm button in HITL mode', () => {
      render(<PersonaTable {...defaultProps} isHitlMode={true} />)
      expect(screen.getByRole('button', { name: /Confirm/i })).toBeInTheDocument()
    })

    it('does not show checkboxes outside HITL mode', () => {
      render(<PersonaTable {...defaultProps} isHitlMode={false} />)
      expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    })

    it('calls onConfirmSelection with selected ids on Confirm', async () => {
      const onConfirmSelection = vi.fn().mockResolvedValue(undefined)
      render(<PersonaTable {...defaultProps} isHitlMode={true} onConfirmSelection={onConfirmSelection} />)
      fireEvent.click(screen.getByRole('button', { name: /Confirm/i }))

      await waitFor(() => {
        expect(onConfirmSelection).toHaveBeenCalledWith(['p1'], [])
      })
    })

    it('allows adding a custom persona', () => {
      render(<PersonaTable {...defaultProps} isHitlMode={true} />)
      fireEvent.click(screen.getByRole('button', { name: /Add custom persona/i }))
      expect(screen.getByRole('textbox', { name: /New persona title/i })).toBeInTheDocument()
    })

    it('adds custom persona to the list when confirmed', async () => {
      const onConfirmSelection = vi.fn().mockResolvedValue(undefined)
      render(<PersonaTable {...defaultProps} isHitlMode={true} onConfirmSelection={onConfirmSelection} />)

      fireEvent.click(screen.getByRole('button', { name: /Add custom persona/i }))
      fireEvent.change(screen.getByRole('textbox', { name: /New persona title/i }), {
        target: { value: 'Head of AI' },
      })
      fireEvent.click(screen.getByRole('button', { name: /^Add$/ }))

      // Custom persona should appear in the table
      await waitFor(() => {
        expect(screen.getByText('Head of AI')).toBeInTheDocument()
      })
    })

    it('includes custom personas in confirm call', async () => {
      const onConfirmSelection = vi.fn().mockResolvedValue(undefined)
      render(<PersonaTable {...defaultProps} isHitlMode={true} onConfirmSelection={onConfirmSelection} />)

      fireEvent.click(screen.getByRole('button', { name: /Add custom persona/i }))
      fireEvent.change(screen.getByRole('textbox', { name: /New persona title/i }), {
        target: { value: 'Head of AI' },
      })
      fireEvent.click(screen.getByRole('button', { name: /^Add$/ }))
      fireEvent.click(screen.getByRole('button', { name: /Confirm/i }))

      await waitFor(() => {
        const [, customPersonas] = onConfirmSelection.mock.calls[0]
        expect((customPersonas as Persona[]).some(p => p.title === 'Head of AI')).toBe(true)
      })
    })
  })
})
