/**
 * Per-company 5-stage pipeline progress indicator.
 * Stages: Signals → Qualifying → Researching → Mapping → Generating
 */
import type { PipelineStatus } from '../api/client'

const STAGES = ['signal_ingestion', 'signal_qualification', 'research', 'solution_mapping', 'persona_generation']

const STAGE_LABELS: Record<string, string> = {
  signal_ingestion: 'Signals',
  signal_qualification: 'Qualifying',
  research: 'Researching',
  solution_mapping: 'Mapping',
  persona_generation: 'Generating',
}

/** Stages that come after the 5-stage pipeline (post-generation). */
const POST_PIPELINE_STAGES = ['awaiting_persona_selection', 'synthesis', 'draft', 'done']

function stageIndex(stage: string | undefined | null): number {
  const normalized = String(stage ?? '').toLowerCase()
  const idx = STAGES.indexOf(normalized)
  if (idx !== -1) return idx
  // Post-pipeline stages should show all 5 stages as complete
  if (POST_PIPELINE_STAGES.includes(normalized)) return STAGES.length
  return 0
}

interface Props {
  currentStage?: string | null
  status: PipelineStatus | string
}

export function ProgressBar({ currentStage, status }: Props) {
  const activeIdx = stageIndex(currentStage)

  return (
    <div className="flex items-center gap-0.5" aria-label="Pipeline progress">
      {STAGES.map((stage, i) => {
        const isDone = i < activeIdx || status === 'completed'
        const isActive = i === activeIdx && status === 'running'
        const label = STAGE_LABELS[stage] ?? stage

        return (
          <div key={stage} className="flex flex-col items-center gap-0.5 flex-1">
            <div
              className={[
                'h-1.5 w-full rounded-full transition-all',
                isDone ? 'bg-green-500' : isActive ? 'bg-blue-500 animate-pulse' : 'bg-gray-200',
              ].join(' ')}
              title={label}
              aria-label={label}
            />
            <span className={`text-[9px] leading-none ${isDone ? 'text-green-600' : isActive ? 'text-blue-600 font-medium' : 'text-gray-400'}`}>
              {label}
            </span>
          </div>
        )
      })}
    </div>
  )
}
