const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8090'
const API_TOKEN = import.meta.env.VITE_API_TOKEN as string | undefined

export type Step = {
  name: string
  status: string
  output_payload: Record<string, unknown>
  created_at: string
}

export type Draft = {
  title: string
  body: string
  tags: string[]
  first_comment: string | null
  narrative_plan: Record<string, unknown>
  quality_report: Record<string, unknown>
  is_final: boolean
}

export type ImageAsset = {
  kind: string
  status: string
  title: string
  prompt: string
  reference_reason: string
  file_path: string | null
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

export type RunCreate = {
  topic: string
  audience: string
  product_function: string
  pain_point: string
  style_preference?: string
  reference_path?: string
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('content-type')) {
    headers.set('content-type', 'application/json')
  }
  if (API_TOKEN) {
    headers.set('authorization', `Bearer ${API_TOKEN}`)
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json() as Promise<T>
}

export const api = {
  createRun: (body: RunCreate) =>
    request<Run>('/api/runs', { method: 'POST', body: JSON.stringify(body) }),
  getRun: (id: number) => request<Run>(`/api/runs/${id}`),
  approve: (id: number) =>
    request<{ ok: boolean; result: Record<string, string> }>(`/api/runs/${id}/review`, {
      method: 'POST',
      body: JSON.stringify({ action: 'approve' }),
    }),
  revise: (id: number, instructions: string) =>
    request<{ ok: boolean }>(`/api/runs/${id}/review`, {
      method: 'POST',
      body: JSON.stringify({ action: 'revise', instructions }),
    }),
  exportUrl: (id: number) => `${API_BASE}/api/runs/${id}/export`,
}

export function assetUrl(filePath: string | null): string | null {
  if (!filePath) return null
  const normalized = filePath.replaceAll('\\', '/')
  const marker = '/exports/'
  const idx = normalized.lastIndexOf(marker)
  if (idx < 0) return null
  return `${API_BASE}/exports/${normalized.slice(idx + marker.length)}`
}
