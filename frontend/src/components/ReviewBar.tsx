import { Check, Download, RotateCcw, Send, SquareX } from 'lucide-react'
import { useRef, useState } from 'react'
import { api, type Run } from '../lib/api'
import { activeStates } from './StepTimeline'

export function ReviewBar({ run, busy, reviewActionsEnabled, selectedLabel, onAction }: {
  run: Run
  busy: boolean
  reviewActionsEnabled: boolean
  selectedLabel?: string
  onAction: (action: (id: number) => Promise<unknown>) => Promise<void>
}) {
  const [instructions, setInstructions] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string>()
  const downloadPending = useRef(false)
  const copyReview = run.status === 'copy_review_required'
  const assetReview = run.status === 'asset_review_required'
  const completed = run.status === 'completed'
  const downloadUrl = run.final_package?.zip_url
  const cleanInstructions = instructions.trim()

  async function downloadExport() {
    if (!downloadUrl || downloadPending.current) return
    downloadPending.current = true
    setDownloading(true)
    setDownloadError(undefined)
    try {
      const { blob, filename } = await api.download(downloadUrl)
      const objectUrl = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = objectUrl
      anchor.download = filename ?? `run-${run.id}.zip`
      anchor.click()
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : '请求失败，请重试。')
    } finally {
      downloadPending.current = false
      setDownloading(false)
    }
  }

  if (copyReview) return <section className="review-bar" aria-label="文案审核操作">
    <div className="review-info">
      <strong>{selectedLabel ? `审核对象 · ${selectedLabel}` : '尚未选中文案'}</strong>
      <p>{reviewActionsEnabled ? '可直接通过，或填写修改意见后返修。' : '当前查看内容尚未选中。请先选择此方案。'}</p>
    </div>
    <label className="revision-field"><span>修改意见</span><textarea data-testid="revision-instructions" rows={1} maxLength={500} value={instructions} onChange={(event) => setInstructions(event.target.value)} placeholder="例如：语气更自然，减少产品感" /></label>
    <div className="review-actions">
      <button data-testid="revise-draft" type="button" onClick={() => {
        if (reviewActionsEnabled && cleanInstructions) void onAction((id) => api.revise(id, cleanInstructions))
      }} disabled={busy || !cleanInstructions || !reviewActionsEnabled}><RotateCcw size={16} />返修</button>
      <button data-testid="approve-copy" type="button" className="primary" onClick={() => {
        if (reviewActionsEnabled) void onAction(api.approveCopy)
      }} disabled={busy || !reviewActionsEnabled}><Send size={16} />通过文案并生成图片</button>
    </div>
  </section>

  if (assetReview) return <section className="review-bar" aria-label="素材审核操作">
    <div className="review-info"><strong>审核对象 · 整组素材</strong><p>共 {run.images.length} 项，通过后将导出发布包。</p></div>
    <button data-testid="approve-assets" type="button" className="primary" onClick={() => void onAction(api.approveAssets)} disabled={busy}><Check size={17} />通过素材并导出</button>
  </section>

  if (completed) return <section className="review-bar" aria-label="发布包下载">
    <div className="review-info"><strong>发布包</strong><p>{downloadUrl ? '已导出 Markdown、JSON 和图片素材。' : '该任务暂无可用的发布包下载地址。'}</p>
      {downloadError && <p className="error" role="alert">下载失败。{downloadError}</p>}
    </div>
    <button data-testid="export-download" type="button" className="primary" disabled={!downloadUrl || downloading} onClick={() => void downloadExport()}><Download size={17} />{downloading ? '下载中…' : '下载发布包'}</button>
  </section>

  if (run.status === 'failed') return <section className="review-bar" aria-label="运行恢复">
    <div className="review-info"><strong>恢复运行</strong><p>从失败阶段继续处理。</p></div>
    <button data-testid="retry-run" type="button" className="primary" onClick={() => void onAction(api.retry)} disabled={busy}><RotateCcw size={17} />重试</button>
  </section>

  if (activeStates.has(run.status)) return <section className="review-bar" aria-label="运行操作">
    <button type="button" className="danger" onClick={() => void onAction(api.cancel)} disabled={busy}><SquareX size={17} />取消运行</button>
  </section>

  return null
}
