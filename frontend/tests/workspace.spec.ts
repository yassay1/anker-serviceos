import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { fixture, ids } from './workspace-fixture'

test('adaptation: search and status filter operate on loaded conversations', async ({ page }) => {
  const state = await fixture(page)
  await page.goto('/desk')
  const list = page.getByRole('complementary', { name: '会话列表', exact: true })
  await page.getByLabel('搜索已加载的会话').fill('22222222')
  await expect(list.getByRole('button', { name: /22222222/ })).toBeVisible()
  await expect(list.getByRole('button', { name: /11111111/ })).toHaveCount(0)
  await page.getByLabel('搜索已加载的会话').clear()
  await list.getByRole('button', { name: '进行中', exact: true }).click()
  await expect(list.getByRole('button', { name: /22222222/ })).toHaveCount(0)
  await expect(list.getByRole('button', { name: /11111111/ })).toBeVisible()
  expect(state.unexpected).toEqual([])
})

test('adaptation: drafts and visibility stay with their conversation', async ({ page }) => {
  const state = await fixture(page)
  state.conversations[1].status = 'ACTIVE'
  await page.goto('/desk')
  await page.getByLabel('回复客户').fill('会话 A 的内部记录')
  await page.getByLabel('仅客服可见的内部备注').check()
  const list = page.getByRole('complementary', { name: '会话列表', exact: true })
  await list.getByRole('button', { name: /22222222/ }).click()
  await expect(page.getByLabel('回复客户')).toHaveValue('')
  await expect(page.getByLabel('仅客服可见的内部备注')).not.toBeChecked()
  await page.getByLabel('回复客户').fill('会话 B 的公开回复')
  await list.getByRole('button', { name: /11111111/ }).click()
  await expect(page.getByLabel('回复客户')).toHaveValue('会话 A 的内部记录')
  await expect(page.getByLabel('仅客服可见的内部备注')).toBeChecked()
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  await expect.poll(() => state.sent.length).toBe(1)
  expect(state.sent[0]).toMatchObject({ visibility: 'INTERNAL', content: [{ type: 'text', text: '会话 A 的内部记录' }] })
})

test('adaptation: narrow screen panels preserve the message draft', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await fixture(page, false)
  await page.goto('/support')
  await page.getByLabel('描述你的问题').fill('充电宝无法持续充电')
  await page.getByRole('button', { name: '资料与协助', exact: true }).click()
  await expect(page.getByRole('button', { name: '请求人工协助', exact: true })).toBeVisible()
  await expect(page.getByLabel('描述你的问题')).toBeHidden()
  await page.getByRole('button', { name: '会话', exact: true }).click()
  await expect(page.getByLabel('描述你的问题')).toHaveValue('充电宝无法持续充电')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('adaptation: draft review requires the backend minimum reason length', async ({ page }) => {
  await fixture(page)
  await page.goto('/desk')
  await page.getByLabel('原因', { exact: true }).fill('短')
  await expect(page.getByRole('button', { name: '批准', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '拒绝', exact: true })).toBeDisabled()
})

test('adaptation: device details show actual facts and history without verifying identity', async ({ page }) => {
  const state = await fixture(page, false)
  await page.goto(`/devices/${ids.device}`)
  await expect(page.getByRole('heading', { name: 'Anker 737', exact: true })).toBeVisible()
  await expect(page.getByText('身份待核验', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('人工测量记录')).toBeVisible()
  await expect(page.getByText('充电接口不稳定', { exact: true })).toBeVisible()
  await expect(page.getByText('PRIVATE-SERIAL-0921', { exact: true })).toHaveCount(0)
  expect(state.unexpected).toEqual([])
})

test('adaptation: explicit forbidden device never falls back to another record', async ({ page }) => {
  await fixture(page, false)
  await page.route(`**/api/v1/devices/${ids.second}`, route => route.fulfill({ status: 404, json: { detail: '设备不存在或无权访问。' } }))
  await page.goto(`/devices/${ids.second}`)
  await expect(page.getByRole('alert')).toContainText('设备不存在或无权访问。')
  await expect(page.getByRole('heading', { name: 'Anker 737', exact: true })).toHaveCount(0)
})

for (const [route, staff, mobile] of [['/desk', true, false], ['/desk', true, true], ['/support', false, false], ['/support', false, true], [`/devices/${ids.device}`, false, false], [`/devices/${ids.device}`, false, true]] as const) {
  test(`adaptation: accessible ${route} ${mobile ? 'mobile' : 'desktop'} capture`, async ({ page }) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 })
    const state = await fixture(page, staff)
    await page.goto(route)
    if (route.includes('/devices')) await expect(page.getByText('人工测量记录')).toBeVisible()
    else await expect(page.getByLabel(staff ? '回复客户' : '描述你的问题')).toBeVisible()
    const scan = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
    expect(scan.violations).toEqual([])
    expect(state.unexpected).toEqual([])
    await page.screenshot({ path: `test-results/adaptation-${staff ? 'desk' : route.includes('devices') ? 'devices' : 'support'}-${mobile ? 'mobile' : 'desktop'}.png`, fullPage: true })
  })
}
