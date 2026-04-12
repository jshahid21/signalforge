/**
 * Per-company 5-stage pipeline progress indicator.
 * Stages: Signals → Qualifying → Researching → Mapping → Generating
 */
import type { PipelineStatus } from '../api/client'

const STAGES = ['signals', 'qualifying', 'researching', 'mapping', 'generating']

const STAGE_LABELS: Record<string, string> = {
  signals: 'Signals',
  qualifying: 'Qualifying',
  researching: 'Researching',
  mapping: 'Mapping',
  generating: 'Generating',
}

function stageIndex(stage: string | undefined | null): number {
  const normalized = String(stage ?? '').toLowerCase().replace(/_/g, '')
  const idx = STAGES.findIndex(s => normalized.includes(s))
  return idx === -1 ? 0 : idx
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
