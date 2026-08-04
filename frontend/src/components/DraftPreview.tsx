import { CheckCircle2, ClipboardCheck, FileText, XCircle } from 'lucide-react'
import { useMemo } from 'react'
import type { Draft, Step } from '../lib/api'

type CandidateMeta = { candidate: number; angle?: string; recommended?: boolean; hard_report?: { passed?: boolean; issues?: string[] }; score_report?: { total?: number; dimensions?: Record<string, number> } }

function candidateMeta(steps: Step[]): CandidateMeta[] {
  const result = steps.find((step) => step.name === 'candidate_round')?.output_payload
  const candidates = result?.candidates
  return Array.isArray(candidates) ? candidates.filter((item): item is CandidateMeta => typeof item === 'object' && item !== null && 'candidate' in item) : []
}

export function DraftPreview({ drafts, steps, canSelect, activeId, onActiveChange, onSelect }: { drafts: Draft[]; steps: Step[]; canSelect: boolean; activeId?: number; onActiveChange: (draftId: number) => void; onSelect: (draft: Draft) => Promise<void> }) {
  const candidates = useMemo(() => drafts.filter((draft) => draft.parent_draft_id === null).sort((a, b) => a.candidate - b.candidate), [drafts])
  const displayDrafts = useMemo(() => [...drafts].sort((a, b) => a.candidate - b.candidate || a.id - b.id), [drafts])
  const activeDraft = drafts.find((draft) => draft.selected) ?? candidates[0]
  const draft = displayDrafts.find((item) => item.id === activeId) ?? activeDraft
  if (!draft) return <section className="panel empty"><FileText size={20} /><span>运行工作流后生成三版图文候选</span></section>

  const meta = candidateMeta(steps).find((item) => item.candidate === draft.candidate)
  const hard = (draft.quality_report.hard as { passed?: boolean; issues?: string[] } | undefined) ?? meta?.hard_report
  const soft = (draft.quality_report.soft as { total?: number; dimensions?: Record<string, number> } | undefined) ?? meta?.score_report
  const score = soft?.total ?? 0
  const dimensions = soft?.dimensions ?? {}
  const recommended = meta?.recommended ?? draft.selected

  return <section className="panel draft-panel">
    <div className="panel-title"><FileText size={18} /><span>文案候选 · 复制审核</span></div>
    <div className="candidate-tabs" role="tablist" aria-label="文案候选">
      {displayDrafts.map((item) => {
        const revision = item.parent_draft_id !== null
        return <button data-testid={revision ? `revision-tab-${item.id}` : `candidate-tab-${item.candidate}`} key={item.id} type="button" className={item.id === draft.id ? 'active' : ''} onClick={() => onActiveChange(item.id)}>{revision ? `Revision · 方案 ${item.candidate}` : `方案 ${item.candidate}`}{item.selected && ' · 已选'}</button>
      })}
    </div>
    <div className="candidate-meta">
      <span>角度：{meta?.angle ?? (draft.narrative_plan.angle as string | undefined) ?? '内容候选'}</span>
      <span className={hard?.passed ? 'status-pass' : 'status-fail'}>{hard?.passed ? <CheckCircle2 size={15} /> : <XCircle size={15} />}{hard?.passed ? '硬规则通过' : '硬规则待修复'}</span>
      {recommended && <b>推荐方案</b>}
    </div>
    <div className="score-strip"><strong>{score}<small>/100</small></strong>{Object.entries(dimensions).map(([name, value]) => <span key={name}>{name} {value}/20</span>)}</div>
    <div className="note-preview"><h2>{draft.title}</h2><p>{draft.body}</p><div className="tags">{draft.tags.map((tag) => <span key={tag}>{tag}</span>)}</div></div>
    <div className="first-comment"><b>首评</b><span>{draft.first_comment ?? '—'}</span></div>
    <div className="qc-block"><div className={hard?.passed ? 'qc-pass' : 'qc-warn'}><ClipboardCheck size={16} /><span>{hard?.passed ? '可选择并提交审核' : '该方案不可选择'}</span></div>{hard?.issues?.length ? <ul>{hard.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul> : null}</div>
    {canSelect && <button data-testid="select-candidate" type="button" className="select-candidate" disabled={!hard?.passed || draft.selected} onClick={() => void onSelect(draft)}>{draft.selected ? '当前已选方案' : '选择此方案'}</button>}
  </section>
}
