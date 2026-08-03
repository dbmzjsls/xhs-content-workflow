import { Image as ImageIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, type ImageAsset } from '../lib/api'

function AuthenticatedImage({ path, alt, fallback }: { path: string; alt: string; fallback: string }) {
  const [source, setSource] = useState<string>()

  useEffect(() => {
    let objectUrl: string | undefined
    let cancelled = false
    void api.blob(path).then((blob) => {
      if (cancelled) return
      objectUrl = URL.createObjectURL(blob)
      setSource(objectUrl)
    }).catch(() => undefined)
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [path])

  return source ? <img src={source} alt={alt} /> : <div className="asset-placeholder">{fallback}</div>
}

export function ImageAssets({ images }: { images: ImageAsset[] }) {
  return <section className="panel image-panel"><div className="panel-title"><ImageIcon size={18} /><span>图片工作流 · 资产审核</span></div>
    {!images.length && <div className="empty-line">文案审核完成后，系统会生成图片任务与质检结果。</div>}
    <div className="image-grid">{images.map((image) => <article className="image-item" key={image.id}>
      {image.url ? <AuthenticatedImage path={image.url} alt={image.title} fallback={image.kind} /> : <div className="asset-placeholder">{image.kind}</div>}
      <div><div className="asset-head"><b>{image.kind}</b><span>{image.status}</span></div><h3>{image.title}</h3><p>{image.reference_reason}</p><details><summary>Prompt 与质检</summary><pre>{image.prompt}{'\n\n'}{JSON.stringify(image.qc_report, null, 2)}</pre></details></div>
    </article>)}</div>
  </section>
}
