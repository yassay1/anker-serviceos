import { expect, test, type Page } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import type { components } from '../src/api/schema'

type S = components['schemas']
const contextOptions = { baseURL: 'http://127.0.0.1:5173', viewport: { width: 1440, height: 1000 } }
const evidencePng = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC', 'base64')

async function login(page: Page, username: string, desk = false) {
  const password = process.env.SERVICEOS_LOCAL_AUTH_PASSWORD
  if (!password) throw new Error('Live regression requires the isolated local development auth configuration.')
  await page.goto(desk ? '/desk' : '/support')
  await page.getByLabel('体验身份').selectOption(username)
  await page.getByLabel('本地体验密码').fill(password)
  await page.getByRole('button', { name: '进入工作区' }).click()
  await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible()
}

test('real API: persisted conversation, human handoff and PUBLIC/INTERNAL separation without an event dispatcher', async ({ browser }) => {
  const customerContext = await browser.newContext(contextOptions)
  const staffContext = await browser.newContext(contextOptions)
  try {
    const customer = await customerContext.newPage()
    const staff = await staffContext.newPage()
    await login(customer, 'customer-a')
    await customer.getByRole('button', { name: '新建会话', exact: true }).click()
    await expect(customer.getByLabel('描述你的问题')).toBeVisible()
    await expect.poll(() => new URL(customer.url()).searchParams.get('conversation')).toMatch(/^[0-9a-f-]{36}$/)
    const conversationId = new URL(customer.url()).searchParams.get('conversation')!
    expect(conversationId).toMatch(/^[0-9a-f-]{36}$/)
    const problem = `真实 API 验收：充电连接不稳定 ${Date.now()}`
    await customer.getByLabel('描述你的问题').fill(problem)
    const receipt = customer.waitForResponse(r => r.url().endsWith(`/conversations/${conversationId}/messages`) && r.request().method() === 'POST')
    await customer.getByRole('button', { name: '发送消息', exact: true }).click()
    expect((await receipt).status()).toBe(202)
    await customer.reload()
    await expect(customer.getByText(problem, { exact: true })).toBeVisible()
    await expect(customer.getByText('实时更新已连接', { exact: true })).toBeVisible()
    const assistance = customer.getByRole('region', { name: '服务交互卡', exact: true })
    await assistance.getByLabel('请求原因').fill('需要人工协助处理当前问题')
    await assistance.getByRole('button', { name: '请求人工协助', exact: true }).click()
    await expect(assistance.getByRole('status')).toHaveText('人工协助请求已保存。')

    await login(staff, 'staff', true)
    await staff.goto(`/desk?conversation=${conversationId}`)
    await expect(staff.getByText(problem, { exact: true })).toBeVisible()
    await staff.getByRole('button', { name: '接管', exact: true }).click()
    await expect(staff.getByText(/需要人工协助处理当前问题 · 已接管/)).toBeVisible()
    await staff.getByLabel('协作模式').selectOption('HUMAN_LEAD')
    await staff.getByLabel('原因', { exact: true }).fill('真实联调人工接续处理')
    await staff.getByRole('button', { name: '切换策略', exact: true }).click()
    await expect(staff.getByText(/当前：真人主导 · 发言策略：仅人工回复/)).toBeVisible()
    await expect(customer.getByText(/当前：真人主导 · 发言策略：仅人工回复/)).toBeVisible()

    const internal = `仅内部审阅的联调备注 ${Date.now()}`
    await staff.getByLabel('仅客服可见的内部备注').check()
    await staff.getByLabel('回复客户').fill(internal)
    const savedNote = staff.waitForResponse(r => r.url().endsWith(`/conversations/${conversationId}/messages`) && r.request().method() === 'POST')
    await staff.getByRole('button', { name: '发送消息', exact: true }).click()
    expect((await savedNote).status()).toBe(202)
    await staff.getByLabel('仅客服可见的内部备注').uncheck()
    const publicReply = `已由客服接续处理 ${Date.now()}`
    await staff.getByLabel('回复客户').fill(publicReply)
    const savedReply = staff.waitForResponse(r => r.url().endsWith(`/conversations/${conversationId}/messages`) && r.request().method() === 'POST')
    await staff.getByRole('button', { name: '发送消息', exact: true }).click()
    const publicReceipt = await savedReply
    expect(publicReceipt.status()).toBe(202)
    expect((await publicReceipt.json() as S['MessageReceipt']).message.visibility).toBe('PUBLIC')
    await expect(customer.getByText(publicReply, { exact: true })).toBeVisible()
    await expect(customer.getByText(internal, { exact: true })).toHaveCount(0)
    const response = await customerContext.request.get(`/api/v1/conversations/${conversationId}/messages`)
    expect(response.status()).toBe(200)
    const messages = await response.json() as S['MessagePage']
    expect(messages.items.every(item => item.visibility === 'PUBLIC')).toBe(true)
    await customer.screenshot({ path: 'test-results/live-support-desktop.png', fullPage: true })
    await staff.screenshot({ path: 'test-results/live-desk-desktop.png', fullPage: true })
    await customer.goto('/desk')
    await expect(customer.getByRole('heading', { name: '此页面仅供客服使用' })).toBeVisible()
  } finally {
    await customerContext.close()
    await staffContext.close()
  }
})

