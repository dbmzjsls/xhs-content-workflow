import { Image as ImageIcon } from 'lucide-react'
import { api, type ImageAsset } from '../lib/api'

export function ImageAssets({ images }: { images: ImageAsset[] }) {
  return <section className="panel image-panel"><div className="panel-title"><ImageIcon size={18} /><span>图片工作流 · 资产审核</span></div>
    {!images.length && <div className="empty-line">文案审核完成后，系统会生成图片任务与质检结果。</div>}
    <div className="image-grid">{images.map((image) => <article className="image-item" key={image.id}>
      {image.url ? <img src={api.url(image.url)} alt={image.title} /> : <div className="asset-placeholder">{image.kind}</div>}
      <div><div className="asset-head"><b>{image.kind}</b><span>{image.status}</span></div><h3>{image.title}</h3><p>{image.reference_reason}</p><details><summary>Prompt 与质检</summary><pre>{image.prompt}{'\n\n'}{JSON.stringify(image.qc_report, null, 2)}</pre></details></div>
    </article>)}</div>
  </section>
}
