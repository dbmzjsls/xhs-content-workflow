import { Paperclip, Sparkles } from 'lucide-react'
import type { RunCreate } from '../lib/api'

type Props = {
  value: RunCreate
  file?: File
  busy: boolean
  onChange: (value: RunCreate) => void
  onFileChange: (file?: File) => void
  onSubmit: () => void
}

const styles = ['备忘录聊天框风', '拼贴风', '大字报纯文字风', '前后对比风', '真人出镜高颜值摄影风', '插画手绘风', '杂志风', '综艺花字风']

export function RunForm({ value, file, busy, onChange, onFileChange, onSubmit }: Props) {
  const patch = (key: keyof RunCreate, next: string) => onChange({ ...value, [key]: next })
  return <section className="panel input-panel">
    <div className="panel-title"><Sparkles size={18} /><span>内容 Brief</span></div>
    <label><span>主题</span><input value={value.topic} onChange={(event) => patch('topic', event.target.value)} /></label>
    <label><span>目标人群</span><input value={value.audience} onChange={(event) => patch('audience', event.target.value)} /></label>
    <label><span>产品功能</span><input value={value.product_function} onChange={(event) => patch('product_function', event.target.value)} /></label>
    <label><span>痛点场景</span><textarea value={value.pain_point} onChange={(event) => patch('pain_point', event.target.value)} /></label>
    <label><span>风格路由</span><select value={value.style_preference ?? styles[0]} onChange={(event) => patch('style_preference', event.target.value)}>{styles.map((style) => <option key={style}>{style}</option>)}</select></label>
    <label className="file-field"><span>参考图（可选）</span><input type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => onFileChange(event.target.files?.[0])} />{file && <small><Paperclip size={13} />{file.name}</small>}</label>
    <button className="primary" type="button" onClick={onSubmit} disabled={busy || !value.topic.trim()}><Sparkles size={17} />{busy ? '正在创建…' : '运行工作流'}</button>
  </section>
}
