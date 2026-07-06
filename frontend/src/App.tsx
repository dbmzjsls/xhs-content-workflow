import { useMemo, useState } from 'react'
import { AlertTriangle, Boxes, RefreshCw } from 'lucide-react'
import { api, type Run, type RunCreate } from './lib/api'
import { RunForm } from './components/RunForm'
import { StepTimeline } from './components/StepTimeline'
import { DraftPreview } from './components/DraftPreview'
import { ImageAssets } from './components/ImageAssets'
import { ReviewBar } from './components/ReviewBar'

const initialBrief: RunCreate = {
  topic: '睡前20分钟改作文',
  audience: '雅思 5.5-6.5 自学考生',
  product_function: 'Writing Checker',
  pain_point: '作文改了很多遍，还是不知道卡在哪个评分维度',
  style_preference: '备忘录聊天框风',
  reference_path: '',
}

export function App() {
  const [brief, setBrief] = useState<RunCreate>(initialBrief)
  const [run, setRun] = useState<Run | undefined>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | undefined>()

  const latestDraft = useMemo(() => run?.drafts.at(-1), [run])

  const submit = async () => {
    setBusy(true)
    setError(undefined)
    try {
      const payload = { ...brief, reference_path: brief.reference_path || undefined }
      setRun(await api.createRun(payload))
    } catch (event) {
      setError(event instanceof Error ? event.message : String(event))
    } finally {
      setBusy(false)
    }
  }

  const refresh = async (id: number) => setRun(await api.getRun(id))

  return (
    <main>
      <header className="topbar">
        <div className="brand-mark">
          <Boxes size={24} />
        </div>
        <div>
          <h1>小红书内容工作流</h1>
          <p>把写作方法论和图片方法论拆成可审计节点</p>
        </div>
        {run && (
          <button className="ghost" type="button" onClick={() => refresh(run.id)}>
            <RefreshCw size={16} />
            刷新
          </button>
        )}
      </header>

      {error && (
        <div className="error">
          <AlertTriangle size={17} />
          <span>{error}</span>
        </div>
      )}

      <div className="workspace">
        <RunForm value={brief} busy={busy} onChange={setBrief} onSubmit={submit} />
        <StepTimeline steps={run?.steps ?? []} currentStep={run?.current_step} />
        <DraftPreview draft={latestDraft} />
        <ImageAssets images={run?.images ?? []} />
      </div>

      <ReviewBar run={run} onRefresh={refresh} />
    </main>
  )
}
