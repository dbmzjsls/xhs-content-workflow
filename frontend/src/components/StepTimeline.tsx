import { AlertCircle, Check, Circle, Clock3, LoaderCircle, PauseCircle } from 'lucide-react'
import type { Run, Step } from '../lib/api'

export const activeStates = new Set(['queued', 'running', 'image_queued', 'image_running'])

const statuses: Record<string, { label: string; tone: string; icon: typeof Circle }> = {
  queued: { label: '文案排队中', tone: 'running', icon: Clock3 },
  running: { label: '文案生成中', tone: 'running', icon: LoaderCircle },
  copy_review_required: { label: '待文案审核', tone: 'review', icon: Clock3 },
  image_queued: { label: '图片排队中', tone: 'running', icon: Clock3 },
  image_running: { label: '图片生成中', tone: 'running', icon: LoaderCircle },
  asset_review_required: { label: '待素材审核', tone: 'review', icon: Clock3 },
  completed: { label: '已完成', tone: 'success', icon: Check },
  failed: { label: '失败', tone: 'failed', icon: AlertCircle },
  canceled: { label: '已取消', tone: 'neutral', icon: PauseCircle },
}
const stages = ['生成文案', '文案审核', '生成图片', '素材审核', '完成']
const stageByStatus = new Map([
  ['queued', 0], ['running', 0], ['copy_review_required', 1], ['image_queued', 2],
  ['image_running', 2], ['asset_review_required', 3], ['completed', 4],
])
const stageByStep = new Map([
  ['text_generation', 0], ['draft_revision', 1], ['revision', 1], ['copy_review', 1],
  ['image_generation', 2], ['asset_review', 3], ['export_package', 4],
])
const stepNames: Record<string, string> = {
  text_generation: '生成文案', brief_normalize: '整理 Brief', style_route: '匹配图片风格',
  narrative_plan: '拟定叙事结构', draft_generate: '撰写文案', candidate_round: '生成并检查候选',
  humanize_check: '检查表达', xhs_quality_check: '检查文案规则', draft_selection: '选择文案',
  copy_review: '文案审核', copy_approval: '通过文案', revision: '返修文案', draft_revision: '返修文案',
  image_generation: '生成图片', image_task_classify: '划分图片任务', reference_select: '选择参考信息',
  prompt_rewrite: '改写提示词', image_generate: '生成图片素材', image_qc: '提示词约束检查',
  prompt_contract_check: '提示词约束检查', asset_review: '素材审核', human_review: '人工审核',
  asset_approval: '通过素材', asset_validation: '验证导出素材', export_package: '导出发布包',
}
const stepStatuses: Record<string, string> = { queued: '排队中', running: '执行中', completed: '已完成', failed: '失败', canceled: '已取消' }

export function RunStatus({ status }: { status: string }) {
  const { label, tone, icon: Icon } = Object.hasOwn(statuses, status) ? statuses[status] : { label: status, tone: 'neutral', icon: Circle }
  return <span className={`run-status tone-${tone}`}><Icon size={14} aria-hidden="true" />{label}</span>
}

export function runStage(run: Run) {
  if (run.status === 'failed') return stageByStep.get(run.current_step)
  return stageByStatus.get(run.status)
}

export function StageProgress({ run }: { run: Run }) {
  const stage = runStage(run)
  const current = stage === undefined ? (run.status === 'canceled' ? '运行已取消' : '当前阶段未知') : stages[stage]
  const progress = <ol className="stage-list">{stages.map((name, index) => {
    const done = stage !== undefined && (index < stage || (index === stage && run.status === 'completed'))
    const active = index === stage && !done
    const Icon = done ? Check : active && run.status === 'failed' ? AlertCircle : Circle
    return <li key={name} aria-current={index === stage ? 'step' : undefined} className={done ? 'done' : active ? (run.status === 'failed' ? 'failed' : 'current') : ''}>
      <span className="stage-marker"><Icon size={15} aria-hidden="true" /></span><span>{name}</span>
      {done && <span className="sr-only">已完成</span>}
    </li>
  })}</ol>

  return <div className="stage-progress" aria-label="工作流阶段">
    <div className="stages-wide">{progress}</div>
    <details className="stages-narrow"><summary>{current}<span>查看全部阶段</span></summary>{progress}</details>
  </div>
}

export function StepTimeline({ steps }: { steps: Step[] }) {
  return <details className="context-card">
    <summary>执行记录 <span className="summary-count">{steps.length} 条</span></summary>
    {steps.length ? <ol className="step-records">{steps.map((step, index) => {
      const status = step.error === 'canceled' ? 'canceled' : step.status
      const time = step.started_at ?? step.created_at
      return <li key={`${step.name}-${step.attempt}-${index}`}>
        <strong>{Object.hasOwn(stepNames, step.name) ? stepNames[step.name] : step.name}</strong>
        <span>{Object.hasOwn(stepStatuses, status) ? stepStatuses[status] : status} · 第 {step.attempt} 次尝试</span>
        <time dateTime={time}>{new Date(time).toLocaleString('zh-CN')}{step.duration_ms !== null && ` · ${step.duration_ms} ms`}</time>
        {step.error && status !== 'canceled' && <p className="step-error">{step.error}</p>}
      </li>
    })}</ol> : <p className="context-empty">暂无执行记录</p>}
  </details>
}
