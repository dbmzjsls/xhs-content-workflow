import { AlertCircle, FileText, LoaderCircle, RefreshCw } from 'lucide-react'
import { useState, type Ref } from 'react'
import { api, type Run } from '../lib/api'
import { DraftPreview, draftChecks, draftLabel } from './DraftPreview'
import { ImageAssets } from './ImageAssets'
import { ReviewBar } from './ReviewBar'
import { referenceUsage } from './RunForm'
import { RunStatus, StageProgress, StepTimeline, activeStates, runStage } from './StepTimeline'

const failureLabels = ['文案生成失败', '文案返修失败', '图片生成失败', '素材审核失败', '导出失败']
const imageStates = new Set(['image_queued', 'image_running', 'asset_review_required', 'completed'])

export function RunDetail({ run, busy, refreshing, error, headingRef, onRefresh, onAction }: {
  run: Run
  busy: boolean
  refreshing: boolean
  error?: string
  headingRef?: Ref<HTMLHeadingElement>
  onRefresh: () => void
  onAction: (action: (id: number) => Promise<unknown>) => Promise<void>
}) {
  const [browsing, setBrowsing] = useState<{ draftId: number; selectedId?: number }>()
  const selected = run.drafts.find((draft) => draft.selected)
  const selectedId = selected?.id
  const copyReview = run.status === 'copy_review_required'
  const visibleDraftId = browsing?.selectedId === selectedId ? browsing?.draftId : undefined
  const draft = run.drafts.find((item) => item.id === visibleDraftId) ?? selected ?? run.drafts[0]
  const reviewActionsEnabled = copyReview && selectedId !== undefined && draft?.id === selectedId
  const stage = runStage(run)
  const showImages = imageStates.has(run.status) || run.images.length > 0 || (run.status === 'failed' && stage === 2)
  const active = activeStates.has(run.status)
  const checks = draft ? draftChecks(draft, run.steps) : undefined
  const fields = [['目标人群', run.audience], ['产品功能', run.product_function], ['痛点场景', run.pain_point], ['图片风格', run.style_preference]]

  const copy = draft && <DraftPreview draft={draft} drafts={run.drafts} steps={run.steps} reviewing={copyReview} busy={busy} onActiveChange={(draftId) => setBrowsing({ draftId, selectedId })} onSelect={(item) => {
    if (copyReview && item.id === draft.id && checks?.hard?.passed === true && !item.selected) {
      void onAction((id) => api.selectDraft(id, item.id))
    }
  }} />

  return <section className="detail-shell" aria-labelledby="run-title">
    <header className="detail-header">
      <div><p className="run-number">任务 #{run.id}</p><h2 id="run-title" ref={headingRef} tabIndex={-1}>{run.topic}</h2></div>
      <div className="detail-controls"><span aria-live="polite"><RunStatus status={run.status} /></span><button type="button" disabled={busy} onClick={onRefresh}><RefreshCw size={16} />{refreshing ? '刷新中…' : '刷新'}</button></div>
    </header>
    <StageProgress run={run} />
    <div className="detail-layout">
      <div className="detail-main">
        {error && <p className="error" role="alert">{error}</p>}
        {run.status === 'failed' && <section className="phase-card phase-error"><AlertCircle size={23} /><div><h3>{stage === undefined ? '运行失败' : failureLabels[stage]}</h3>{run.error && <p>{run.error}</p>}</div></section>}
        {run.status === 'canceled' && <section className="phase-card"><h3>运行已取消</h3></section>}
        {active && <section className="phase-card"><span className="icon-tile blue"><LoaderCircle size={22} /></span><div><h3>{stage === 2 ? '正在处理图片' : '正在处理文案'}</h3><p>{run.status.endsWith('queued') ? '任务已进入队列，等待执行。' : '生成结果将在此处更新。'}</p></div></section>}
        {run.status === 'completed' && <section className="phase-card phase-success"><FileText size={23} /><div><h3>图文已完成</h3><p>{run.final_package?.zip_url ? '发布包已准备好，可在下方下载。' : '可查看本次运行的文案与素材。'}</p></div></section>}
        {showImages && <ImageAssets images={run.images} reviewing={run.status === 'asset_review_required'} />}
        {copy && (showImages ? <details className="context-card archived-copy"><summary>查看已保存文案{selected ? ` · ${selected.title}` : ''}</summary>{copy}</details> : copy)}
        {copyReview && !draft && <p className="phase-card">此任务暂无可供审核的文案。</p>}
      </div>
      <aside className="detail-context" aria-label="任务背景">
        <details className="context-card brief-summary">
          <summary>Brief 摘要</summary>
          <dl>{fields.map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value || '未填写'}</dd></div>)}</dl>
          <p>{referenceUsage}</p>
        </details>
        {copyReview && <details className="context-card">
          <summary>当前检查摘要</summary>
          <p>{checks?.hard?.passed === true ? '硬规则通过' : checks?.hard?.passed === false ? '硬规则未通过' : '暂无硬规则结果'}</p>
          <p>{typeof checks?.soft?.total === 'number' ? `综合评分 ${checks.soft.total} / 100` : '暂无评分'}</p>
        </details>}
        <StepTimeline steps={run.steps} />
      </aside>
    </div>
    <ReviewBar run={run} busy={busy} reviewActionsEnabled={reviewActionsEnabled} selectedLabel={selected && draftLabel(selected, run.drafts)} onAction={onAction} />
  </section>
}
