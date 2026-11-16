import { expect, test, type Page } from '@playwright/test'

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
  test(`complete mock workflow ${withUpload ? 'with upload' : 'without reference'} through export`, async ({ page }, testInfo) => {
    if (withUpload) await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/')
    await expect(page.locator('.file-field')).toContainText('参考素材留档（可选）')
    await expect(page.locator('.file-field').getByText(REFERENCE_USAGE, { exact: true })).toBeVisible()
    await expect(page.locator('label[for="brief-upload"]')).not.toContainText(REFERENCE_USAGE)
    await expect(page.getByTestId('brief-upload')).toHaveAttribute('aria-describedby', 'brief-upload-help')
    await page.getByTestId('brief-topic').fill('Playwright commuting writing check')
    await page.getByTestId('brief-audience').fill('IELTS self-study commuters')
    await page.getByTestId('brief-product').fill('Writing Checker')
    await page.getByTestId('brief-pain-point').fill('My examples do not support the point')
    if (withUpload) await page.screenshot({ path: testInfo.outputPath('brief-create.png'), fullPage: true })
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
    await page.getByText('Brief 摘要', { exact: true }).click()
    await expect(page.locator('.brief-summary').getByText(REFERENCE_USAGE, { exact: true })).toBeVisible()
    await page.getByText('Brief 摘要', { exact: true }).click()
    await expect(page.locator('.candidate-tabs button')).toHaveCount(3)
    await page.getByTestId('candidate-tab-1').click()
    if (withUpload) await page.screenshot({ path: testInfo.outputPath('candidate-comparison.png'), fullPage: true })
    const firstTitle = await page.locator('.note-preview h2').textContent()
    await page.getByTestId('candidate-tab-1').press('ArrowRight')
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
    if (withUpload) {
      await page.getByTestId('approve-copy').scrollIntoViewIfNeeded()
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
      await page.screenshot({ path: testInfo.outputPath('copy-review-revision.png'), fullPage: true })
    }
    await page.getByTestId('candidate-tab-2').click()
    await expect(page.getByText('当前查看内容尚未选中。请先选择此方案。')).toBeVisible()
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
    const records = page.locator('details').filter({ has: page.getByText(/^执行记录/) })
    await records.locator('summary').click()
    await expect(records.getByText('提示词约束检查', { exact: true })).toBeVisible()
    await records.locator('summary').click()

    await expect(page.locator('.asset-preview img')).toBeVisible()
    if (withUpload) await page.screenshot({ path: testInfo.outputPath('asset-review.png'), fullPage: true })
    await page.getByTestId('approve-assets').click()
    await expect(page.getByTestId('export-download')).toBeEnabled()
    if (withUpload) {
      await expect(page.locator('.asset-preview img')).toBeVisible()
      await page.screenshot({ path: testInfo.outputPath('publication-package.png'), fullPage: true })
    }
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

const runFixture = {
  id: 9010, status: 'copy_review_required', current_step: 'copy_review',
  topic: '通勤路上怎么练习雅思写作', audience: '雅思自学考生', product_function: 'Writing Checker',
  pain_point: '例子和论点总是对不上', style_preference: '备忘录聊天框风', brief: {},
  error: null, final_package: null, updated_at: '2026-10-01T00:00:00Z', created_at: '2026-10-01T00:00:00Z',
  steps: [], images: [],
  drafts: [{ id: 1, candidate: 1, title: '我终于知道例子为什么写跑了', body: '我在地铁上重新读了一遍作文。\n\n原来我写的例子只讲了发生了什么，却没说清它怎么支持我的观点。',
    tags: ['#雅思写作'], first_comment: '你会怎么改这个例子？', narrative_plan: { angle: '通勤复盘' },
    quality_report: { hard: { passed: true }, soft: { total: 88 } }, selected: true, is_final: false, parent_draft_id: null }],
}

function deferred() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => { release = resolve })
  return { promise, release }
}

async function expectNoOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width)
}

