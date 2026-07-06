import { CheckCircle2, CircleDot, Loader2 } from 'lucide-react'
import type { Step } from '../lib/api'

const expected = [
  'brief_normalize',
  'style_route',
  'narrative_plan',
  'draft_generate',
  'humanize_check',
  'xhs_quality_check',
  'revision',
  'image_task_classify',
  'reference_select',
  'prompt_rewrite',
  'image_generate',
  'image_qc',
  'human_review',
]

export function StepTimeline({ steps, currentStep }: { steps: Step[]; currentStep?: string }) {
  const done = new Set(steps.map((step) => step.name))

  return (
    <section className="panel timeline-panel">
      <div className="panel-title">
        <CircleDot size={18} />
        <span>LangGraph 节点</span>
      </div>
      <ol className="timeline">
        {expected.map((name) => {
          const isDone = done.has(name)
          const isCurrent = currentStep === name
          return (
            <li key={name} className={isDone ? 'done' : isCurrent ? 'current' : ''}>
              {isDone ? <CheckCircle2 size={16} /> : isCurrent ? <Loader2 size={16} /> : <CircleDot size={16} />}
              <span>{name}</span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
