import { useCallback, useEffect, useRef, useState } from 'react'
import { History, Layers3, Plus } from 'lucide-react'
import { api, type Run, type RunCreate, type RunSummary } from './lib/api'
import { RunForm } from './components/RunForm'
import { RunHistory } from './components/RunHistory'
import { RunDetail } from './components/RunDetail'
import { activeStates } from './components/StepTimeline'

const initialBrief: RunCreate = {
  topic: '', audience: '', product_function: '', pain_point: '', style_preference: '备忘录聊天框风',
}

type View = { kind: 'create' | 'history' } | { kind: 'detail'; id: number; topic: string }

function displayError(error: unknown) {
  return error instanceof Error ? error.message : '请求失败，请重试。'
}

export function App() {
  const [view, setView] = useState<View>({ kind: 'create' })
  const [brief, setBrief] = useState(initialBrief)
  const [file, setFile] = useState<File>()
  const [run, setRun] = useState<Run>()
  const [history, setHistory] = useState<RunSummary[]>()
  const [historyError, setHistoryError] = useState<string>()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [creating, setCreating] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const navigation = useRef(0)
  const detailRequest = useRef(0)
  const historyRequest = useRef(0)
  const pending = useRef(false)
  const heading = useRef<HTMLHeadingElement>(null)

  const refreshHistory = useCallback(async () => {
    const request = ++historyRequest.current
    setHistoryError(undefined)
    try {
      const { items } = await api.listRuns()
      if (request === historyRequest.current) setHistory(items)
    } catch (event) {
      if (request === historyRequest.current) setHistoryError(displayError(event))
    }
  }, [])

  const refresh = useCallback(async (id: number, visit: number, afterAction = false) => {
    const request = ++detailRequest.current
    const isCurrent = () => visit === navigation.current && request === detailRequest.current
    try {
      const current = await api.getRun(id)
      if (isCurrent()) {
        setRun(current)
        setError(undefined)
      }
    } catch (event) {
      if (isCurrent()) {
        if (afterAction) setRun(undefined)
        setError(displayError(event))
      }
    }
  }, [])

  useEffect(() => { void refreshHistory() }, [refreshHistory])

  const runId = run?.id
  const polling = run != null && activeStates.has(run.status)
  useEffect(() => {
    if (!polling || runId == null || busy || refreshing) return
    const visit = navigation.current
    let stopped = false
    let timer: number
    const tick = async () => {
      if (stopped || visit !== navigation.current) return
      if (!pending.current) {
        await refresh(runId, visit)
        if (!stopped && visit === navigation.current) void refreshHistory()
      }
      if (!stopped) timer = window.setTimeout(tick, 1500)
    }
    timer = window.setTimeout(tick, 1500)
    return () => { stopped = true; window.clearTimeout(timer) }
  }, [runId, polling, busy, refreshing, refresh, refreshHistory])

  function navigate(next: View, created?: Run) {
    const visit = ++navigation.current
    setRun(created)
    setError(undefined)
    setRefreshing(false)
    setView(next)
    if (next.kind === 'detail' && !created) void refresh(next.id, visit)
    window.requestAnimationFrame(() => {
      if (visit === navigation.current) heading.current?.focus()
    })
  }

  async function reloadDetail(id: number) {
    if (pending.current || refreshing) return
    const visit = navigation.current
    setRefreshing(true)
    setError(undefined)
    await Promise.all([refresh(id, visit), refreshHistory()])
    if (visit === navigation.current) setRefreshing(false)
  }

  async function submit() {
    if (pending.current) return
    pending.current = true
    const visit = navigation.current
    setCreating(true)
    setBusy(true)
    setError(undefined)
    try {
      const upload = file ? await api.upload(file) : undefined
      const created = await api.createRun({ ...brief, upload_asset_ids: upload ? [upload.id] : [] })
      setFile(undefined)
      if (visit === navigation.current) navigate({ kind: 'detail', id: created.id, topic: created.topic }, created)
      void refreshHistory()
    } catch (event) {
      if (visit === navigation.current) setError(displayError(event))
    } finally {
      pending.current = false
      setCreating(false)
      setBusy(false)
    }
  }

  async function runAction(action: (id: number) => Promise<unknown>) {
    if (!run || pending.current || refreshing) return
    pending.current = true
    ++detailRequest.current
    const visit = navigation.current
    setBusy(true)
    setError(undefined)
    try {
      await action(run.id)
      if (visit === navigation.current) await refresh(run.id, visit, true)
    } catch (event) {
      if (visit === navigation.current) {
        await refresh(run.id, visit, true)
        if (visit === navigation.current) setError(displayError(event))
      }
    } finally {
      pending.current = false
      setBusy(false)
      void refreshHistory()
    }
  }

  const detail = view.kind === 'detail' ? view : undefined

  return <>
    <header className="topbar">
      <div className="topbar-inner">
        <div className="brand"><span className="brand-mark"><Layers3 size={20} aria-hidden="true" /></span><h1>小红书内容工作台</h1></div>
        <button className={view.kind === 'create' ? '' : 'primary'} type="button" disabled={creating} onClick={() => navigate({ kind: 'create' })}><Plus size={18} />新建内容</button>
      </div>
    </header>
    <main className={`workspace view-${view.kind}`}>
      <RunHistory headingRef={view.kind === 'history' ? heading : undefined} items={history} error={historyError} selectedId={detail?.id} onRetry={() => void refreshHistory()} onSelect={(item) => navigate({ kind: 'detail', id: item.id, topic: item.topic })} />
      <div className="work-area" hidden={view.kind === 'history'}>
        <button className="history-back" type="button" onClick={() => navigate({ kind: 'history' })}><History size={17} />{detail ? '返回运行历史' : '查看运行历史'}</button>
        <div hidden={view.kind !== 'create'}>
          <RunForm headingRef={view.kind === 'create' ? heading : undefined} value={brief} file={file} busy={busy} creating={creating} error={view.kind === 'create' ? error : undefined} onChange={setBrief} onFileChange={setFile} onSubmit={() => void submit()} />
        </div>
        {detail && (run ? <RunDetail key={run.id} headingRef={heading} run={run} busy={busy || refreshing} refreshing={refreshing} error={error} onRefresh={() => void reloadDetail(run.id)} onAction={runAction} /> :
          <section className="detail-shell detail-loading">
            <p className="run-number">任务 #{detail.id}</p>
            <h2 ref={heading} tabIndex={-1}>{detail.topic}</h2>
            {error ? <><p className="error" role="alert">任务加载失败。{error}</p><button type="button" onClick={() => void reloadDetail(detail.id)}>重新加载任务</button></> : <p role="status">正在加载任务…</p>}
          </section>)}
      </div>
    </main>
  </>
}