test('history and detail report errors, and out-of-order detail responses cannot change the review target', async ({ page }) => {
  const slow = deferred()
  const requested = deferred()
  const runB = { ...runFixture, id: 9011, topic: '另一篇通勤笔记' }
  let historyFailed = true
  let detailRequests = 0
  let approvedPath: string | undefined
  await page.route(/\/api\/runs(?:\/.*)?(?:\?.*)?$/, async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/runs') {
      if (historyFailed) return route.fulfill({ status: 503, json: { detail: '暂时无法读取' } })
      return route.fulfill({ json: { items: [runFixture, runB] } })
    }
    if (path === '/api/runs/9010') {
      requested.release()
      await slow.promise
      return route.fulfill({ json: runFixture })
    }
    if (path === '/api/runs/9011/copy-approval') {
      approvedPath = path
      return route.fulfill({ json: { status: 'asset_review_required' } })
    }
    if (++detailRequests === 1) return route.fulfill({ status: 503, json: { detail: '详情暂时不可用' } })
    return route.fulfill({ json: approvedPath ? { ...runB, status: 'asset_review_required' } : runB })
  })
  await page.goto('/')
  await expect(page.getByRole('alert')).toContainText('运行历史加载失败')
  await expect(page.getByText('暂无运行记录')).toHaveCount(0)
  historyFailed = false
  await page.getByRole('button', { name: '重试加载历史' }).click()
  await page.getByTestId('brief-topic').fill('保留未提交的主题')
  await page.locator('.history-panel button').filter({ hasText: runFixture.topic }).click()
  await requested.promise
  await expect(page.getByText('正在加载任务…')).toBeVisible()
  await expect(page.getByTestId('approve-copy')).toHaveCount(0)
  await page.locator('.history-panel button').filter({ hasText: runB.topic }).click()
  await expect(page.getByRole('alert')).toContainText('任务加载失败')
  await page.getByRole('button', { name: '重新加载任务' }).click()
  await expect(page.getByRole('heading', { name: runB.topic })).toBeVisible()
  await expect(page.getByTestId('approve-copy')).toBeEnabled()
  const responded = page.waitForResponse((response) => response.url().endsWith('/9010'))
  slow.release()
  await responded
  await page.getByTestId('approve-copy').click()
  await expect(page.getByTestId('approve-assets')).toBeVisible()
  expect(approvedPath).toBe('/api/runs/9011/copy-approval')
  await page.getByRole('button', { name: '新建内容' }).click()
  await expect(page.getByTestId('brief-topic')).toHaveValue('保留未提交的主题')
})

test('in-flight polling leaves the create view intact and double submit sends one request', async ({ page }) => {
  const poll = deferred()
  const polling = deferred()
  const create = deferred()
  const created = deferred()
  const running = { ...runFixture, status: 'running', current_step: 'text_generation', drafts: [] }
  let reads = 0
  let creates = 0
  await page.route(/\/api\/runs(?:\/.*)?(?:\?.*)?$/, async (route) => {
    const path = new URL(route.request().url()).pathname
    if (route.request().method() === 'POST') {
      creates++
      created.release()
      await create.promise
      return route.fulfill({ status: 202, json: { ...running, id: 9012, status: 'canceled' } })
    }
    if (path === '/api/runs') return route.fulfill({ json: { items: [running] } })
    if (++reads === 1) return route.fulfill({ json: running })
    polling.release()
    await poll.promise
    return route.fulfill({ json: runFixture })
  })
  await page.goto('/')
  await page.locator('.history-panel button').filter({ hasText: running.topic }).click()
  await expect(page.getByRole('button', { name: '取消运行' })).toBeVisible()
  await polling.promise
  await page.getByRole('button', { name: '新建内容' }).click()
  await page.getByTestId('brief-topic').fill('新的内容')
  const response = page.waitForResponse((item) => item.url().endsWith('/9010'))
  poll.release()
  await response
  await expect(page.getByTestId('brief-topic')).toBeVisible()
  await expect(page.getByTestId('approve-copy')).toHaveCount(0)
  await page.getByTestId('create-run').dblclick()
  await created.promise
  await expect(page.getByTestId('create-run')).toBeDisabled()
  create.release()
  await expect(page.getByText('任务 #9012')).toBeVisible()
  expect(creates).toBe(1)
})

