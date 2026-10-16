import { expect, test, type Page } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import type { components } from '../src/api/schema'

type S = components['schemas']
const contextOptions = { baseURL: process.env.SERVICEOS_LIVE_BASE_URL || 'http://127.0.0.1:5173', viewport: { width: 1440, height: 1000 } }
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
    const existingConversation = await customerContext.request.post('/api/v1/conversations', { data: {} })
    expect(existingConversation.status()).toBe(201)
    const previousConversationId = (await existingConversation.json() as S['ConversationRead']).id
    await customer.reload()
    await expect.poll(() => new URL(customer.url()).searchParams.get('conversation')).toBe(previousConversationId)
    await customer.getByRole('button', { name: '开始新对话', exact: true }).click()
    await expect(customer.getByLabel('描述你的问题')).toBeVisible()
    await expect.poll(() => new URL(customer.url()).searchParams.get('conversation')).toMatch(/^[0-9a-f-]{36}$/)
    await expect.poll(() => new URL(customer.url()).searchParams.get('conversation')).not.toBe(previousConversationId)
    const conversationId = new URL(customer.url()).searchParams.get('conversation')!
    expect(conversationId).toMatch(/^[0-9a-f-]{36}$/)
    const problem = `真实 API 验收：充电连接不稳定 ${Date.now()}`
    await customer.getByLabel('描述你的问题').fill(problem)
    const receipt = customer.waitForResponse(r => r.request().method() === 'POST' && /\/api\/v1\/conversations\/[^/]+\/messages$/.test(new URL(r.url()).pathname), { timeout: 15_000 })
    await customer.getByRole('button', { name: '发送消息', exact: true }).click()
    const messageReceipt = await receipt
    expect(messageReceipt.status()).toBe(202)
    expect((await messageReceipt.json() as S['MessageReceipt']).message.conversation_id).toBe(conversationId)
    await customer.reload()
    await expect(customer.getByText(problem, { exact: true })).toBeVisible()
    await expect(customer.getByText('实时更新已连接', { exact: true })).toBeVisible()
    const assistance = customer.getByRole('region', { name: '服务交互卡', exact: true })
    await assistance.locator('details.ui-ActionBar > summary').click()
    await assistance.getByLabel('请求原因').fill('需要人工协助处理当前问题')
    await assistance.getByRole('button', { name: '请求人工协助', exact: true }).click()
    await expect(assistance.getByRole('status')).toHaveText('人工协助请求已保存。')

    await login(staff, 'staff', true)
    await staff.goto(`/desk?conversation=${conversationId}`)
    await expect(staff.getByText(problem, { exact: true })).toBeVisible()
    await staff.getByRole('button', { name: '人工协作与审批', exact: true }).click()
    await staff.getByRole('button', { name: '接管', exact: true }).click()
    await expect(staff.getByText(/需要人工协助处理当前问题 · 已接管/)).toBeVisible()
    await staff.getByLabel('协作模式').selectOption('HUMAN_LEAD')
    await staff.getByLabel('原因', { exact: true }).fill('真实联调人工接续处理')
    await staff.getByRole('button', { name: '切换策略', exact: true }).click()
    await expect(staff.getByText(/当前：真人主导 · 发言策略：仅人工回复/)).toBeVisible()
    await expect(customer.getByRole('region', { name: '人机协作' }).getByText('真人主导 · 仅人工回复')).toBeVisible()

    const internal = `仅内部审阅的联调备注 ${Date.now()}`
    await staff.getByRole('button', { name: '内部备注', exact: true }).click()
    await staff.getByLabel('回复客户').fill(internal)
    const savedNote = staff.waitForResponse(r => r.url().endsWith(`/conversations/${conversationId}/messages`) && r.request().method() === 'POST')
    await staff.getByRole('button', { name: '保存内部备注', exact: true }).click()
    expect((await savedNote).status()).toBe(202)
    await staff.getByRole('button', { name: '回复客户', exact: true }).click()
    const publicReply = `已由客服接续处理 ${Date.now()}`
    await staff.getByLabel('回复客户').fill(publicReply)
    const savedReply = staff.waitForResponse(r => r.url().endsWith(`/conversations/${conversationId}/messages`) && r.request().method() === 'POST')
    await staff.getByRole('button', { name: '发送回复', exact: true }).click()
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
    const verification = customer.getByRole('region', { name: '结果核验' })
    await expect(verification.getByText('模拟服务请求收到成功回执')).toBeVisible()
    await expect(verification.getByRole('button', { name: '保存观察结果' })).toBeDisabled()
    await verification.getByLabel('现在的实际情况').selectOption('WORKING')
    await verification.getByLabel('补充说明').fill('客户测试后确认原问题已解决')
    await verification.getByRole('button', { name: '保存观察结果' }).click()
    await expect(verification.getByText(/已恢复 · 已核验解决/)).toBeVisible()
    const resolvedCase = await customerContext.request.get(`/api/v1/cases/${serviceCase.id}`)
    expect((await resolvedCase.json() as S['CaseRead']).status).toBe('RESOLVED')
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

