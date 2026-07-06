import { Image as ImageIcon } from 'lucide-react'
import { assetUrl, type ImageAsset } from '../lib/api'

export function ImageAssets({ images }: { images: ImageAsset[] }) {
  return (
    <section className="panel image-panel">
      <div className="panel-title">
        <ImageIcon size={18} />
        <span>图片工作流</span>
      </div>
      {!images.length && <div className="empty-line">等待图片任务分类、参考图选择和 prompt 改写</div>}
      <div className="image-grid">
        {images.map((image) => {
          const url = assetUrl(image.file_path)
          return (
            <article className="image-item" key={`${image.kind}-${image.title}`}>
              {url ? <img src={url} alt={image.title} /> : <div className="asset-placeholder">{image.kind}</div>}
              <div>
                <div className="asset-head">
                  <b>{image.kind}</b>
                  <span>{image.status}</span>
                </div>
                <h3>{image.title}</h3>
                <p>{image.reference_reason}</p>
                <details>
                  <summary>Prompt</summary>
                  <pre>{image.prompt}</pre>
                </details>
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
