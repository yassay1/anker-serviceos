import { expect, test } from '@playwright/test'
import type { components } from '../src/api/schema'

type S = components['schemas']
const caseId = '11111111-1111-4111-8111-111111111111'
const actorId = '22222222-2222-4222-8222-222222222222'
const tenantId = '33333333-3333-4333-8333-333333333333'
const createdAt = '2026-10-14T01:00:00Z'
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC', 'base64')

test('case image: accepted state, checked preview and same-id recovery', async ({ page }) => {
  const actor: S['ActorRead'] = { actor_id: actorId, tenant_id: tenantId, kind: 'CUSTOMER', role: null, display_name: '客户' }
  let serviceCase: S['CaseRead'] = { id: caseId, customer_id: actorId, problem_text: '图片证据案例',
    user_goal: null, status: 'OPEN', version: 1, created_at: createdAt }
  let saved: S['EvidenceRead'] | null = null
  let firstId = ''
  let uploads = 0
  let checked = false
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    if (path.endsWith('/auth/me')) return route.fulfill({ json: actor })
    if (path === '/api/v1/cases') return route.fulfill({ json: [serviceCase] })
    if (path === `/api/v1/cases/${caseId}`) return route.fulfill({ json: serviceCase })
    if (path.endsWith('/actions') || path.endsWith('/approvals')) return route.fulfill({ json: [] })
    if (path.endsWith('/evidence') && method === 'GET') return route.fulfill({ json: {
      items: saved ? [{ ...saved, inspection_status: checked ? 'CLEAN' : 'PENDING' }] : [], next_cursor: null,
    } satisfies S['EvidencePage'] })
    if (path.endsWith('/evidence') && method === 'POST') {
      uploads += 1
      const body = route.request().postData() ?? ''
      const match = body.match(/name="client_evidence_id"\r?\n\r?\n([0-9a-f-]+)/)
      expect(match).not.toBeNull()
      const id = match![1]
      if (!firstId) firstId = id
      expect(id).toBe(firstId)
      saved = { id: '44444444-4444-4444-8444-444444444444', case_id: caseId,
        client_evidence_id: id, visibility: 'PUBLIC', media_type: 'image/png', byte_size: png.length,
        inspection_status: 'PENDING', verification: 'UNVERIFIED', source_kind: 'CUSTOMER', created_at: createdAt }
      serviceCase = { ...serviceCase, version: 2 }
      if (uploads === 1) return route.abort('failed') // Server committed, transport outcome unknown.
      return route.fulfill({ status: 202, json: saved })
    }
    if (path.endsWith('/content')) return route.fulfill({ status: checked ? 200 : 404,
      body: checked ? png : undefined, contentType: 'image/png' })
    return route.fulfill({ status: 404, json: { detail: '不可见' } })
  })
  await page.goto(`/cases/${caseId}`)
  const panel = page.getByRole('region', { name: '案例图片证据' })
  await panel.getByLabel('选择图片').setInputFiles({ name: 'proof.png', mimeType: 'image/png', buffer: png })
  await panel.getByRole('button', { name: '提交图片' }).click()
  await expect(panel.getByText(/上次上传结果尚未确认/)).toBeVisible()
  await page.reload()
  await expect(panel.getByText('已在服务器记录中找到上次上传的图片。')).toBeVisible()
  expect(uploads).toBe(1)
  await expect(panel.getByText(/图片 #44444444.*待检查/)).toBeVisible()
  await expect(panel.getByRole('button', { name: '查看图片' })).toHaveCount(0)
  checked = true
  await page.reload()
  await panel.getByRole('button', { name: '查看图片' }).click()
  await expect(panel.getByRole('dialog').getByRole('img')).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('case image: wrong owner cannot access detail', async ({ page }) => {
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me')) return route.fulfill({ json: {
      actor_id: actorId, tenant_id: tenantId, kind: 'CUSTOMER', role: null, display_name: '客户',
    } satisfies S['ActorRead'] })
    if (path === '/api/v1/cases') return route.fulfill({ json: [] })
    return route.fulfill({ status: 404, json: { detail: '记录不存在或当前账号无权访问。' } })
  })
  await page.goto(`/cases/${caseId}`)
  await expect(page.getByRole('alert')).toContainText('无权访问')
  await expect(page.getByRole('region', { name: '案例图片证据' })).toHaveCount(0)
})
