import { ClipboardCheck, FileText } from 'lucide-react'
import type { Draft } from '../lib/api'

export function DraftPreview({ draft }: { draft?: Draft }) {
  if (!draft) {
    return (
      <section className="panel empty">
        <FileText size={20} />
        <span>运行工作流后生成推文候选</span>
      </section>
    )
  }

  const post = draft.quality_report?.post_revision as
    | { passed?: boolean; issues?: string[]; metrics?: Record<string, number> }
    | undefined
  const pre = draft.quality_report?.pre_revision as
    | { quality?: { issues?: string[] }; humanize?: { issues?: string[] } }
    | undefined

  return (
    <section className="panel draft-panel">
      <div className="panel-title">
        <FileText size={18} />
        <span>发布稿</span>
      </div>
      <div className="note-preview">
        <h2>{draft.title}</h2>
        <p>{draft.body}</p>
        <div className="tags">{draft.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
      </div>
      <div className="first-comment">
        <b>首评</b>
        <span>{draft.first_comment}</span>
      </div>
      <div className="qc-block">
        <div className={post?.passed ? 'qc-pass' : 'qc-warn'}>
          <ClipboardCheck size={16} />
          <span>{post?.passed ? '规则通过' : '需要复核'}</span>
        </div>
        <div className="metrics">
          <span>标题 {post?.metrics?.title_chars ?? draft.title.length}/20</span>
          <span>正文 {post?.metrics?.body_chars ?? draft.body.length}/400</span>
          <span>标签 {post?.metrics?.tag_count ?? draft.tags.length}</span>
        </div>
        <ul>
          {(post?.issues?.length ? post.issues : ['品牌名、标签、发现式植入和字数均已通过']).map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
          {pre?.quality?.issues?.map((issue) => <li key={issue}>修前：{issue}</li>)}
          {pre?.humanize?.issues?.map((issue) => <li key={issue}>去 AI 味：{issue}</li>)}
        </ul>
      </div>
    </section>
  )
}
