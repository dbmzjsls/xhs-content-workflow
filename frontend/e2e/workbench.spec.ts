import { expect, test } from '@playwright/test'

const API_BASE = 'http://127.0.0.1:8090'
const API_TOKEN = 'e2e-api-token'
const REFERENCE_USAGE = '参考信息驱动的 prompt 重写：仅使用素材角色、标签和选择理由；不分析或向生成模型发送图片内容。上传图片仅供素材留档，生成结果不会自动参考其构图、颜色或 UI。'
const HISTORICAL_NOTICE = '下方保留原始生成记录，历史记录可能包含旧版能力描述；图片内容未作为模型输入。'
const ABSOLUTE_FILESYSTEM_PATH = /(?:^|["'\s(])(?:[A-Za-z]:\\{1,2}|\/(?:Users|home|tmp|srv)\/)/

test('absolute path matcher ignores prompt labels and detects filesystem paths', () => {
  expect('Primary request:\\nCreate a cover').not.toMatch(ABSOLUTE_FILESYSTEM_PATH)
  expect('C:\\Users\\runner\\reference.png').toMatch(ABSOLUTE_FILESYSTEM_PATH)
  expect(JSON.stringify({ path: 'C:\\Users\\runner\\reference.png' })).toMatch(ABSOLUTE_FILESYSTEM_PATH)
  expect('/tmp/xhs-workbench/reference.png').toMatch(ABSOLUTE_FILESYSTEM_PATH)
})

for (const withUpload of [true, false]) {
  test(`complete mock workflow ${withUpload ? 'with upload' : 'without reference'} through export`, async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.file-field')).toContainText('参考素材留档（可选）')
    await expect(page.locator('.file-field').getByText(REFERENCE_USAGE, { exact: true })).toBeVisible()
    await page.getByTestId('brief-topic').fill('Playwright commuting writing check')
    await page.getByTestId('brief-audience').fill('IELTS self-study commuters')
    await page.getByTestId('brief-product').fill('Writing Checker')
    await page.getByTestId('brief-pain-point').fill('My examples do not support the point')
    if (withUpload) await page.getByTestId('brief-upload').setInputFiles({
      name: 'reference.png',
      mimeType: 'image/png',
      buffer: Buffer.concat([
        Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
        Buffer.from('playwright'),
      ]),
    })

    const [createdResponse] = await Promise.all([
      page.waitForResponse(
        (response) => response.url() === `${API_BASE}/api/runs` && response.request().method() === 'POST',
      ),
      page.getByTestId('create-run').click(),
    ])
    expect(createdResponse.status()).toBe(202)
    const created = (await createdResponse.json()) as { id: number; status: string }
    expect(created.status).toBe('queued')

    await expect(page.getByTestId('approve-copy')).toBeVisible({ timeout: 30_000 })
    await expect(page.locator('.file-field').getByText(REFERENCE_USAGE, { exact: true })).toBeVisible()
    await expect(page.locator('.candidate-tabs button')).toHaveCount(3)
    await page.getByTestId('candidate-tab-1').click()
    const firstTitle = await page.locator('.note-preview h2').textContent()
    await page.getByTestId('candidate-tab-2').click()
    const secondTitle = await page.locator('.note-preview h2').textContent()
    expect(secondTitle).not.toBe(firstTitle)

    await page.getByTestId('candidate-tab-1').click()
    const [selectionResponse] = await Promise.all([
      page.waitForResponse((response) => response.url().endsWith(`/api/runs/${created.id}/selection`)),
      page.getByTestId('select-candidate').click(),
    ])
    expect(selectionResponse.ok()).toBeTruthy()

    await page.getByTestId('revision-instructions').fill('Make it conversational and less product-led')
    const [revisionResponse] = await Promise.all([
      page.waitForResponse((response) => response.url().endsWith(`/api/runs/${created.id}/revisions`)),
      page.getByTestId('revise-draft').click(),
    ])
    expect(revisionResponse.ok()).toBeTruthy()
    await expect
      .poll(async () => {
        const response = await page.request.get(`${API_BASE}/api/runs/${created.id}`, {
          headers: { authorization: `Bearer ${API_TOKEN}` },
        })
        const detail = (await response.json()) as {
          drafts: Array<{ selected: boolean; parent_draft_id: number | null }>
        }
        return detail.drafts.some((draft) => draft.selected && draft.parent_draft_id !== null)
      })
      .toBe(true)

    const revisionTab = page.locator('[data-testid^="revision-tab-"]').first()
    await expect(revisionTab).toBeVisible()
    await expect(revisionTab).toHaveClass(/active/)
    await page.getByTestId('candidate-tab-2').click()
    await expect(page.getByTestId('revise-draft')).toBeDisabled()
    await expect(page.getByTestId('approve-copy')).toBeDisabled()
    await revisionTab.click()
    await expect(page.getByTestId('revise-draft')).toBeEnabled()
    await expect(page.getByTestId('approve-copy')).toBeEnabled()

    await page.getByTestId('approve-copy').click()
    await expect(page.getByTestId('approve-assets')).toBeVisible({ timeout: 30_000 })
    await expect(page.locator('.image-item').first()).toBeVisible()
    await expect(page.locator('.image-panel').getByText(REFERENCE_USAGE, { exact: true })).toBeVisible()
    await expect(page.locator('.image-panel').getByText(HISTORICAL_NOTICE, { exact: true })).toBeVisible()
    await expect(page.locator('.image-item summary').first()).toHaveText('Prompt 与提示词约束检查')

    await page.getByTestId('approve-assets').click()
    await expect(page.getByTestId('export-download')).not.toHaveClass(/disabled/)
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByTestId('export-download').click(),
    ])
    expect(download.suggestedFilename()).toMatch(/\.zip$/)
    const headers = { authorization: `Bearer ${API_TOKEN}` }
    const detailResponse = await page.request.get(`${API_BASE}/api/runs/${created.id}`, { headers })
    const detail = await detailResponse.json() as { status: string; final_package: { markdown_url: string; json_url: string } }
    expect(detail.status).toBe('completed')
    const markdown = await (await page.request.get(`${API_BASE}${detail.final_package.markdown_url}`, { headers })).text()
    const packageJson = await (await page.request.get(`${API_BASE}${detail.final_package.json_url}`, { headers })).text()
    expect(markdown).toContain('## 参考素材信息')
    expect(markdown).toContain(REFERENCE_USAGE)
    expect(markdown).toContain(HISTORICAL_NOTICE)
    expect(JSON.parse(packageJson).reference_usage).toBe(REFERENCE_USAGE)
    for (const content of [JSON.stringify(detail), markdown, packageJson]) {
      expect(content).not.toMatch(ABSOLUTE_FILESYSTEM_PATH)
    }
    await expect(page.locator('.image-panel').getByText(REFERENCE_USAGE, { exact: true })).toBeVisible()
  })
}

