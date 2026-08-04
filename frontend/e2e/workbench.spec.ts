import { expect, test } from '@playwright/test'

const API_BASE = 'http://127.0.0.1:8090'
const API_TOKEN = 'e2e-api-token'

test('complete mock workflow from Brief and upload through export', async ({ page }) => {
  await page.goto('/')
  await page.getByTestId('brief-topic').fill('Playwright commuting writing check')
  await page.getByTestId('brief-audience').fill('IELTS self-study commuters')
  await page.getByTestId('brief-product').fill('Writing Checker')
  await page.getByTestId('brief-pain-point').fill('My examples do not support the point')
  await page.getByTestId('brief-upload').setInputFiles({
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

  await page.getByTestId('approve-assets').click()
  await expect(page.getByTestId('export-download')).not.toHaveClass(/disabled/)
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByTestId('export-download').click(),
  ])
  expect(download.suggestedFilename()).toMatch(/\.zip$/)
})
