import { Check, Download, RotateCcw, Send, SquareX, TimerReset } from 'lucide-react'
import { useState } from 'react'
import { api, type Run } from '../lib/api'

type Props = { run?: Run; busy: boolean; reviewActionsEnabled: boolean; onRevise: (instructions: string) => Promise<void>; onApproveCopy: () => Promise<void>; onApproveAssets: () => Promise<void>; onRetry: () => Promise<void>; onCancel: () => Promise<void> }
const active = new Set(['queued', 'running', 'image_queued', 'image_running'])

export function ReviewBar({ run, busy, reviewActionsEnabled, onRevise, onApproveCopy, onApproveAssets, onRetry, onCancel }: Props) {
  const [instructions, setInstructions] = useState('把语气再自然一点，减少产品感。')
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string>()
  if (!run) return null
  const copyReview = run.status === 'copy_review_required'
  const assetReview = run.status === 'asset_review_required'
  const completed = run.status === 'completed'
  const runId = run.id
  const downloadUrl = run.final_package?.zip_url
  async function downloadExport() {
    if (!downloadUrl || downloading) return
    setDownloading(true)
    setDownloadError(undefined)
    try {
      const { blob, filename } = await api.download(downloadUrl)
      const objectUrl = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = objectUrl
      anchor.download = filename ?? `run-${runId}.zip`
      anchor.click()
      URL.revokeObjectURL(objectUrl)
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : '下载失败')
    } finally {
      setDownloading(false)
    }
  }
  return <section className="review-bar"><div><b>{copyReview ? '文案审核' : assetReview ? '资产审核' : '运行状态'}</b><span>{downloadError || run.error || (completed ? '发布包已导出' : run.current_step)}</span></div>
    {copyReview && <><input data-testid="revision-instructions" aria-label="修改指令" value={instructions} onChange={(event) => setInstructions(event.target.value)} placeholder="输入具体修改指令" /><button data-testid="revise-draft" type="button" title={reviewActionsEnabled ? undefined : '请先选择当前可见文案'} onClick={() => void onRevise(instructions.trim())} disabled={busy || !instructions.trim() || !reviewActionsEnabled}><RotateCcw size={16} />返修</button><button data-testid="approve-copy" type="button" className="primary" title={reviewActionsEnabled ? undefined : '请先选择当前可见文案'} onClick={() => void onApproveCopy()} disabled={busy || !reviewActionsEnabled}><Send size={16} />通过文案</button></>}
    {assetReview && <button data-testid="approve-assets" type="button" className="primary" onClick={() => void onApproveAssets()} disabled={busy}><Check size={16} />通过资产并导出</button>}
    {run.status === 'failed' && <button data-testid="retry-run" type="button" onClick={() => void onRetry()} disabled={busy}><TimerReset size={16} />重试</button>}
    {active.has(run.status) && <button type="button" className="danger" onClick={() => void onCancel()} disabled={busy}><SquareX size={16} />取消运行</button>}
    <a data-testid="export-download" className={`download ${completed && !downloading ? '' : 'disabled'}`} href={downloadUrl ?? undefined} onClick={(event) => { event.preventDefault(); void downloadExport() }}><Download size={16} />{downloading ? '下载中…' : '下载发布包'}</a>
  </section>
}