test('historical audit keeps its capability notice through an empty failed panel and retry', async ({ page }) => {
  const historicalReason = '旧版记录：参考上传图片的构图、颜色和 UI。'
  const historicalPrompt = '旧版 Prompt：Use the uploaded reference image composition.'
  let resumed = false
  const historicalRun = {
    id: 9001, status: 'failed', current_step: 'image_generation',
    topic: 'Historical reference retry', audience: 'IELTS students',
    product_function: 'Writing Checker', pain_point: 'Unclear feedback',
    style_preference: '备忘录聊天框风', brief: {}, final_package: null,
    error: 'image provider failed', created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z', steps: [], drafts: [], images: [],
  }
  await page.route(/\/api\/runs(?:\/.*)?(?:\?.*)?$/, async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/runs') {
      await route.fulfill({ json: { items: [historicalRun] } })
    } else if (path === '/api/runs/9001/retry') {
      resumed = true
      await route.fulfill({ json: { status: 'image_queued' } })
    } else if (path === '/api/runs/9001') {
      await route.fulfill({ json: resumed ? {
        ...historicalRun, status: 'asset_review_required', current_step: 'asset_review', error: null,
        images: [{ id: 1, kind: '封面图', status: 'generated', title: 'Historical cover',
          prompt: historicalPrompt, reference_reason: historicalReason, url: null,
          qc_report: { passed: true, checks: ['旧版质检记录'] } }],
      } : historicalRun })
    } else {
      await route.continue()
    }
  })
  await page.goto('/')
  await page.locator('.history-panel button').filter({ hasText: 'Historical reference retry' }).click()
  const panel = page.locator('.image-panel')
  await expect(panel.locator('.image-item')).toHaveCount(0)
  await expect(panel.getByText(REFERENCE_USAGE, { exact: true })).toBeVisible()
  await expect(panel.getByText(HISTORICAL_NOTICE, { exact: true })).toBeVisible()
  await page.getByTestId('retry-run').click()
  await expect(page.getByTestId('approve-assets')).toBeVisible()
  await expect(panel.getByText(REFERENCE_USAGE, { exact: true })).toBeVisible()
  await expect(panel.getByText(HISTORICAL_NOTICE, { exact: true })).toBeVisible()
  await expect(panel.locator('.image-item p')).toHaveText(historicalReason)
  await panel.getByText('Prompt 与提示词约束检查', { exact: true }).click()
  await expect(panel.locator('pre')).toHaveText(`${historicalPrompt}\n\n${JSON.stringify({ passed: true, checks: ['旧版质检记录'] }, null, 2)}`)
})
