import { History } from 'lucide-react'
import type { Ref } from 'react'
import type { RunSummary } from '../lib/api'
import { RunStatus } from './StepTimeline'

export function RunHistory({ items, error, selectedId, headingRef, onSelect, onRetry }: {
  items?: RunSummary[]
  error?: string
  selectedId?: number
  headingRef?: Ref<HTMLHeadingElement>
  onSelect: (item: RunSummary) => void
  onRetry: () => void
}) {
  return <aside className="panel history-panel" aria-labelledby="history-title">
    <div className="panel-title history-title"><History size={19} /><h2 id="history-title" ref={headingRef} tabIndex={-1}>最近运行</h2></div>
    {error && <div className="history-message"><p className="error" role="alert">运行历史加载失败。{error}</p><button type="button" onClick={onRetry}>重试加载历史</button></div>}
    {!error && !items && <p className="history-message" role="status">正在加载运行历史…</p>}
    {!error && items?.length === 0 && <p className="history-message">暂无运行记录</p>}
    {items && items.length > 0 && <ul>{items.map((item) => <li key={item.id}>
      <button type="button" aria-current={selectedId === item.id ? 'true' : undefined} onClick={() => onSelect(item)}>
        <strong title={item.topic}>{item.topic}</strong>
        <RunStatus status={item.status} />
        <small>#{item.id}<time dateTime={item.updated_at}>{new Date(item.updated_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</time></small>
      </button>
    </li>)}</ul>}
  </aside>
}
