/**
 * Regression tests for ProgressBar — ensures stage names from the backend
 * are correctly mapped to progress bar positions.
 * Added for GitHub Issue #27.
 */
import { render, screen } from '@testing-library/react'
import { ProgressBar } from '../components/ProgressBar'

describe('ProgressBar', () => {
  it('renders all five stages', () => {
    render(<ProgressBar currentStage="signal_ingestion" status="running" />)
    expect(screen.getByText('Signals')).toBeInTheDocument()
    expect(screen.getByText('Qualifying')).toBeInTheDocument()
    expect(screen.getByText('Researching')).toBeInTheDocument()
    expect(screen.getByText('Mapping')).toBeInTheDocument()
    expect(screen.getByText('Generating')).toBeInTheDocument()
  })

  it('highlights signal_ingestion as the first active stage', () => {
    render(<ProgressBar currentStage="signal_ingestion" status="running" />)
    const bar = screen.getByLabelText('Signals')
    expect(bar.className).toContain('bg-blue-500')
  })

  it('highlights signal_qualification as the second stage', () => {
    render(<ProgressBar currentStage="signal_qualification" status="running" />)
    const bar = screen.getByLabelText('Qualifying')
    expect(bar.className).toContain('bg-blue-500')
    // First stage should be done (green)
    const first = screen.getByLabelText('Signals')
    expect(first.className).toContain('bg-green-500')
  })

  it('highlights research as the third stage', () => {
    render(<ProgressBar currentStage="research" status="running" />)
    const bar = screen.getByLabelText('Researching')
    expect(bar.className).toContain('bg-blue-500')
  })

  it('highlights solution_mapping as the fourth stage', () => {
    render(<ProgressBar currentStage="solution_mapping" status="running" />)
    const bar = screen.getByLabelText('Mapping')
    expect(bar.className).toContain('bg-blue-500')
  })

  it('highlights persona_generation as the fifth stage', () => {
    render(<ProgressBar currentStage="persona_generation" status="running" />)
    const bar = screen.getByLabelText('Generating')
    expect(bar.className).toContain('bg-blue-500')
  })

  it('marks all stages green when status is completed', () => {
    render(<ProgressBar currentStage="persona_generation" status="completed" />)
    const bars = screen.getAllByTitle(/Signals|Qualifying|Researching|Mapping|Generating/)
    bars.forEach(bar => {
      expect(bar.className).toContain('bg-green-500')
    })
  })

  it('shows all stages as done for post-pipeline stages', () => {
    const postStages = ['awaiting_persona_selection', 'synthesis', 'draft', 'done']
    for (const stage of postStages) {
      const { unmount } = render(<ProgressBar currentStage={stage} status="running" />)
      const bars = screen.getAllByTitle(/Signals|Qualifying|Researching|Mapping|Generating/)
      bars.forEach(bar => {
        expect(bar.className).toContain('bg-green-500')
      })
      unmount()
    }
  })

  it('falls back to index 0 for unknown stage names', () => {
    render(<ProgressBar currentStage="unknown_stage" status="running" />)
    const bar = screen.getByLabelText('Signals')
    expect(bar.className).toContain('bg-blue-500')
  })
})
