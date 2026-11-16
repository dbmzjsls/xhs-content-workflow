import { Image as ImageIcon, RotateCcw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, type ImageAsset } from '../lib/api'
import { referenceUsage } from './RunForm'

const historicalNotice = '下方保留原始生成记录，历史记录可能包含旧版能力描述；图片内容未作为模型输入。'
const assetKinds = new Map([['[internal path redacted]', '类型未显示']])
const assetStatuses = new Map([['mock', 'Mock 占位图'], ['generated', '已生成'], ['failed', '生成失败'], ['queued', '排队中'], ['pending', '待生成'], ['running', '生成中']])

function AssetImage({ path, alt, failed, thumbnail = false }: { path: string | null; alt: string; failed: boolean; thumbnail?: boolean }) {
  const [source, setSource] = useState<string>()
  const [loadError, setLoadError] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!path) return
    let objectUrl: string | undefined
    let canceled = false
    void api.blob(path).then((blob) => {
      if (canceled) return
      objectUrl = URL.createObjectURL(blob)
      setSource(objectUrl)
    }).catch(() => { if (!canceled) setLoadError(true) })
    return () => {
      canceled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [path, attempt])

  function reload() {
    setLoadError(false)
    setLoaded(false)
    setSource(undefined)
    setAttempt((value) => value + 1)
  }

  return <div className={thumbnail ? 'asset-thumb' : 'asset-preview'}>
    {source && !loadError && <img src={source} alt={thumbnail ? '' : alt} hidden={!loaded} onLoad={() => setLoaded(true)} onError={() => setLoadError(true)} />}
    {(!loaded || loadError || !path) && <div className="asset-placeholder">
      <ImageIcon size={thumbnail ? 19 : 28} aria-hidden="true" />
      {!thumbnail && <>
        <span role="status">{!path ? (failed ? '图片生成失败' : '暂无图片地址') : loadError ? '图片加载失败' : '正在加载图片…'}</span>
        {loadError && <button type="button" onClick={reload}><RotateCcw size={16} />重新加载图片</button>}
      </>}
    </div>}
  </div>
}

export function ImageAssets({ images, reviewing }: { images: ImageAsset[]; reviewing: boolean }) {
  const [activeId, setActiveId] = useState<number>()
  const activeIndex = images.findIndex((item) => item.id === activeId)
  const index = Math.max(0, activeIndex)
  const image = images[index]
  return <section className="panel image-panel">
    <div className="panel-title"><span className="icon-tile teal"><ImageIcon size={18} /></span><h3>{reviewing ? '素材审核' : '图片素材'}</h3></div>
    <div className="reference-notice"><p>{referenceUsage}</p><p>{historicalNotice}</p></div>
    {!image ? <p className="context-empty">暂无生成素材</p> : <>
      <article className="image-item" key={image.id}>
        <div className="asset-head"><span>素材 {index + 1} / {images.length} · {assetKinds.get(image.kind) ?? image.kind}</span><span className="pill">{assetStatuses.get(image.status) ?? image.status}</span></div>
        <h4>{image.title}</h4>
        <AssetImage key={image.url} path={image.url} alt={image.title} failed={image.status === 'failed'} />
        {image.reference_reason && <p>{image.reference_reason}</p>}
        <details><summary>Prompt 与提示词约束检查</summary><pre>{image.prompt}{'\n\n'}{JSON.stringify(image.qc_report, null, 2)}</pre></details>
      </article>
      <ul className="asset-strip" aria-label="素材列表">{images.map((item, position) => <li key={item.id}>
        <button type="button" aria-pressed={item.id === image.id} aria-label={`素材 ${position + 1} · ${item.title}`} onClick={() => setActiveId(item.id)}>
          <AssetImage key={item.url} path={item.url} alt="" failed={item.status === 'failed'} thumbnail />
          <span>{position + 1} · {assetKinds.get(item.kind) ?? item.kind}</span>
        </button>
      </li>)}</ul>
    </>}
  </section>
}