test('real API: authorized device history and rejection for another customer and tenant', async ({ browser }) => {
  const ownerContext = await browser.newContext(contextOptions)
  try {
    const owner = await ownerContext.newPage()
    await login(owner, 'customer-a')
    const created = await ownerContext.request.post('/api/v1/devices', { data: { model: '联调测试设备', serial_number: `TEST-${Date.now()}` } })
    expect(created.status()).toBe(201)
    const device = await created.json() as S['DeviceRead']
    const createdCase = await ownerContext.request.post('/api/v1/cases', { data: { problem_text: '联调设备服务记录', user_goal: '保留可查看的关联历史' } })
    expect(createdCase.status()).toBe(201)
    const serviceCase = await createdCase.json() as S['CaseRead']
    const linked = await ownerContext.request.post(`/api/v1/cases/${serviceCase.id}/devices`, { data: { device_id: device.id, expected_version: serviceCase.version } })
    expect(linked.status()).toBe(200)
    await owner.goto(`/devices/${device.id}`)
    await expect(owner.getByRole('heading', { name: '联调测试设备', exact: true })).toBeVisible()
    await expect(owner.getByText('身份待核验', { exact: true })).toBeVisible()
    await expect(owner.getByText('联调设备服务记录', { exact: true })).toBeVisible()
    await owner.setViewportSize({ width: 390, height: 844 })
    expect(await owner.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await owner.screenshot({ path: 'test-results/live-device-mobile.png', fullPage: true })
    for (const username of ['customer-b', 'other-tenant']) {
      const otherContext = await browser.newContext(contextOptions)
      try {
        const other = await otherContext.newPage()
        await login(other, username)
        await other.goto(`/devices/${device.id}`)
        await expect(other.getByRole('alert')).toContainText('无权访问')
        await expect(other.getByRole('heading', { name: '联调测试设备', exact: true })).toHaveCount(0)
      } finally { await otherContext.close() }
    }
  } finally { await ownerContext.close() }
})

test('real API: separate mock request, supervisor approval, worker receipt and customer projection', async ({ browser }) => {
  const customerContext = await browser.newContext(contextOptions)
  const staffContext = await browser.newContext(contextOptions)
  const supervisorContext = await browser.newContext(contextOptions)
  try {
    const customer = await customerContext.newPage()
    const staff = await staffContext.newPage()
    const supervisor = await supervisorContext.newPage()
    await login(customer, 'customer-a')
    const created = await customerContext.request.post('/api/v1/cases', { data: {
      problem_text: `模拟动作联调案例 ${Date.now()}`,
    } })
    expect(created.status()).toBe(201)
    const serviceCase = await created.json() as S['CaseRead']
    await login(staff, 'staff', true)
    await staff.goto(`/cases/${serviceCase.id}`)
    const actions = staff.getByRole('region', { name: '模拟售后动作' })
    await actions.getByLabel('申请原因').fill('需要模拟提交一次售后请求')
    await actions.getByRole('button', { name: '提交待审批请求' }).click()
    await expect(actions.getByText('模拟动作请求已保存，等待另一位有审批权限的客服处理。')).toBeVisible()
    await expect(actions.getByText('尚无模拟回执；审批状态不代表执行成功。')).toBeVisible()
    await login(supervisor, 'supervisor', true)
    await supervisor.goto(`/cases/${serviceCase.id}`)
    const review = supervisor.getByRole('region', { name: '模拟售后动作' })
    await review.getByRole('button', { name: '批准', exact: true }).click()
    await expect(review.getByText('审批已保存，模拟操作等待 Worker 执行。')).toBeVisible()
    const listed = await staffContext.request.get(`/api/v1/cases/${serviceCase.id}/actions`)
    expect(listed.status()).toBe(200)
    const action = (await listed.json() as S['CaseActionRead'][])[0]
    expect(action.status).toBe('APPROVED')
    for (let attempt = 0; attempt < 10; attempt++) {
      execFileSync('uv', ['run', '--project', '../backend', '--locked', 'python', '-m', 'serviceos_api.worker.actions', '--once'], {
        cwd: process.cwd(), env: process.env, timeout: 30_000,
      })
      const current = await staffContext.request.get(`/api/v1/actions/${action.id}`)
      if ((await current.json() as S['CaseActionRead']).status === 'SUCCEEDED') break
    }
    await customer.goto(`/cases/${serviceCase.id}`)
    const customerActions = customer.getByRole('region', { name: '模拟售后动作' })
    await expect(customerActions.getByText(/模拟回执：MOCK-/)).toBeVisible()
    await expect(customerActions.getByText(/申请原因/)).toHaveCount(0)
    const customerRead = await customerContext.request.get(`/api/v1/actions/${action.id}`)
    expect((await customerRead.json() as S['CaseActionRead']).receipt?.adapter).toBe('MOCK')
    await customer.screenshot({ path: 'test-results/live-mock-action-customer.png', fullPage: true })
    await customer.setViewportSize({ width: 390, height: 844 })
    expect(await customer.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await customer.screenshot({ path: 'test-results/live-mock-action-customer-mobile.png', fullPage: true })
    await supervisor.screenshot({ path: 'test-results/live-mock-action-supervisor.png', fullPage: true })
  } finally {
    await customerContext.close()
    await staffContext.close()
    await supervisorContext.close()
  }
})

test('real API: customer image upload, inspection and authorized preview', async ({ browser }) => {
  const ownerContext = await browser.newContext(contextOptions)
  const otherContext = await browser.newContext(contextOptions)
  const staffContext = await browser.newContext(contextOptions)
  try {
    const owner = await ownerContext.newPage()
    const other = await otherContext.newPage()
    const staff = await staffContext.newPage()
    await login(owner, 'customer-a')
    const created = await ownerContext.request.post('/api/v1/cases', { data: {
      problem_text: `图片上传联调案例 ${Date.now()}`,
    } })
    expect(created.status()).toBe(201)
    const serviceCase = await created.json() as S['CaseRead']
    await owner.goto(`/cases/${serviceCase.id}`)
    const panel = owner.getByRole('region', { name: '案例图片证据' })
    await panel.getByLabel('选择图片').setInputFiles({ name: 'evidence.png', mimeType: 'image/png', buffer: evidencePng })
    await panel.getByRole('button', { name: '提交图片' }).click()
    await expect(panel.getByText(/图片已受理，等待服务端结构检查/)).toBeVisible()
    await expect(panel.getByText(/待检查/).last()).toBeVisible()
    await expect(panel.getByRole('button', { name: '查看图片' })).toHaveCount(0)
    const before = await ownerContext.request.get(`/api/v1/cases/${serviceCase.id}/evidence`)
    expect(before.status()).toBe(200)
    const evidence = ((await before.json() as S['EvidencePage']).items)[0]
    expect(evidence.inspection_status).toBe('PENDING')
    const forbiddenBefore = await ownerContext.request.get(`/api/v1/cases/${serviceCase.id}/evidence/${evidence.id}/content`)
    expect(forbiddenBefore.status()).toBe(404)
    for (let attempt = 0; attempt < 10; attempt++) {
      execFileSync('uv', ['run', '--project', '../backend', '--locked', 'python', '-m', 'serviceos_api.worker.inspection', '--once'], {
        cwd: process.cwd(), env: process.env, timeout: 30_000,
      })
      const listed = await ownerContext.request.get(`/api/v1/cases/${serviceCase.id}/evidence`)
      if ((await listed.json() as S['EvidencePage']).items[0].inspection_status === 'CLEAN') break
    }
    await owner.reload()
    await panel.getByRole('button', { name: '查看图片' }).click()
    await expect(panel.getByRole('dialog').getByRole('img')).toBeVisible()
    await login(other, 'customer-b')
    const hidden = await otherContext.request.get(`/api/v1/cases/${serviceCase.id}/evidence`)
    expect(hidden.status()).toBe(404)
    await login(staff, 'staff', true)
    await staff.goto(`/cases/${serviceCase.id}`)
    const staffPanel = staff.getByRole('region', { name: '案例图片证据' })
    await staffPanel.getByLabel('可见范围').selectOption('INTERNAL')
    await staffPanel.getByLabel('选择图片').setInputFiles({ name: 'internal.png', mimeType: 'image/png', buffer: evidencePng })
    await staffPanel.getByRole('button', { name: '提交图片' }).click()
    await expect(staffPanel.getByText(/图片已受理/)).toBeVisible()
    await owner.reload()
    const customerList = await ownerContext.request.get(`/api/v1/cases/${serviceCase.id}/evidence`)
    expect((await customerList.json() as S['EvidencePage']).items).toHaveLength(1)
    await owner.setViewportSize({ width: 390, height: 844 })
    expect(await owner.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await owner.screenshot({ path: 'test-results/live-case-evidence-mobile.png', fullPage: true })
  } finally {
    await ownerContext.close()
    await otherContext.close()
    await staffContext.close()
  }
})
