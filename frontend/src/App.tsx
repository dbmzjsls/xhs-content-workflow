import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Boxes, RefreshCw } from 'lucide-react'
import { api, type Draft, type Run, type RunCreate, type RunSummary } from './lib/api'
import { RunForm } from './components/RunForm'
import { StepTimeline } from './components/StepTimeline'
import { DraftPreview } from './components/DraftPreview'
import { ImageAssets } from './components/ImageAssets'
import { ReviewBar } from './components/ReviewBar'

const initialBrief: RunCreate = { topic: '睡前 20 分钟改作文', audience: '雅思 5.5-6.5 自学考生', product_function: 'Writing Checker', pain_point: '作文改了很多遍，还是不知道卡在哪个评分维度', style_preference: '备忘录聊天框风' }
const pollingStates = new Set(['queued', 'running', 'image_queued', 'image_running'])
const imageVisibleStates = new Set(['image_queued', 'image_running', 'asset_review_required', 'completed'])
const label: Record<string, string> = { queued: '排队中', running: '文案生成中', copy_review_required: '等待文案审核', image_queued: '图片排队中', image_running: '图片生成中', asset_review_required: '等待资产审核', completed: '已完成', failed: '失败', canceled: '已取消' }

function displayError(error: unknown) { return error instanceof Error ? error.message : String(error) }
function imagePanelVisible(run: Run) { return imageVisibleStates.has(run.status) || (run.status === 'failed' && run.current_step === 'image_generation') }

export function App() {
  const [brief, setBrief] = useState<RunCreate>(initialBrief)
  const [file, setFile] = useState<File | undefined>()
  const [run, setRun] = useState<Run | undefined>()
  const [history, setHistory] = useState<RunSummary[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | undefined>()

  const refreshHistory = useCallback(async () => setHistory((await api.listRuns()).items), [])
  const refresh = useCallback(async (id: number) => {
    const current = await api.getRun(id)
    setRun(current)
    await refreshHistory()
    return current
  }, [refreshHistory])

  useEffect(() => { void refreshHistory().catch((event) => setError(displayError(event))) }, [refreshHistory])
  useEffect(() => {
    if (!run || !pollingStates.has(run.status)) return
    const timer = window.setInterval(() => { void refresh(run.id).catch((event) => setError(displayError(event))) }, 1500)
    return () => window.clearInterval(timer)
  }, [run?.id, run?.status, refresh])

  const runAction = async (action: () => Promise<unknown>) => {
    if (!run) return
    setBusy(true); setError(undefined)
    try { await action(); await refresh(run.id) } catch (event) { setError(displayError(event)); await refresh(run.id).catch(() => undefined) } finally { setBusy(false) }
  }

  const submit = async () => {
    setBusy(true); setError(undefined)
    try {
      const upload = file ? await api.upload(file) : undefined
      const created = await api.createRun({ ...brief, upload_asset_ids: upload ? [upload.id] : [] })
      setRun(created); setFile(undefined); await refreshHistory()
    } catch (event) { setError(displayError(event)) } finally { setBusy(false) }
  }

  const selected = useMemo(() => run?.drafts.find((draft) => draft.selected), [run])
  const select = async (draft: Draft) => runAction(async () => { if (run) await api.selectDraft(run.id, draft.id) })

  return <main>
    <header className="topbar"><div className="brand-mark"><Boxes size={24} /></div><div><h1>小红书内容工作流</h1><p>把文案、图片与审核拆成可追溯的交付节点</p></div>{run && <button className="ghost" type="button" onClick={() => void refresh(run.id)}><RefreshCw size={16} />刷新</button>}</header>
    {error && <div className="error" role="alert"><AlertTriangle size={17} /><span>{error}</span><button type="button" onClick={() => setError(undefined)}>关闭</button></div>}
    <div className="workspace">
      <RunForm value={brief} file={file} busy={busy} onChange={setBrief} onFileChange={setFile} onSubmit={() => void submit()} />
      <section className="panel history-panel"><div className="panel-title"><RefreshCw size={18} /><span>运行历史</span></div>{history.length === 0 ? <div className="empty-line">暂无历史运行</div> : <ul>{history.map((item) => <li key={item.id}><button type="button" className={run?.id === item.id ? 'active' : ''} onClick={() => { setError(undefined); void refresh(item.id).catch((event) => setError(displayError(event))) }}><b>#{item.id} {item.topic}</b><span className={`run-status ${item.status}`}>{label[item.status] ?? item.status}</span><small>{new Date(item.updated_at).toLocaleString()}</small></button></li>)}</ul>}</section>
      <StepTimeline steps={run?.steps ?? []} currentStep={run?.current_step} />
      <DraftPreview drafts={run?.drafts ?? []} steps={run?.steps ?? []} canSelect={run?.status === 'copy_review_required'} onSelect={select} />
      {run && imagePanelVisible(run) && <ImageAssets images={run.images} />}
    </div>
    {selected && run?.status === 'copy_review_required' && <p className="selection-note">当前选择：方案 {selected.candidate}。可提交修改意见，或通过文案进入图片生成。</p>}
    <ReviewBar run={run} busy={busy} onRevise={(instructions) => runAction(async () => { if (run) await api.revise(run.id, instructions) })} onApproveCopy={() => runAction(async () => { if (run) await api.approveCopy(run.id) })} onApproveAssets={() => runAction(async () => { if (run) await api.approveAssets(run.id) })} onRetry={() => runAction(async () => { if (run) await api.retry(run.id) })} onCancel={() => runAction(async () => { if (run) await api.cancel(run.id) })} />
  </main>
}
