import { Image, Lightbulb, Paperclip, PenLine, Sparkles } from 'lucide-react'
import { useEffect, useRef, type Ref } from 'react'
import type { RunCreate } from '../lib/api'

type Props = {
  headingRef?: Ref<HTMLHeadingElement>
  value: RunCreate
  file?: File
  busy: boolean
  creating: boolean
  error?: string
  onChange: (value: RunCreate) => void
  onFileChange: (file?: File) => void
  onSubmit: () => void
}

const styles = ['备忘录聊天框风', '拼贴风', '大字报纯文字风', '前后对比风', '真人出镜高颜值摄影风', '插画手绘风', '杂志风', '综艺花字风']
const imageTypes = ['image/png', 'image/jpeg', 'image/webp']

export const referenceUsage = '参考信息驱动的 prompt 重写：仅使用素材角色、标签和选择理由；不分析或向生成模型发送图片内容。上传图片仅供素材留档，生成结果不会自动参考其构图、颜色或 UI。'

export function RunForm({ headingRef, value, file, busy, creating, error, onChange, onFileChange, onSubmit }: Props) {
  const fileInput = useRef<HTMLInputElement>(null)
  useEffect(() => { if (!file && fileInput.current) fileInput.current.value = '' }, [file])
  const patch = (key: keyof RunCreate, next: string) => onChange({ ...value, [key]: next })
  const fileError = file && (file.size > 10 * 1024 * 1024 ? '参考素材不能超过 10 MB。' :
    file.type && !imageTypes.includes(file.type) ? '请选择 PNG、JPEG 或 WebP 图片。' : undefined)

  return <section className="panel input-panel" aria-labelledby="create-title">
    <div className="create-intro">
      <span className="icon-tile purple"><Sparkles size={23} /></span>
      <h2 id="create-title" ref={headingRef} tabIndex={-1}>开始一篇新内容</h2>
      <p>填写主题与受众，生成候选文案并逐步审核。</p>
    </div>
    <form onSubmit={(event) => { event.preventDefault(); if (!fileError && value.topic.trim()) onSubmit() }}>
      <fieldset disabled={creating}>
        <legend><span className="icon-tile purple"><Lightbulb size={18} /></span>内容方向</legend>
        <div className="form-fields">
          <label className="full-field"><span>主题</span><input required data-testid="brief-topic" value={value.topic} placeholder="例如：睡前 20 分钟改作文" onChange={(event) => patch('topic', event.target.value)} /></label>
          <label className="full-field"><span>目标人群</span><input data-testid="brief-audience" value={value.audience} placeholder="例如：雅思 5.5–6.5 自学考生" onChange={(event) => patch('audience', event.target.value)} /></label>
        </div>
      </fieldset>
      <fieldset disabled={creating}>
        <legend><span className="icon-tile blue"><PenLine size={18} /></span>表达重点</legend>
        <div className="form-fields">
          <label className="full-field"><span>产品功能</span><input data-testid="brief-product" value={value.product_function} placeholder="例如：Writing Checker" onChange={(event) => patch('product_function', event.target.value)} /></label>
          <label className="full-field"><span>痛点场景</span><textarea rows={2} data-testid="brief-pain-point" value={value.pain_point} placeholder="例如：作文改了很多遍，还是不知道卡在哪个评分维度" onChange={(event) => patch('pain_point', event.target.value)} /></label>
        </div>
      </fieldset>
      <fieldset disabled={creating}>
        <legend><span className="icon-tile teal"><Image size={18} /></span>视觉偏好</legend>
        <div className="form-fields">
          <label><span>图片风格</span><select data-testid="brief-style" value={value.style_preference ?? styles[0]} onChange={(event) => patch('style_preference', event.target.value)}>{styles.map((style) => <option key={style}>{style}</option>)}</select></label>
          <div className="file-field">
            <label htmlFor="brief-upload"><span>参考素材留档（可选）</span><input ref={fileInput} id="brief-upload" data-testid="brief-upload" type="file" accept={imageTypes.join(',')} aria-invalid={Boolean(fileError)} aria-describedby={fileError ? 'brief-upload-help brief-upload-error' : 'brief-upload-help'} onChange={(event) => onFileChange(event.target.files?.[0])} /></label>
            {file && <small className="file-name"><Paperclip size={14} />{file.name}</small>}
            {fileError && <p id="brief-upload-error" className="error" role="alert">{fileError}</p>}
            <small>PNG、JPEG 或 WebP，最大 10 MB</small>
            <p id="brief-upload-help">{referenceUsage}</p>
          </div>
        </div>
      </fieldset>
      <div className="form-footer">
        {error && <p className="error" role="alert">创建失败。{error}</p>}
        <button data-testid="create-run" className="primary" type="submit" disabled={busy || Boolean(fileError) || !value.topic.trim()}><Sparkles size={17} />{creating ? '正在创建…' : '生成候选文案'}</button>
      </div>
    </form>
  </section>
}