test('downloads report errors, support retry, and reset when changing tasks', async ({ page }) => {
  const complete = { ...runFixture, status: 'completed', final_package: { zip_url: '/api/test-download' } }
  const unavailable = { ...complete, id: 9011, topic: '没有下载地址', final_package: null }
  let attempts = 0
  await page.route(/\/api\/runs(?:\/.*)?(?:\?.*)?$/, (route) => {
    const path = new URL(route.request().url()).pathname
    return route.fulfill({ json: path === '/api/runs' ? { items: [complete, unavailable] } : path.endsWith('/9010') ? complete : unavailable })
  })
  await page.route('**/api/test-download', (route) => ++attempts === 1
    ? route.fulfill({ status: 503, json: { detail: '文件暂不可用' } })
    : route.fulfill({ body: 'mock archive', contentType: 'application/zip' }))
  await page.goto('/')
  await page.locator('.history-panel button').filter({ hasText: complete.topic }).click()
  await page.getByTestId('export-download').click()
  await expect(page.getByRole('alert')).toContainText('下载失败')
  const download = page.waitForEvent('download')
  await page.getByTestId('export-download').click()
  expect((await download).suggestedFilename()).toBe('run-9010.zip')
  await page.locator('.history-panel button').filter({ hasText: unavailable.topic }).click()
  await expect(page.getByTestId('export-download')).toBeDisabled()
  await expect(page.getByText('该任务暂无可用的发布包下载地址。')).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('asset preview distinguishes loading, display errors, and generation failures', async ({ page }) => {
  const image = { id: 1, kind: '封面图', status: 'generated', title: '第一张图', url: '/api/test-image', prompt: '封面提示词', reference_reason: '', qc_report: {} }
  const detail = { ...runFixture, status: 'asset_review_required', current_step: 'asset_review', images: [
    image, { ...image, id: 2, title: '第二张图', url: null },
    { ...image, id: 3, title: '第三张图', status: 'failed', url: null },
  ] }
  const loading = deferred()
  let imageReady = false
  await page.route(/\/api\/runs(?:\/.*)?(?:\?.*)?$/, (route) => route.fulfill({ json: new URL(route.request().url()).pathname === '/api/runs' ? { items: [detail] } : detail }))
  await page.route('**/api/test-image', async (route) => {
    if (!imageReady) {
      await loading.promise
      return route.fulfill({ status: 503 })
    }
    return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="100"><rect width="400" height="100" fill="purple"/></svg>' })
  })
  await page.goto('/')
  await page.locator('.history-panel button').filter({ hasText: detail.topic }).click()
  await expect(page.getByText('正在加载图片…')).toBeVisible()
  loading.release()
  await expect(page.getByText('图片加载失败')).toBeVisible()
  imageReady = true
  await page.getByRole('button', { name: '重新加载图片' }).click()
  const preview = page.getByRole('img', { name: '第一张图' })
  await expect(preview).toBeVisible()
  expect(await preview.evaluate((image) => image.clientWidth / image.clientHeight)).toBeCloseTo(4, 1)
  await page.getByRole('button', { name: '素材 2 · 第二张图' }).click()
  await expect(page.getByText('暂无图片地址')).toBeVisible()
  await page.getByRole('button', { name: '素材 3 · 第三张图' }).click()
  await expect(page.locator('.asset-preview').getByText('图片生成失败')).toBeVisible()
  await expect(page.getByText('审核对象 · 整组素材')).toBeVisible()
})

for (const [status, action] of [
  ['queued', '取消运行'], ['running', '取消运行'], ['copy_review_required', '通过文案并生成图片'],
  ['image_queued', '取消运行'], ['image_running', '取消运行'], ['asset_review_required', '通过素材并导出'],
  ['completed', '下载发布包'], ['failed', '重试'], ['canceled', null], ['future_status', null],
] as const) {
  test(`stage actions match ${status}`, async ({ page }) => {
    let detail = { ...runFixture, status, current_step: status === 'failed' ? 'draft_revision' : status }
    await page.route(/\/api\/runs(?:\/.*)?(?:\?.*)?$/, (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/cancel')) detail = { ...detail, status: 'canceled', current_step: 'canceled' } as typeof detail
      return route.fulfill({ json: path === '/api/runs' ? { items: [detail] } : detail })
    })
    await page.goto('/')
    await page.locator('.history-panel button').filter({ hasText: detail.topic }).click()
    await expect(page.getByRole('heading', { name: detail.topic })).toBeVisible()
    const actions = page.locator('.review-bar button')
    if (!action) await expect(actions).toHaveCount(0)
    else await expect(actions.filter({ hasText: action })).toBeVisible()
    if (status === 'failed') await expect(page.getByText('文案返修失败')).toBeVisible()
    if (status === 'running') {
      await page.getByRole('button', { name: '取消运行' }).click()
      await expect(page.getByRole('heading', { name: '运行已取消' })).toBeVisible()
      await expect(actions).toHaveCount(0)
    }
  })
}

for (const [width, height] of [[1440, 900], [1366, 768], [1024, 768], [768, 1024], [390, 844], [320, 800]]) {
  test(`workbench fits ${width} × ${height}`, async ({ page }, testInfo) => {
    const wideText = 'VeryLongUnbrokenTopic'.repeat(15)
    const item = { ...runFixture, topic: wideText }
    await page.setViewportSize({ width, height })
    await page.route(/\/api\/runs(?:\/.*)?(?:\?.*)?$/, (route) => route.fulfill({ json: new URL(route.request().url()).pathname === '/api/runs' ? { items: [item] } : item }))
    await page.goto('/')
    await expect(page.getByRole('heading', { name: '开始一篇新内容' })).toBeVisible()
    await expectNoOverflow(page)
    if (width < 1024) await page.getByRole('button', { name: '查看运行历史' }).click()
    await page.locator('.history-panel button').filter({ hasText: wideText }).click()
    await expect(page.getByTestId('approve-copy')).toBeEnabled()
    await expectNoOverflow(page)
    if (width < 1024) {
      await page.getByRole('button', { name: '返回运行历史' }).click()
      await expect(page.getByRole('heading', { name: '最近运行' })).toBeFocused()
      await page.locator('.history-panel button').filter({ hasText: wideText }).click()
      await expect(page.getByTestId('approve-copy')).toBeEnabled()
    }
    await page.screenshot({ path: testInfo.outputPath(`detail-${width}.png`), fullPage: true })
  })
}
