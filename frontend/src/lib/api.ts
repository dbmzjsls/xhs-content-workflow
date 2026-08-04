const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8090'
const API_TOKEN = import.meta.env.VITE_API_TOKEN?.trim()

export type Step = {
  name: string
  status: string
  output_payload: Record<string, unknown>
  created_at: string
  attempt: number
  started_at: string | null
  heartbeat_at: string | null
  completed_at: string | null
  duration_ms: number | null
  error: string | null
  error_type: string | null
}

export type Draft = {
  id: number
  title: string
  body: string
  tags: string[]
  first_comment: string | null
  narrative_plan: Record<string, unknown>
  quality_report: Record<string, unknown>
  is_final: boolean
  selected: boolean
  candidate: number
  parent_draft_id: number | null
}

export type ImageAsset = {
  id: number
  kind: string
  status: string
  title: string
  prompt: string
  reference_reason: string
  url: string | null
  qc_report: Record<string, unknown>
}

export type Run = {
  id: number
  status: string
  current_step: string
  topic: string
  audience: string
  product_function: string
  pain_point: string
  style_preference: string | null
  brief: Record<string, unknown>
  final_package: Record<string, string> | null
  error: string | null
  created_at: string
  updated_at: string
  steps: Step[]
  drafts: Draft[]
  images: ImageAsset[]
}

export type RunSummary = Pick<Run, 'id' | 'status' | 'current_step' | 'topic' | 'error' | 'created_at' | 'updated_at'>

export type RunCreate = {
  topic: string
  audience: string
  product_function: string
  pain_point: string
  style_preference?: string
  upload_asset_ids?: number[]
}

export type Upload = { id: number; mime_type: string; size_bytes: number; url: string }

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

async function errorMessage(response: Response): Promise<string> {
  const fallback = `请求失败（${response.status}）`
  const raw = await response.text()
  if (!raw) return fallback
  try {
    const body: unknown = JSON.parse(raw)
    if (typeof body === 'object' && body && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail
      return typeof detail === 'string' ? detail : JSON.stringify(detail)
    }
    return JSON.stringify(body)
  } catch { return raw }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await requestResponse(path, options)
  return response.json() as Promise<T>
}

async function requestResponse(path: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers)
  if (API_TOKEN && !headers.has('authorization')) {
    headers.set('authorization', `Bearer ${API_TOKEN}`)
  }
  if (options.body && !(options.body instanceof FormData) && !headers.has('content-type')) {
    headers.set('content-type', 'application/json')
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status)
  return response
}

function responseFilename(response: Response): string | undefined {
  const disposition = response.headers.get('content-disposition')
  if (!disposition) return undefined
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1]
  if (encoded) return decodeURIComponent(encoded)
  return /filename="?([^";]+)"?/i.exec(disposition)?.[1]
}

const idempotencyHeaders = () => ({ 'Idempotency-Key': crypto.randomUUID() })

export const api = {
  createRun: (body: RunCreate) => request<Run>('/api/runs', { method: 'POST', body: JSON.stringify(body) }),
  listRuns: () => request<{ items: RunSummary[] }>('/api/runs?limit=50'),
  getRun: (id: number) => request<Run>(`/api/runs/${id}`),
  upload: (file: File) => {
    const body = new FormData()
    body.append('file', file)
    return request<Upload>('/api/uploads', { method: 'POST', body })
  },
  selectDraft: (id: number, draftId: number) =>
    request<{ status: string }>(`/api/runs/${id}/selection`, { method: 'POST', headers: idempotencyHeaders(), body: JSON.stringify({ draft_id: draftId }) }),
  revise: (id: number, instructions: string) =>
    request<{ status: string }>(`/api/runs/${id}/revisions`, { method: 'POST', headers: idempotencyHeaders(), body: JSON.stringify({ instructions }) }),
  approveCopy: (id: number) => request<{ status: string }>(`/api/runs/${id}/copy-approval`, { method: 'POST', headers: idempotencyHeaders() }),
  approveAssets: (id: number) => request<{ status: string }>(`/api/runs/${id}/asset-approval`, { method: 'POST', headers: idempotencyHeaders() }),
  retry: (id: number) => request<{ status: string }>(`/api/runs/${id}/retry`, { method: 'POST', headers: idempotencyHeaders() }),
  cancel: (id: number) => request<{ status: string }>(`/api/runs/${id}/cancel`, { method: 'POST', headers: idempotencyHeaders() }),
  blob: async (path: string) => (await requestResponse(path)).blob(),
  download: async (path: string) => {
    const response = await requestResponse(path)
    return { blob: await response.blob(), filename: responseFilename(response) }
  },
}
