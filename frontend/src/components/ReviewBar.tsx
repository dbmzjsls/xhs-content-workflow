import { Download, RotateCcw, Send } from 'lucide-react'
import { useState } from 'react'
import { api, type Run } from '../lib/api'

export function ReviewBar({
  run,
  onRefresh,
}: {
  run?: Run
  onRefresh: (id: number) => Promise<void>
}) {
  const [instructions, setInstructions] = useState('再弱化一点产品感，结尾更像真实记录')
  const [busy, setBusy] = useState(false)
  if (!run) return null

  const approve = async () => {
    setBusy(true)
    try {
      await api.approve(run.id)
      await onRefresh(run.id)
    } finally {
      setBusy(false)
    }
  }

  const revise = async () => {
    setBusy(true)
    try {
      await api.revise(run.id, instructions)
      await onRefresh(run.id)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="review-bar">
      <div>
        <b>人工审核</b>
        <span>{run.status === 'completed' ? '发布包已导出' : '等待审核通过或返修'}</span>
      </div>
      <input value={instructions} onChange={(event) => setInstructions(event.target.value)} />
      <button type="button" onClick={revise} disabled={busy || run.status === 'completed'}>
        <RotateCcw size={16} />
        返修
      </button>
      <button type="button" className="primary" onClick={approve} disabled={busy}>
        <Send size={16} />
        审核通过
      </button>
      <a className={`download ${run.final_package ? '' : 'disabled'}`} href={api.exportUrl(run.id)}>
        <Download size={16} />
        导出
      </a>
    </section>
  )
}
