import { CheckCircle2, FileText, XCircle } from 'lucide-react'
import type { Draft, Step } from '../lib/api'

type CandidateMeta = { candidate: number; angle?: string; recommended?: boolean; hard_report?: HardReport; score_report?: ScoreReport }
type HardReport = { passed?: boolean; issues?: string[] }
type ScoreReport = { total?: number; dimensions?: Record<string, number> }

function candidateRound(steps: Step[]) {
  return [...steps].reverse().find((step) => step.name === 'candidate_round' && Array.isArray(step.output_payload.candidates))?.output_payload
}

export function draftLabel(draft: Draft, drafts: Draft[]) {
  const number = drafts.filter((item) => item.candidate === draft.candidate && item.parent_draft_id !== null && item.id <= draft.id).length
  return `方案 ${draft.candidate}${draft.parent_draft_id !== null ? ` · 返修 ${number}` : ''}`
}

export function draftChecks(draft: Draft, steps: Step[]) {
  const round = candidateRound(steps)
  const candidates = round?.candidates as CandidateMeta[] | undefined
  const meta = draft.parent_draft_id === null ? candidates?.find((item) => item?.candidate === draft.candidate) : undefined
  return {
    hard: (draft.quality_report.hard as HardReport | undefined) ?? meta?.hard_report,
    soft: (draft.quality_report.soft as ScoreReport | undefined) ?? meta?.score_report,
    angle: (draft.narrative_plan.angle as string | undefined) ?? meta?.angle,
    recommended: draft.parent_draft_id === null && (meta?.recommended === true || round?.recommended_candidate === draft.candidate),
  }
}

export function DraftPreview({ draft, drafts, steps, reviewing, busy, onActiveChange, onSelect }: {
  draft: Draft
  drafts: Draft[]
  steps: Step[]
  reviewing: boolean
  busy: boolean
  onActiveChange: (draftId: number) => void
  onSelect: (draft: Draft) => void
}) {
  const displayDrafts = [...drafts].sort((a, b) => a.candidate - b.candidate || a.id - b.id)
  const { hard, soft, angle, recommended } = draftChecks(draft, steps)
  const parent = drafts.find((item) => item.id === draft.parent_draft_id)
  const selected = drafts.find((item) => item.selected)
  const dimensions = Object.entries(soft?.dimensions ?? {})
  const activeIndex = displayDrafts.findIndex((item) => item.id === draft.id)

  return <section className="panel draft-panel">
    <div className="panel-title"><span className="icon-tile purple"><FileText size={18} /></span><h3>{reviewing ? '文案审核' : draft.is_final ? '已通过文案' : '文案记录'}</h3></div>
    <div className="candidate-tabs" role="tablist" aria-label="文案版本" onKeyDown={(event) => {
      const last = displayDrafts.length - 1
      const index = ({ ArrowLeft: (activeIndex + last) % displayDrafts.length, ArrowRight: (activeIndex + 1) % displayDrafts.length, Home: 0, End: last } as Record<string, number>)[event.key]
      if (index === undefined) return
      event.preventDefault()
      const next = displayDrafts[index]
      onActiveChange(next.id)
      document.getElementById(`draft-tab-${next.id}`)?.focus()
    }}>
      {displayDrafts.map((item) => <button
        data-testid={item.parent_draft_id !== null ? `revision-tab-${item.id}` : `candidate-tab-${item.candidate}`}
        id={`draft-tab-${item.id}`} key={item.id} type="button" role="tab" aria-controls="draft-content"
        aria-selected={item.id === draft.id} tabIndex={item.id === draft.id ? 0 : -1}
        className={item.id === draft.id ? 'active' : ''} onClick={() => onActiveChange(item.id)}
      >{draftLabel(item, drafts)}{item.selected && <small>已选</small>}</button>)}
    </div>
    <div id="draft-content" role="tabpanel" aria-labelledby={`draft-tab-${draft.id}`} tabIndex={0}>
      <div className="candidate-meta">
        <span>正在查看 <strong>{draftLabel(draft, drafts)}</strong></span>
        {selected && <span>已选 <strong>{draftLabel(selected, drafts)}</strong></span>}
        {recommended && <span className="pill">系统推荐</span>}
      </div>
      <div className="draft-checks">
        {angle && <span>角度 · {angle}</span>}
        <span className={hard?.passed === true ? 'status-pass' : hard?.passed === false ? 'status-fail' : ''}>
          {hard?.passed === true ? <><CheckCircle2 size={16} />硬规则通过</> : hard?.passed === false ? <><XCircle size={16} />硬规则未通过</> : '暂无硬规则结果'}
        </span>
        <span>{typeof soft?.total === 'number' ? <><strong>{soft.total}</strong> / 100</> : '暂无评分'}</span>
      </div>
      {parent && <p className="muted revision-parent">返修自 {draftLabel(parent, drafts)}</p>}
      {dimensions.length > 0 && <details className="score-details"><summary>评分维度</summary><ul>{dimensions.map(([name, value]) => <li key={name}>{name} {value}/20</li>)}</ul></details>}
      {Boolean(hard?.issues?.length) && <ul className="rule-issues">{hard?.issues?.map((issue, index) => <li key={index}>{issue}</li>)}</ul>}
      {reviewing && <div className="selection-control">
        <button data-testid="select-candidate" type="button" disabled={busy || hard?.passed !== true || draft.selected} onClick={() => onSelect(draft)}>{draft.selected ? '当前已选方案' : '选择此方案'}</button>
        {!draft.selected && hard?.passed !== true && <small>硬规则通过后才能选择。</small>}
      </div>}
      <article className="note-preview"><h2>{draft.title}</h2><p>{draft.body}</p><div className="tags">{draft.tags.map((tag, index) => <span key={index}>{tag}</span>)}</div></article>
      <div className="first-comment"><strong>首评</strong><p>{draft.first_comment || '暂无首评'}</p></div>
    </div>
  </section>
}
