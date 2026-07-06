import { Sparkles, Workflow } from 'lucide-react'
import type { RunCreate } from '../lib/api'

type Props = {
  value: RunCreate
  busy: boolean
  onChange: (value: RunCreate) => void
  onSubmit: () => void
}

const styles = [
  '备忘录聊天框风',
  '拼贴风',
  '大字报纯文字风',
  '前后对比风',
  '真人出镜高颜值摄影风',
  '插画手绘风',
  '杂志风',
  '综艺花字风',
]

export function RunForm({ value, busy, onChange, onSubmit }: Props) {
  const patch = (key: keyof RunCreate, next: string) => onChange({ ...value, [key]: next })

  return (
    <section className="panel input-panel">
      <div className="panel-title">
        <Workflow size={18} />
        <span>内容 Brief</span>
      </div>
      <label>
        <span>主题</span>
        <input value={value.topic} onChange={(event) => patch('topic', event.target.value)} />
      </label>
      <label>
        <span>目标人群</span>
        <input value={value.audience} onChange={(event) => patch('audience', event.target.value)} />
      </label>
      <label>
        <span>产品功能</span>
        <input
          value={value.product_function}
          onChange={(event) => patch('product_function', event.target.value)}
        />
      </label>
      <label>
        <span>痛点场景</span>
        <textarea value={value.pain_point} onChange={(event) => patch('pain_point', event.target.value)} />
      </label>
      <label>
        <span>风格路由</span>
        <select
          value={value.style_preference ?? '备忘录聊天框风'}
          onChange={(event) => patch('style_preference', event.target.value)}
        >
          {styles.map((style) => (
            <option key={style} value={style}>
              {style}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>参考图路径</span>
        <input
          value={value.reference_path ?? ''}
          onChange={(event) => patch('reference_path', event.target.value)}
          placeholder="可选：本地参考图路径"
        />
      </label>
      <button className="primary" type="button" onClick={onSubmit} disabled={busy}>
        <Sparkles size={17} />
        {busy ? '生成中' : '运行工作流'}
      </button>
    </section>
  )
}