test('real API: customer consent precedes staff follow-up schedule', async ({ browser }) => {
  const customerContext = await browser.newContext(contextOptions)
  const staffContext = await browser.newContext(contextOptions)
  try {
    const customer = await customerContext.newPage()
    const staff = await staffContext.newPage()
    await login(customer, 'customer-a')
    const created = await customerContext.request.post('/api/v1/cases', { data: {
      problem_text: `回访联调案例 ${Date.now()}`,
    } })
    expect(created.status()).toBe(201)
    const serviceCase = await created.json() as S['CaseRead']
    const conversation = await customerContext.request.post('/api/v1/conversations', { data: {} })
    expect(conversation.status()).toBe(201)
    const conversationId = (await conversation.json() as S['ConversationRead']).id
    const linked = await customerContext.request.post(`/api/v1/cases/${serviceCase.id}/conversations`, { data: {
      expected_version: serviceCase.version, conversation_id: conversationId,
    } })
    expect(linked.status()).toBe(200)
    await login(staff, 'staff', true)
    await staff.goto(`/cases/${serviceCase.id}`)
    const staffPanel = staff.getByRole('region', { name: '回访安排' })
    await expect(staffPanel.getByRole('button', { name: '保存预约' })).toBeDisabled()
    await customer.goto(`/cases/${serviceCase.id}`)
    const panel = customer.getByRole('region', { name: '回访安排' })
    await panel.locator('details.secondary-form > summary').click()
    await panel.getByLabel('回访目的').fill('确认设备充电恢复情况')
    await panel.getByRole('button', { name: '同意此目的的回访' }).click()
    await expect(panel.getByText('同意已保存，客服现在可以预约此次回访。')).toBeVisible()
    await staff.reload()
    await staffPanel.getByLabel('客户已同意的目的').selectOption({ label: '确认设备充电恢复情况' })
    const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000)
    const localValue = new Date(tomorrow.getTime() - tomorrow.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
    await staffPanel.getByLabel('回访时间').fill(localValue)
    await staffPanel.getByRole('button', { name: '保存预约' }).click()
    await expect(staffPanel.getByText('回访已预约；到期后系统会生成客服待办，不会自动联系客户。')).toBeVisible()
    await customer.reload()
    await expect(panel.getByText(/等待到期/)).toBeVisible()
    const tasks = await staffContext.request.get(`/api/v1/conversations/${conversationId}/tasks`)
    expect(await tasks.json()).toEqual([])
  } finally {
    await customerContext.close()
    await staffContext.close()
  }
})

test('real API: case fact appears in device passport only after verification and resolution archive', async ({ browser }) => {
  const customerContext = await browser.newContext(contextOptions)
  const staffContext = await browser.newContext(contextOptions)
  try {
    const customer = await customerContext.newPage()
    const staff = await staffContext.newPage()
    await login(customer, 'customer-a')
    const deviceResponse = await customerContext.request.post('/api/v1/devices', { data: {
      model: `事实归档设备 ${Date.now()}`,
    } })
    expect(deviceResponse.status()).toBe(201)
    const device = await deviceResponse.json() as S['DeviceRead']
    const caseResponse = await customerContext.request.post('/api/v1/cases', { data: {
      problem_text: `事实归档案例 ${Date.now()}`,
    } })
    expect(caseResponse.status()).toBe(201)
    const serviceCase = await caseResponse.json() as S['CaseRead']
    const link = await customerContext.request.post(`/api/v1/cases/${serviceCase.id}/devices`, { data: {
      device_id: device.id, expected_version: serviceCase.version,
    } })
    expect(link.status()).toBe(200)
    const linkedCase = await link.json() as S['CaseRead']
    await login(staff, 'staff', true)
    await staff.goto(`/devices/${device.id}`)
    await staff.locator('.staff-advanced > summary').click()
    const panel = staff.getByRole('region', { name: '案例事实归档' })
    await panel.getByLabel('来源案例').selectOption(serviceCase.id)
    await panel.getByLabel('事实字段').fill('port_type')
    await panel.getByLabel('核对到的内容').fill('USB-C')
    await panel.getByRole('button', { name: '保存候选事实' }).click()
    await expect(panel.getByText('候选事实已保存，需客服核验后再考虑归档。')).toBeVisible()
    await panel.getByLabel('核验或撤销原因').fill('已核对实物端口')
    await panel.getByRole('button', { name: '核验事实' }).click()
    await expect(panel.getByText('事实已由客服核验，待来源案例解决后方可归档。')).toBeVisible()
    await expect(panel.getByRole('button', { name: '归档到设备' })).toBeDisabled()
    await customer.goto(`/devices/${device.id}`)
    await expect(customer.getByText('暂无已核验事实')).toBeVisible()
    const started = await staffContext.request.post(`/api/v1/cases/${serviceCase.id}/transitions`, { data: {
      expected_version: linkedCase.version, target_status: 'IN_PROGRESS', reason: '人工复核处理中',
    } })
    expect(started.status()).toBe(200)
    const resolved = await staffContext.request.post(`/api/v1/cases/${serviceCase.id}/transitions`, { data: {
      expected_version: (await started.json() as S['CaseRead']).version,
      target_status: 'RESOLVED', reason: '客户确认原问题解决',
    } })
    expect(resolved.status()).toBe(200)
    await staff.reload()
    await staff.locator('.staff-advanced > summary').click()
    await panel.getByRole('button', { name: '归档到设备' }).click()
    await expect(panel.getByText('已核验事实归档到长期设备档案。')).toBeVisible()
    await customer.reload()
    await expect(customer.getByRole('region', { name: '已核验事实' }).getByText('USB-C')).toBeVisible()
    await staff.screenshot({ path: 'test-results/live-case-fact-staff.png', fullPage: true })
    await staff.setViewportSize({ width: 390, height: 844 })
    expect(await staff.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await staff.screenshot({ path: 'test-results/live-case-fact-staff-mobile.png', fullPage: true })
    await panel.getByLabel('核验或撤销原因').fill('复核后发现端口记录错误')
    await panel.getByRole('button', { name: '撤销事实' }).click()
    await expect(panel.getByText('事实已撤销，不再作为可信设备事实展示。')).toBeVisible()
    await customer.reload()
    await expect(customer.getByText('暂无已核验事实')).toBeVisible()
  } finally {
    await customerContext.close()
    await staffContext.close()
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
